"""AgentService facade（impl-spec v2 附录 E1；OPEN-1/F9 冻结）。

- **镜像 legacy InterviewService 完整 public surface**：start/answer/end/get_report/
  get_detail/history/stats/today + `store`/`topic_tracker` 属性（API coverage 端点直接访问）。
- 职责归属（F9）：start/answer/end = Agent 核心（经 orchestrator）；get_report/get_detail/
  history = 直读 store（无业务复制）；stats/today = **委托 legacy 只读实例**（stats 传
  exclude_sources=("followup",)，F9）。
- `AgentTopicTracker`：get_coverage 默认过滤 followup（API coverage 端点不传参，F9 冻结）。
- `build_agent_service`：app.main 装配工厂（显式 DI，不 import settings，保持可测）。
"""

from __future__ import annotations

from typing import Optional

from app.exceptions import AuthorizationError
from app.services.agent.orchestrator import AgentOrchestrator
from app.services.agent.profile_store import ProfileStore, SessionProfileStore
from app.services.agent.state_machine import EscapeHatch, EscapeHatchConfig, StateMachine
from app.services.agent.tools import ToolRegistry, build_default_tools
from app.services.topic_tracker import TopicTracker
from app.storage.interview_store import InterviewStore


class AgentTopicTracker(TopicTracker):
    """coverage 默认过滤 followup（F9：API coverage 端点直接调用 get_coverage 不传参）。"""

    def get_coverage(
        self,
        session_id: str,
        position: str,
        exclude_sources: tuple[str, ...] = ("followup",),
    ) -> dict:
        return super().get_coverage(session_id, position, exclude_sources=exclude_sources)


class AgentService:
    """legacy InterviewService 的替代实现（agent 模式，API/前端零改动）。"""

    def __init__(
        self,
        *,
        orchestrator: AgentOrchestrator,
        store: InterviewStore,
        topic_tracker: TopicTracker,
        legacy_readonly: Optional[object] = None,
        resume_parser: Optional[object] = None,
        facade: Optional[object] = None,
    ):
        self.orchestrator = orchestrator
        self.store = store
        self.topic_tracker = topic_tracker
        self._legacy_readonly = legacy_readonly
        self.resume_parser = resume_parser
        self.facade = facade

    # ---------------------------------------------------------------- 核心（Agent 编排）

    async def start(
        self,
        position: str,
        username: str = "",
        resume_file=None,
        jd_text: Optional[str] = None,
    ) -> dict:
        """与 legacy start 同签名（multipart：可选 resume/JD）。resume/JD 解析复用存量 ResumeParser。"""
        personalized = ""
        if resume_file and self.resume_parser:
            try:
                resume_raw = await self.resume_parser.extract_pdf_text(resume_file)
                if resume_raw:
                    resume_analysis = await self.resume_parser.parse_resume(resume_raw)
                    if resume_analysis.get("summary"):
                        personalized += f"候选人背景：{resume_analysis['summary']}\n"
            except Exception:
                pass  # 简历解析失败不阻塞面试（与 legacy 行为一致）
        if jd_text and self.resume_parser:
            try:
                jd_analysis = await self.resume_parser.parse_jd(jd_text)
                if jd_analysis.get("summary"):
                    personalized += f"岗位要求：{jd_analysis['summary']}\n"
            except Exception:
                pass
        return await self.orchestrator.start(position, username=username, personalized_context=personalized)

    async def answer(
        self,
        question_id: str,
        answer: str,
        generate_next: bool = True,
        username: Optional[str] = None,
    ) -> dict:
        """与 legacy answer 同签名（按 question_id）。"""
        if username is not None:
            row = self.store.get_question(question_id)
            if row is None:
                raise ValueError(f"Question not found: {question_id}")
            self._authorize(row["session_id"], username)
        return await self.orchestrator.submit_answer(
            question_id, answer, generate_next=generate_next, user_id=username or "",
        )

    async def end(self, session_id: str, username: Optional[str] = None) -> dict:
        self._authorize(session_id, username)
        return await self.orchestrator.end(session_id, user_id=username or "")

    # ---------------------------------------------------------------- 只读（直读 store / 委托 legacy）

    async def get_report(self, session_id: str, username: Optional[str] = None) -> Optional[dict]:
        """只读，不触发 LLM（与 legacy 语义一致）。"""
        session = self.store.get_session(session_id)
        if not session:
            return None
        self._authorize(session_id, username)
        return session.get("report")

    def get_detail(self, session_id: str, username: Optional[str] = None) -> Optional[dict]:
        """纯读取：会话元信息 + 逐题问答（legacy 形状）。"""
        session = self.store.get_session(session_id)
        if not session:
            return None
        self._authorize(session_id, username)
        meta = {k: session.get(k) for k in (
            "id", "position", "status", "total_rounds", "total_score",
            "started_at", "completed_at",
        )}
        return {"session": meta, "questions": self.store.get_questions(session_id)}

    def history(self, username: Optional[str] = None, limit: int = 20) -> list[dict]:
        return self.store.list_sessions(limit=limit, username=username)

    def stats(self, username: Optional[str] = None) -> dict:
        """委托 legacy（F9：exclude_sources=("followup",)，追问不污染薄弱点画像）。"""
        if self._legacy_readonly is None:
            return {"categories": [], "total_questions": 0}
        return self._legacy_readonly.stats(username=username, exclude_sources=("followup",))

    async def today(self, username: Optional[str] = None, position: Optional[str] = None) -> dict:
        """独立产品功能（今日一题），委托 legacy。"""
        if self._legacy_readonly is None:
            raise ValueError("legacy readonly service not injected")
        return await self._legacy_readonly.today(username=username, position=position)

    def _authorize(self, session_id: str, username: Optional[str]) -> None:
        if username is None:
            return
        if not self.store.owns_session(session_id, username):
            raise AuthorizationError("无权访问该面试场次")


