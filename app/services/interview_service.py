"""Interview service for AI-driven interview flow.

Generates questions, evaluates answers, and produces reports
using the LLM client, optionally backed by knowledge base retrieval.
"""

import json
import re
from typing import Optional

from fastapi import UploadFile

from app.services.llm_client import LLMClient
from app.services.interview_agent import InterviewPlanner, PlannerContext
from app.services.resume_parser import ResumeParser
from app.storage.faiss_store import FaissStore
from app.services.embedding import EmbeddingService
from app.storage.interview_store import InterviewStore
from app.services.topic_tracker import TopicTracker
from app.services.retrieval_facade import RetrievalFacade
from app.utils.logger import get_logger
from app.config import settings
from app.exceptions import AuthorizationError

logger = get_logger(__name__)

# --- Prompt templates ---

SYSTEM_START = """你是一个专业的 Java/后端技术面试官。
你的职责是：
1. 根据岗位方向出题，覆盖技术知识点、项目经验、系统设计
2. 公正评价面试者的回答，给出评分和具体建议
3. 根据回答质量动态调整后续题目难度

请严格按 JSON 格式输出，不要包含额外说明。"""

QUESTION_PROMPT = """你正在进行一场 {position} 岗位的面试。

当前是第 {round} 题。
前面已有 {history_count} 道题，难度分布：{difficulty_history}
上一题评价：{last_evaluation_summary}

{knowledge_context}

{coverage_summary}
{suggested_topic}

【知识树参考】
{knowledge_tree_structure}

请出一道{难度提示}技术面试题，混合技术知识点、项目经验或系统设计方向。
题目应该是面试中常见的高质量题目。

请按以下 JSON 格式输出（不要包含其他内容）：
{{
    "question": "题目内容",
    "difficulty": "easy/medium/hard",
    "source": "kb/llm",
    "knowledge_tags": ["知识点标签1", "知识点标签2"],
    "topic": "从知识树中选择的 topic 名称",
    "category": "从知识树中选择的 category 名称"
}}"""

EVALUATE_PROMPT = """请对面试者的回答进行评价。

题目：{question}
难度：{difficulty}
期望考察的知识点：{knowledge_tags}

面试者的回答：{answer}

{knowledge_context}

请按以下 JSON 格式评价（不要包含其他内容）：
{{
    "score": <1-10 的整数>,
    "comment": "一句话评价摘要（优点和不足各一句，约 30-50 字）",
    "score_reason": "评分原因：按条目列出「答对的部分」与「遗漏或错误的部分」，约 100-200 字",
    "reference_answer": "该题的参考答案要点：结构化列出标准回答应覆盖的关键点，约 150-300 字",
    "tags": ["涉及知识点1", "涉及知识点2"],
    "next_difficulty": "easy/medium/hard",
    "should_end": false
}}

评分标准：
- 9-10：回答准确完整，深度超出预期
- 7-8：回答正确，覆盖主要知识点，略有不足
- 5-6：回答基本正确，但不够深入或遗漏关键点
- 3-4：回答有明显错误或遗漏
- 1-2：回答完全不对或避而不答"""

REPORT_PROMPT = """请根据以下面试记录生成面试报告。

岗位：{position}
总题数：{total_rounds}
总分：{total_score}

各题详情：
{questions_detail}

请按以下 JSON 格式输出（不要包含其他内容）：
{{
    "score_breakdown": [
        {{"round": 1, "question": "完整题目", "score": 7, "tags": ["知识点1"], "comment": "一句话摘要", "score_reason": "评分原因", "reference_answer": "参考答案"}}
    ],
    "total_score": <1-10 的浮点数>,
    "knowledge_analysis": {{
        "strengths": ["掌握较好的知识点1", "掌握较好的知识点2"],
        "weaknesses": ["薄弱的知识点1", "薄弱的知识点2"]
    }},
    "improvement_suggestions": [
        "具体改进建议1",
        "具体改进建议2"
    ],
    "level": "初级/中级/高级"
}}

等级标准：
- 8分以上：高级 — 深度和广度俱佳
- 6-7.9分：中级 — 基础扎实，需补充深度
- 6分以下：初级 — 需要系统性地补充知识"""


