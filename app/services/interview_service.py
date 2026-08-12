"""Interview service for AI-driven interview flow.

Generates questions, evaluates answers, and produces reports
using the LLM client, optionally backed by knowledge base retrieval.
"""

import json
import re
from typing import Optional

from app.services.llm_client import LLMClient
from app.storage.faiss_store import FaissStore
from app.services.embedding import EmbeddingService
from app.storage.interview_store import InterviewStore
from app.utils.logger import get_logger

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

请出一道{难度提示}技术面试题，混合技术知识点、项目经验或系统设计方向。
题目应该是面试中常见的高质量题目。

请按以下 JSON 格式输出（不要包含其他内容）：
{{
    "question": "题目内容",
    "difficulty": "easy/medium/hard",
    "source": "kb/llm",
    "knowledge_tags": ["知识点标签1", "知识点标签2"]
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
    "comment": "评价内容（指出优点和不足，约 50-100 字）",
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
        {{"round": 1, "question": "题目概要", "score": 7, "tags": ["知识点1"]}}
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
    ):
        self.store = store
        self.llm = llm
        self.faiss = faiss
        self.embedding = embedding
        self.max_rounds = 15
        self.min_rounds = 5

    async def start(self, position: str) -> dict:
        """Start a new interview session and generate the first question."""
        session = self.store.create_session(position)
        question_data = await self._generate_question(session["id"], position, round_num=1)
        return {
            "session_id": session["id"],
            "question": question_data,
        }

    async def answer(self, question_id: str, answer: str) -> dict:
        """Submit an answer, get evaluation and optionally next question."""
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

        # Evaluate the answer
        kb_context = await self._retrieve_context(question["question"] + " " + answer)
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
            "tags": ["未知"],
            "next_difficulty": "medium",
            "should_end": False,
        }

        score = evaluation.get("score", 5)
        self.store.update_answer(question_id, answer, evaluation, score)

        # Check if interview should end
        should_end = evaluation.get("should_end", False)
        total_rounds = session["total_rounds"] or 0

        if should_end or total_rounds >= self.max_rounds:
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

        # Generate next question
        next_difficulty = evaluation.get("next_difficulty", "medium")
        next_round = total_rounds + 1
        next_q = await self._generate_question(
            session_id, session["position"], next_round, next_difficulty, question["answer"], evaluation
        )

        return {
            "evaluation": evaluation,
            "is_complete": False,
            "next_question": next_q,
            "session_id": session_id,
        }

    async def end(self, session_id: str) -> dict:
        """Force-end an interview and generate report."""
        session = self.store.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        report = await self._generate_report(session_id)
        self.store.complete_session(session_id, report)
        return {"session_id": session_id, "report": report}

    async def get_report(self, session_id: str) -> Optional[dict]:
        """Get interview report."""
        session = self.store.get_session(session_id)
        if not session:
            return None
        if session.get("report"):
            return session["report"]
        # Generate report if not yet generated
        report = await self._generate_report(session_id)
        self.store.complete_session(session_id, report)
        return report

    def history(self) -> list[dict]:
        """List recent interview sessions."""
        return self.store.list_sessions()

    # --- Internal methods ---

    async def _generate_question(
        self,
        session_id: str,
        position: str,
        round_num: int,
        difficulty: str = "medium",
        last_answer: str = "",
        last_evaluation: Optional[dict] = None,
    ) -> dict:
        """Generate a question for the interview."""
        # Get context from previous questions
        questions = self.store.get_questions(session_id)
        history_count = len(questions)
        difficulty_history = ", ".join([_difficulty_label(q.get("difficulty", "medium")) for q in questions]) or "暂无"
        last_eval_summary = ""
        if last_evaluation:
            last_eval_summary = f"得分：{last_evaluation.get('score', '?')}，评语：{last_evaluation.get('comment', '')[:50]}"

        # Retrieve knowledge base context
        kb_context = await self._retrieve_context(f"{position} 技术面试题 {difficulty}")

        prompt = QUESTION_PROMPT.format(
            position=position,
            round=round_num,
            history_count=history_count,
            difficulty_history=difficulty_history,
            last_evaluation_summary=last_eval_summary,
            knowledge_context=kb_context,
            难度提示=_difficulty_label(difficulty),
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
            }

        question_text = parsed.get("question", text[:200])
        q_difficulty = parsed.get("difficulty", difficulty)
        q_source = parsed.get("source", "llm")
        knowledge_tags = parsed.get("knowledge_tags", [])

        # Store the question
        q = self.store.add_question(session_id, round_num, question_text, q_difficulty, q_source)

        return {
            "id": q["id"],
            "content": question_text,
            "round": round_num,
            "difficulty": q_difficulty,
            "source": q_source,
            "knowledge_tags": knowledge_tags,
        }

    async def _retrieve_context(self, query: str) -> str:
        """Retrieve knowledge base context for a query."""
        if not self.faiss or not self.faiss.is_loaded() or not self.embedding:
            return ""

        try:
            query_vector = await self.embedding.encode([query])
            if query_vector.size == 0:
                return ""
            results = self.faiss.search(query_vector[0], 3)
            if not results:
                return ""
            # Deduplicate
            seen = set()
            chunks = []
            for r in results:
                if r.content not in seen:
                    seen.add(r.content)
                    chunks.append(r.content)
            if chunks:
                return f"以下是从知识库检索到的参考资料：\n" + "\n---\n".join(chunks)
        except Exception as e:
            logger.warning(f"Knowledge retrieval failed: {e}")
        return ""

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
            tags = []
            if q.get("evaluation"):
                tags = q["evaluation"].get("tags", [])
            q_details.append({
                "round": q["round"],
                "question": q["question"][:80],
                "score": score,
                "tags": tags,
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
        if parsed:
            parsed["total_score"] = avg_score
            return parsed

        # Fallback report
        return {
            "total_score": avg_score,
            "score_breakdown": q_details,
            "knowledge_analysis": {"strengths": [], "weaknesses": []},
            "improvement_suggestions": ["报告生成失败，请重试"],
            "level": "中级" if avg_score >= 6 else "初级",
        }