def build_agent_service(
    *,
    store: InterviewStore,
    llm: object,
    facade: object,
    topic_tracker: TopicTracker,
    resume_parser: Optional[object] = None,
    legacy_readonly: Optional[object] = None,
    profile_store: Optional[ProfileStore] = None,
    trace_dir: str = "data/traces",
    trace_retention: int = 200,
    escape_config: Optional[EscapeHatchConfig] = None,
    followup_enabled: Optional[bool] = None,
    max_followup_depth: Optional[int] = None,
    max_answer_chars: Optional[int] = None,
    light_model: str = "qwen-turbo",
    heavy_model: str = "qwen-plus",
    use_gateway: bool = True,
) -> AgentService:
    """app.main 装配工厂（agent 模式）：显式 DI 组装 orchestrator + tools + service。

    本工厂不 import settings（保持可测）；settings 值由调用方（app.main）传入。
    ``use_gateway=True``（默认，spec E5）：经 ModelGateway 分级调用
    （light→turbo / heavy→plus / plus→turbo 降级），仍通过 LLMClient，无第二套 HTTP。
    """
    profile_store = profile_store or SessionProfileStore()
    agent_tracker = AgentTopicTracker(interview_store=store)

    tools = build_default_tools(facade=facade, topic_tracker=agent_tracker, profile_store=profile_store)
    registry = ToolRegistry()
    for tool in tools.values():
        registry.register(tool)

    escape = EscapeHatch(escape_config or EscapeHatchConfig())

    if use_gateway:
        from app.services.agent.model_gateway import LEVEL_HEAVY, LEVEL_LIGHT, ModelGateway, TaskSpec

        gateway = ModelGateway(llm, light_model=light_model, heavy_model=heavy_model)

        async def llm_call(prompt: str, system: Optional[str] = None) -> str:
            result = await gateway.generate(TaskSpec(role_level=LEVEL_HEAVY, prompt=prompt, system=system))
            return result.text

        async def llm_call_light(prompt: str, system: Optional[str] = None) -> str:
            result = await gateway.generate(TaskSpec(role_level=LEVEL_LIGHT, prompt=prompt, system=system))
            return result.text
    else:

        async def llm_call(prompt: str, system: Optional[str] = None) -> str:
            return await llm.chat(prompt, system=system)  # type: ignore[attr-defined]

        llm_call_light = None

    orchestrator = AgentOrchestrator(
        machine=StateMachine(),
        tools=registry,
        store=store,
        llm_call=llm_call,
        llm_call_light=llm_call_light,
        escape_hatch=escape,
        trace_dir=trace_dir,
        trace_retention=trace_retention,
        profile_store=profile_store,
        followup_enabled=True if followup_enabled is None else followup_enabled,
        max_followup_depth=1 if max_followup_depth is None else max_followup_depth,
        max_answer_chars=2000 if max_answer_chars is None else max_answer_chars,
    )
    return AgentService(
        orchestrator=orchestrator,
        store=store,
        topic_tracker=agent_tracker,
        legacy_readonly=legacy_readonly,
        resume_parser=resume_parser,
        facade=facade,
    )