# --- Difficulty indicator ---

def _difficulty_label(d: str) -> str:
    return {"easy": "偏易", "medium": "适中", "hard": "偏难"}.get(d, "适中")


def _parse_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    # Try to find JSON in markdown code blocks first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Fallback: try to parse entire text as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Last resort: try to find { ... } in the text
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


class InterviewService:
    """Core interview logic: question generation, evaluation, reporting."""

    def __init__(
        self,
        store: InterviewStore,
        llm: LLMClient,
        faiss: Optional[FaissStore] = None,
        embedding: Optional[EmbeddingService] = None,
        resume_parser: Optional[ResumeParser] = None,
        topic_tracker: Optional[TopicTracker] = None,
        facade: Optional[RetrievalFacade] = None,
    ):
        self.store = store
        self.llm = llm
        self.faiss = faiss
        self.embedding = embedding
        self.resume_parser = resume_parser
        self.topic_tracker = topic_tracker
        self.facade = facade
        self.followup_retrieval = settings.enable_interview_followup_retrieval
        self.max_rounds = 15
        self.min_rounds = 5
        self.planner = InterviewPlanner()

    async def start(
        self,
        position: str,
        username: str = "",
        resume_file: Optional[UploadFile] = None,
        jd_text: Optional[str] = None,
    ) -> dict:
        """Start a new interview session, optionally with resume+JD analysis."""
        # Create session with empty analysis first
        session = self.store.create_session(position, username=username)

        # Parse resume and JD if provided
        resume_analysis = {}
        jd_analysis = {}
        match_analysis = {}
        resume_raw = ""
        jd_raw = ""

        if resume_file and self.resume_parser:
            try:
                resume_raw = await self.resume_parser.extract_pdf_text(resume_file)
                if resume_raw:
                    resume_analysis = await self.resume_parser.parse_resume(resume_raw)
            except Exception as e:
                logger.warning(f"Resume parsing failed: {e}")

        if jd_text and self.resume_parser:
            try:
                jd_raw = jd_text
                jd_analysis = await self.resume_parser.parse_jd(jd_text)
            except Exception as e:
                logger.warning(f"JD parsing failed: {e}")

        # Perform matching analysis if both resume and JD are available
        if resume_analysis and jd_analysis:
            try:
                match_analysis = await self.resume_parser.analyze_match(resume_analysis, jd_analysis)
            except Exception as e:
                logger.warning(f"Match analysis failed: {e}")

        # Store analysis results
        self.store.update_analysis(
            session["id"],
            resume_text=resume_raw[:5000] if resume_raw else None,
            resume_analysis=json.dumps(resume_analysis, ensure_ascii=False) if resume_analysis else None,
            jd_text=jd_raw[:3000] if jd_raw else None,
            jd_analysis=json.dumps(jd_analysis, ensure_ascii=False) if jd_analysis else None,
            match_analysis=json.dumps(match_analysis, ensure_ascii=False) if match_analysis else None,
        )

        # Generate first question with personalized context
        question_data = await self._generate_question(
            session["id"], position, round_num=1,
            match_analysis=match_analysis,
            resume_analysis=resume_analysis,
            jd_analysis=jd_analysis,
        )

        return {
            "session_id": session["id"],
            "question": question_data,
        }

    def _authorize(self, session_id: str, username: str | None) -> None:
        """校验登录用户是否拥有该面试场次；不拥有则抛 AuthorizationError(403)。"""
        if username is None:
            return
        if not self.store.owns_session(session_id, username):
            raise AuthorizationError("无权访问该面试场次")

    async def answer(self, question_id: str, answer: str, generate_next: bool = True,
                     username: str | None = None) -> dict:
        """Submit an answer, get evaluation and optionally next question.

        Args:
            question_id: The question to answer.
            answer: The user's answer text.
            generate_next: If True, also generate the next question. When the
                user is re-answering the same question ("再答一次"), pass False
                to only return the fresh evaluation and let the frontend decide.
        """
        # Get the question record directly from SQLite
        with self.store._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM interview_questions WHERE id = ?", (question_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"Question not found: {question_id}")

        question = dict(row)
        session_id = question["session_id"]
        session = self.store.get_session(session_id)

        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # 用户隔离：校验当前登录用户拥有该场次
        self._authorize(session_id, username)

        # Evaluate the answer —— 评价 query 保持「问题 + 用户回答」拼接（Part B §5.3），
        # 统一走 facade 检索并带回来源用于溯源
        kb_context, kb_sources = await self._retrieve_context_with_sources(
            question["question"] + " " + answer
        )
        eval_prompt = EVALUATE_PROMPT.format(
            question=question["question"],
            difficulty=question["difficulty"],
            knowledge_tags=question.get("knowledge_tags", "[]"),
            answer=answer,
            knowledge_context=kb_context,
        )
        eval_text = await self.llm.chat(eval_prompt)
        evaluation = _parse_json(eval_text) or {
            "score": 5,
            "comment": "评价解析失败，请参考面试报告。",
            "score_reason": "",
            "reference_answer": "",
            "tags": ["未知"],
            "next_difficulty": "medium",
            "should_end": False,
        }
        # 容错：LLM 输出缺少新字段时补空，避免前端渲染异常
        if not isinstance(evaluation, dict):
            evaluation = {"score": 5, "comment": "", "score_reason": "", "reference_answer": "", "tags": [], "next_difficulty": "medium", "should_end": False}
        evaluation.setdefault("score_reason", "")
        evaluation.setdefault("reference_answer", "")
        # 溯源（Part B §5.5）：评价所用检索来源（文档名 + chunk 定位），随评价入库供报告回查
        evaluation.setdefault("sources", kb_sources)

        score = evaluation.get("score", 5)
        self.store.update_answer(question_id, answer, evaluation, score)

        # Check if interview should end
        should_end = evaluation.get("should_end", False)
        total_rounds = session["total_rounds"] or 0

        if self._decide_action(
            mode="interview", total_answered=total_rounds,
            should_end=should_end, last_evaluation=evaluation,
        ) == "generate_report":
            # End the interview
            report = await self._generate_report(session_id)
            self.store.complete_session(session_id, report)
            return {
                "evaluation": evaluation,
                "is_complete": True,
                "report": report,
                "session_id": session_id,
            }

        if total_rounds >= self.min_rounds:
            # Ask user if they want to continue (we'll let the frontend decide)
            pass

        # 再答一次：只返回评价，不生成下一题，把节奏权交还给用户
        if not generate_next:
            return {
                "evaluation": evaluation,
                "is_complete": False,
                "next_question": None,
                "session_id": session_id,
            }

        # Generate next question
        next_difficulty = evaluation.get("next_difficulty", "medium")
        next_round = total_rounds + 1
        next_q = await self._generate_question(
            session_id, session["position"], next_round, next_difficulty, question["answer"], evaluation,
            match_analysis=None, resume_analysis=None, jd_analysis=None,
            followup=True,
        )

        return {
            "evaluation": evaluation,
            "is_complete": False,
            "next_question": next_q,
            "session_id": session_id,
        }

    def _decide_action(self, mode: str, total_answered: int, should_end: bool, last_evaluation: dict | None) -> str:
        """构建 PlannerContext 并让 Planner 决策下一动作（ask_question / generate_report）。"""
        ctx = PlannerContext(
            mode=mode,
            total_answered=total_answered,
            max_rounds=self.max_rounds,
            should_end=should_end,
            last_evaluation=last_evaluation,
            pending_evaluation=False,
        )
        return self.planner.decide(ctx)

    async def end(self, session_id: str, username: str | None = None) -> dict:
        """Force-end an interview and generate report."""
        session = self.store.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        self._authorize(session_id, username)
        report = await self._generate_report(session_id)
        self.store.complete_session(session_id, report)
        return {"session_id": session_id, "report": report}

    async def get_report(self, session_id: str, username: str | None = None) -> Optional[dict]:
        """Get interview report (read-only).

        仅返回已生成并落库的报告；不存在或会话未完成时返回 None，
        绝不在此处触发 LLM 生成，避免"查看"产生写副作用。
        """
        session = self.store.get_session(session_id)
        if not session:
            return None
        self._authorize(session_id, username)
        return session.get("report")

    def get_detail(self, session_id: str, username: str | None = None) -> Optional[dict]:
        """获取面试详情（纯读取）：会话元信息 + 逐题问答。

        不触发任何 LLM 调用、不改变会话状态。空归属（username=''）的记录
        与既有用户隔离逻辑一致，通过 _authorize 判定权限。
        """
        session = self.store.get_session(session_id)
        if not session:
            return None
        self._authorize(session_id, username)
        meta = {k: session.get(k) for k in (
            "id", "position", "status", "total_rounds", "total_score",
            "started_at", "completed_at",
        )}
        questions = self.store.get_questions(session_id)
        return {"session": meta, "questions": questions}

    def history(self, username: str | None = None, limit: int = 20) -> list[dict]:
        """List recent interview sessions (scoped to a user when provided)."""
        return self.store.list_sessions(limit=limit, username=username)

    def stats(self, username: str | None = None,
              exclude_sources: Optional[tuple[str, ...]] = None) -> dict:
        """跨场次知识点画像：聚合某用户所有已完成面试中各 topic/category 的得分。

        返回每个分类的题目数、平均分、薄弱子标题，用于复习页的"薄弱点画像"。
        按 username 过滤数据源，实现用户复习画像隔离。
        ``exclude_sources``（F9 冻结）：非空时过滤 source 命中该集合的问题行
        （agent 模式传 ("followup",)，默认 None 保持 legacy 行为不变）。
        """
        try:
            sessions = self.store.list_sessions(limit=100, username=username)
        except Exception as e:
            logger.warning(f"Failed to list sessions for stats: {e}")
            sessions = []

        category_map: dict[str, dict] = {}
        for s in sessions:
            if s.get("status") != "completed":
                continue
            try:
                questions = self.store.get_questions(s["id"])
            except Exception as e:
                logger.warning(f"Failed to load questions for session {s['id']}: {e}")
                continue
            for q in questions:
                if exclude_sources and q.get("source") in exclude_sources:
                    continue
                if q.get("answer") == "":
                    continue
                category = q.get("category") or "未分类"
                topic = q.get("topic") or "未指定"
                score = q.get("score") or 0
                cat = category_map.setdefault(category, {
                    "category": category,
                    "total_questions": 0,
                    "total_score": 0.0,
                    "topics": {},
                })
                cat["total_questions"] += 1
                cat["total_score"] += score
                topic_entry = cat["topics"].setdefault(topic, {"count": 0, "total_score": 0.0})
                topic_entry["count"] += 1
                topic_entry["total_score"] += score

        categories = []
        for cat in category_map.values():
            avg = round(cat["total_score"] / max(cat["total_questions"], 1), 1)
            weak_topics = [
                {
                    "topic": t,
                    "count": info["count"],
                    "avg_score": round(info["total_score"] / max(info["count"], 1), 1),
                }
                for t, info in cat["topics"].items()
                if (info["total_score"] / max(info["count"], 1)) < 6.0
            ]
            weak_topics.sort(key=lambda x: x["avg_score"])
            categories.append({
                "category": cat["category"],
                "total_questions": cat["total_questions"],
                "avg_score": avg,
                "weak_topics": weak_topics,
            })

        categories.sort(key=lambda c: (c["avg_score"], -c["total_questions"]))
        return {"categories": categories, "total_questions": sum(c["total_questions"] for c in categories)}

    async def today(self, username: str | None = None, position: str | None = None) -> dict:
        """今日一题：从某用户历史薄弱分类中选一个 topic，调用 LLM 生成一道复习题。

        若无历史数据，则按默认岗位随机出一题。该题独立于面试流程，不落库。
        岗位优先级：显式 position > 该用户最近一场面试的岗位 > 全局默认岗位。
        """
        # 解析岗位来源
        if not position:
            latest = self.store.list_sessions(limit=1, username=username)
            position = (latest[0].get("position") if latest and latest[0].get("position") else None) \
                or settings.default_interview_position

        stats = self.stats(username)
        weak_topics = []
        for cat in stats.get("categories", []):
            for t in cat.get("weak_topics", []):
                weak_topics.append({"category": cat["category"], **t})
        weak_topics.sort(key=lambda x: x["avg_score"])

        prompt = (
            "请出一道技术面试复习题。\n"
            f"岗位方向：{position}\n"
        )
        if weak_topics:
            target = weak_topics[0]
            prompt += (
                f"需要重点考察的领域：{target['category']} - {target['topic']}\n"
                f"该知识点历史平均得分 {target['avg_score']}/10，属于薄弱环节，请针对性出题。\n"
            )
        else:
            prompt += "请从该岗位的核心知识点中随机出题。\n"

        prompt += (
            "请以 JSON 格式返回，字段：question（题目内容）、topic（知识点名称）、"
            "category（分类）、difficulty（easy/medium/hard）、source（固定为 today）。"
        )

        try:
            text = await self.llm.chat(prompt)
            parsed = _parse_json(text)
        except Exception as e:
            logger.error(f"Today question generation failed: {e}")
            parsed = None

        if not parsed:
            return {"question": "今日复习题生成失败，请稍后再试。", "topic": "", "category": "", "difficulty": "medium"}

        return {
            "question": parsed.get("question", ""),
            "topic": parsed.get("topic", ""),
            "category": parsed.get("category", ""),
            "difficulty": parsed.get("difficulty", "medium"),
            "source": "today",
        }

    # --- Internal methods ---

    async def _generate_question(
        self,
        session_id: str,
        position: str,
        round_num: int,
        difficulty: str = "medium",
        last_answer: str = "",
        last_evaluation: Optional[dict] = None,
        match_analysis: Optional[dict] = None,
        resume_analysis: Optional[dict] = None,
        jd_analysis: Optional[dict] = None,
        followup: bool = False,
    ) -> dict:
        """Generate a question for the interview.

        followup=True 表示这是基于上一题回答的「追问式下一题」。按 Part B §5.2，
        追问环节默认不触发真实检索（enable_interview_followup_retrieval=False）。
        """
        # Get context from previous questions
        questions = self.store.get_questions(session_id)
        history_count = len(questions)
        difficulty_history = ", ".join([_difficulty_label(q.get("difficulty", "medium")) for q in questions]) or "暂无"
        last_eval_summary = ""
        if last_evaluation:
            last_eval_summary = f"得分：{last_evaluation.get('score', '?')}，评语：{last_evaluation.get('comment', '')[:50]}"

        # 追问默认不检索（Part B §5.2）；出题 / 开启开关时才走真实检索
        kb_context, kb_q_sources = "", []
        if not (followup and not self.followup_retrieval):
            kb_context, kb_q_sources = await self._retrieve_context_with_sources(
                f"{position} 技术面试题 {difficulty}"
            )

        # Build personalized context if match analysis is available
        personalized_context = ""
        if match_analysis and match_analysis.get("matched_skills"):
            jd_summary = jd_analysis.get("summary", "") if jd_analysis else ""
            resume_summary = resume_analysis.get("summary", "") if resume_analysis else ""
            missing = ", ".join(match_analysis.get("missing_skills", []))
            matched = ", ".join(match_analysis.get("matched_skills", []))
            risk = ", ".join(match_analysis.get("risk_areas", []))
            focus = match_analysis.get("interview_focus", "")

            personalized_context = f"""
【简历与JD匹配分析】
岗位要求：{jd_summary}
候选人背景：{resume_summary}
已匹配技能：{matched}
技能缺口：{missing}
高风险追问方向：{risk}
面试重点：{focus}

请基于以上分析，针对候选人的简历短板和岗位核心要求出题。
"""

        # --- Knowledge tree integration ---
        coverage_text = ""
        tree_text = ""
        suggestion_text = ""
        suggested_category = ""
        if self.topic_tracker:
            tree = self.topic_tracker.get_tree(position)
            if tree:
                coverage_text = self.topic_tracker.get_coverage_summary_text(session_id, position)
                tree_text = self.topic_tracker.get_tree_structure_text(position)
                suggestion = self.topic_tracker.get_next_suggestion(session_id, position)
                if suggestion.get("topic"):
                    suggested_category = suggestion.get("category", "")
                    suggestion_text = (
                        f"建议优先出题方向：{suggested_category} - {suggestion['topic']}\n"
                        f"原因：{suggestion['reason']}"
                    )

        prompt = QUESTION_PROMPT.format(
            position=position,
            round=round_num,
            history_count=history_count,
            difficulty_history=difficulty_history,
            last_evaluation_summary=last_eval_summary,
            knowledge_context=kb_context + personalized_context,
            难度提示=_difficulty_label(difficulty),
            coverage_summary=coverage_text,
            knowledge_tree_structure=tree_text,
            suggested_topic=suggestion_text,
            suggested_category=suggested_category,
        )

        text = await self.llm.chat(prompt, SYSTEM_START)
        parsed = _parse_json(text)
        if not parsed:
            logger.warning(f"Failed to parse question JSON, using fallback. Raw: {text[:200]}")
            parsed = {
                "question": text[:200] if len(text) > 200 else text,
                "difficulty": difficulty,
                "source": "llm",
                "knowledge_tags": [],
                "topic": "",
                "category": "",
            }

        question_text = parsed.get("question", text[:200])
        q_difficulty = parsed.get("difficulty", difficulty)
        q_source = parsed.get("source", "llm")
        knowledge_tags = parsed.get("knowledge_tags", [])
        q_topic = parsed.get("topic", "") or ""
        q_category = parsed.get("category", "") or ""

        # Store the question
        q = self.store.add_question(
            session_id, round_num, question_text, q_difficulty, q_source,
            topic=q_topic, category=q_category,
        )

        return {
            "id": q["id"],
            "content": question_text,
            "round": round_num,
            "difficulty": q_difficulty,
            "source": q_source,
            "knowledge_tags": knowledge_tags,
            "topic": q_topic,
            "category": q_category,
            "sources": kb_q_sources,  # 溯源（Part B §5.5）：出题所用检索来源
        }

    async def _retrieve_context(self, query: str) -> str:
        """Retrieve knowledge base context for a query (老签名，只返回文本)。"""
        text, _ = await self._retrieve_context_with_sources(query)
        return text

    async def _retrieve_context_with_sources(self, query: str) -> tuple[str, list]:
        """统一检索上下文 + 来源（Part B S3）。

        优先走 RetrievalFacade（hybrid + rerank 已验证管线），facade 不可用或索引缺失时
        降级到旧 raw FAISS 链路（DR-001：检索失败不得阻塞面试主线）。返回 (context_text, sources)。
        """
        # 1) 优先 facade
        if self.facade is not None:
            try:
                result = await self.facade.retrieve(query, top_k=5)
                if not result.is_empty:
                    text = f"以下是从知识库检索到的参考资料：\n" + result.to_text()
                    sources = [
                        {"file": s.file, "chunk_index": s.chunk_index, "score": s.score}
                        for s in result.sources
                    ]
                    return text, sources
            except Exception as e:
                logger.warning(f"Facade retrieval failed, fallback to raw faiss: {e}")

        # 2) 降级：旧 raw FAISS 逻辑（行为保持升级前一致）
        if not self.faiss or not self.faiss.is_loaded() or not self.embedding:
            return "", []
        try:
            query_vector = await self.embedding.encode([query])
            if query_vector.size == 0:
                return "", []
            results = self.faiss.search(query_vector[0], 3)
            if not results:
                return "", []
            seen = set()
            chunks = []
            sources = []
            for r in results:
                if r.content not in seen:
                    seen.add(r.content)
                    chunks.append(r.content)
                    sources.append({"file": r.source_file, "chunk_index": r.chunk_index, "score": r.score})
            if chunks:
                text = f"以下是从知识库检索到的参考资料：\n" + "\n---\n".join(chunks)
                return text, sources
        except Exception as e:
            logger.warning(f"Knowledge retrieval failed: {e}")
        return "", []

    async def _generate_report(self, session_id: str) -> dict:
        """Generate an interview report from all questions and answers."""
        session = self.store.get_session(session_id)
        questions = self.store.get_questions(session_id)

        if not session or not questions:
            return {"total_score": 0, "level": "未知", "improvement_suggestions": ["无足够数据"]}

        total_score = 0
        q_details = []
        for q in questions:
            score = q.get("score", 0) or 0
            total_score += score
            eval_data = q.get("evaluation") or {}
            tags = eval_data.get("tags", [])
            q_details.append({
                "round": q["round"],
                # 报告携带完整题目，不再截断，保证可独立复盘
                "question": q["question"],
                "score": score,
                "tags": tags,
                "comment": eval_data.get("comment", ""),
                "score_reason": eval_data.get("score_reason", ""),
                "reference_answer": eval_data.get("reference_answer", ""),
                "topic": q.get("topic", "") or "",
                "category": q.get("category", "") or "",
            })

        avg_score = round(total_score / len(questions), 1)

        prompt = REPORT_PROMPT.format(
            position=session["position"],
            total_rounds=len(questions),
            total_score=avg_score,
            questions_detail=json.dumps(q_details, ensure_ascii=False, indent=2),
        )

        text = await self.llm.chat(prompt)
        parsed = _parse_json(text)

        # --- Topic analysis (no LLM needed) ---
        topic_analysis = []
        category_scores = {}
        for q in q_details:
            cat = q.get("category", "") or "其他"
            if cat not in category_scores:
                category_scores[cat] = {"scores": [], "topics": set()}
            category_scores[cat]["scores"].append(q["score"])
            if q.get("topic"):
                category_scores[cat]["topics"].add(q["topic"])

        for cat_name, data in category_scores.items():
            avg = round(sum(data["scores"]) / len(data["scores"]), 1)
            if avg >= 7:
                status = "strong"
            elif avg >= 5:
                status = "moderate"
            else:
                status = "weak"
            topic_analysis.append({
                "category": cat_name,
                "topics_covered": len(data["topics"]),
                "avg_score": avg,
                "status": status,
            })

        if parsed:
            parsed["total_score"] = avg_score
            parsed["topic_analysis"] = topic_analysis

            # 用本地真实数据校正 score_breakdown：保证完整题目、真实评分原因与参考答案，
            # 避免 LLM 截断题目或遗漏新字段
            detail_by_round = {d["round"]: d for d in q_details}
            llm_breakdown = parsed.get("score_breakdown") or []
            corrected = []
            for item in llm_breakdown:
                local = detail_by_round.get(item.get("round"))
                merged = dict(item)
                if local:
                    for key in ("question", "score", "tags", "comment", "score_reason", "reference_answer", "topic", "category"):
                        if local.get(key):
                            merged[key] = local[key]
                corrected.append(merged)
            # 补充 LLM 遗漏的题目
            seen_rounds = {item.get("round") for item in corrected if item.get("round")}
            for d in q_details:
                if d["round"] not in seen_rounds:
                    corrected.append(d)
            parsed["score_breakdown"] = corrected

            # Generate recommended_study from topic_analysis
            recommended = []
            for ta in topic_analysis:
                if ta["status"] == "weak":
                    recommended.append({
                        "category": ta["category"],
                        "priority": "high",
                        "reason": f"得分偏低（{ta['avg_score']}分），建议重点复习",
                    })
                elif ta["status"] == "moderate":
                    recommended.append({
                        "category": ta["category"],
                        "priority": "medium",
                        "reason": f"基础尚可（{ta['avg_score']}分），建议补充深度",
                    })
            parsed["recommended_study"] = recommended
            return parsed

        # Fallback report
        return {
            "total_score": avg_score,
            "score_breakdown": q_details,
            "knowledge_analysis": {"strengths": [], "weaknesses": []},
            "improvement_suggestions": ["报告生成失败，请重试"],
            "level": "中级" if avg_score >= 6 else "初级",
            "topic_analysis": topic_analysis,
        }