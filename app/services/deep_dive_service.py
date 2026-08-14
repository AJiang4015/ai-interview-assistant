# app/services/deep_dive_service.py
import json
import re

from app.storage.deep_dive_store import DeepDiveStore
from app.utils.logger import get_logger

logger = get_logger(__name__)

MAX_DEPTH = 5

SYSTEM_MEAN = (
    "你是一名极其严格、喜欢刨根问底的资深技术面试官。"
    "你的风格是：抓住候选人回答中每一个技术断言，连续追问，逼迫其讲清原理、必要性与边界。"
    "追问要单刀直入、一针见血，但语气专业克制，不进行人身攻击。"
    "你只问一个问题，不解释答案。"
)

FIRST_ASK_PROMPT = """候选人简历中有一个项目：{project_name}
技术点：{tech_points}
项目描述：{description}

你作为严格的面试官，针对这个项目和技术点，抛出第一个尖锐问题，要求候选人解释"为什么这么选/怎么实现"。
请以 JSON 输出：{{"question": "问题内容"}}
"""

FOLLOW_UP_PROMPT = """候选人正在接受你的项目深挖追问。
技术点：{tech_point}
项目：{project_name}
此前追问链：
{history}

候选人对上一个问题的回答是：{answer}

请针对这个回答，只问一个更深入或更尖锐的追问（质疑其选择、要求原理、升级规模、考察边界）。
请以 JSON 输出：{{"question": "追问内容"}}
"""

JUDGE_PROMPT = """判断候选人回答的质量，并决定是否继续追问。

问题：{question}
候选人的回答：{answer}

请以 JSON 输出：
{{
    "score": <1-10 整数>,
    "judgment": "一句话点评（指出候选人暴露的薄弱点）",
    "can_answer": <true/false，false 表示答不上来或明显错误>
}}
"""

SUMMARY_PROMPT = """请根据本次项目深挖的完整追问链，生成一份总结。
追问链：
{history}

请以 JSON 输出：
{{
    "weaknesses": ["候选人暴露的薄弱点1", "薄弱点2"],
    "key_points": ["该技术点应掌握的核心要点1", "要点2"],
    "overall": "整体评价（60字内）"
}}
"""


def _parse_json(text: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


class DeepDiveService:
    def __init__(self, store: DeepDiveStore, llm):
        self.store = store
        self.llm = llm

    def extract_projects(self, resume_analysis: dict) -> list[dict]:
        """从简历解析结果中提取项目及技术点。"""
        projects = resume_analysis.get("projects") or []
        out = []
        for p in projects:
            out.append({
                "name": p.get("name", "未命名项目"),
                "description": p.get("description", ""),
                "technologies": p.get("technologies") or [],
            })
        return out

    async def start(self, project_name: str, tech_point: str, description: str = "") -> dict:
        session = self.store.create_session(project_name, tech_point, description)
        prompt = FIRST_ASK_PROMPT.format(
            project_name=project_name, tech_points=tech_point, description=description)
        try:
            text = await self.llm.chat(prompt, SYSTEM_MEAN)
            parsed = _parse_json(text) or {"question": f"请先解释一下你在项目 {project_name} 中使用 {tech_point} 的动机。"}
        except Exception as e:
            logger.warning("Deep dive first_ask LLM call failed: %s", e)
            parsed = {"question": f"请先解释一下你在项目 {project_name} 中使用 {tech_point} 的动机。"}
        q = self.store.add_question(session["id"], 1, parsed["question"])
        return {"session_id": session["id"], "question": self._qdict(q)}

    async def answer(self, question_id: str, answer: str, action: str = "continue") -> dict:
        session = self.store.get_session_by_question(question_id)
        if session is None:
            raise ValueError(f"Question not found: {question_id}")
        questions = self.store.get_questions(session["id"])
        current = next(q for q in questions if q["id"] == question_id)

        try:
            judge_text = await self.llm.chat(
                JUDGE_PROMPT.format(question=current["question"], answer=answer), SYSTEM_MEAN)
            judge = _parse_json(judge_text) or {"score": 5, "judgment": "", "can_answer": True}
        except Exception as e:
            logger.warning("Deep dive judge LLM call failed: %s", e)
            judge = {"score": 5, "judgment": "", "can_answer": True}
        self.store.update_answer(question_id, answer, judge.get("score", 5), judge)

        questions = self.store.get_questions(session["id"])
        answered = [q for q in questions if q["answer"]]
        depth = len(answered)
        if action == "end" or depth >= MAX_DEPTH or not judge.get("can_answer", True):
            summary = await self._generate_summary(session["id"])
            return {"is_complete": True, "judgment": judge, "summary": summary}

        try:
            follow_text = await self.llm.chat(
                FOLLOW_UP_PROMPT.format(
                    tech_point=session["tech_point"], project_name=session["project_name"],
                    history=self._fmt_history(questions), answer=answer),
                SYSTEM_MEAN)
            follow = _parse_json(follow_text) or {"question": "再说得具体一点，你当时是怎么实现的？"}
        except Exception as e:
            logger.warning("Deep dive follow_up LLM call failed: %s", e)
            follow = {"question": "再说得具体一点，你当时是怎么实现的？"}
        nq = self.store.add_question(session["id"], depth + 1, follow["question"])
        return {"is_complete": False, "judgment": judge, "next_question": self._qdict(nq)}

    async def end(self, session_id: str) -> dict:
        summary = await self._generate_summary(session_id)
        return {"summary": summary}

    async def _generate_summary(self, session_id: str) -> dict:
        questions = self.store.get_questions(session_id)
        history = "\n".join(f"Q: {q['question']}\nA: {q['answer']}" for q in questions)
        try:
            text = await self.llm.chat(SUMMARY_PROMPT.format(history=history))
            parsed = _parse_json(text) or {"weaknesses": [], "key_points": [], "overall": "深挖结束。"}
        except Exception as e:
            logger.warning("Deep dive summary LLM call failed: %s", e)
            parsed = {"weaknesses": [], "key_points": [], "overall": "深挖结束。"}
        self.store.complete_session(session_id, json.dumps(parsed, ensure_ascii=False))
        return parsed

    @staticmethod
    def _qdict(q) -> dict:
        return {"id": q["id"], "question": q["question"], "round": q["round"]}

    @staticmethod
    def _fmt_history(questions) -> str:
        return "\n".join(f"Q: {q['question']}\nA: {q['answer']}" for q in questions if q["answer"])