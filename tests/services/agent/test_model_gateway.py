"""W2 上：model_gateway 单元测试（impl-spec v2 附录 E5；JD1-7）。

先于实现编写（TDD）。覆盖：
- light → qwen-turbo
- heavy → qwen-plus
- heavy plus 失败 → 降级 turbo（retries 计数）
- light 无降级链（turbo 即链底）
- 链路全失败 → LLMAPIError
- cost/model 记录（model 正确、cost 占位、延迟记录）
- 不绕过 LLMClient（BailianAdapter 只调 llm.chat(model=...)）
- 接线：build_agent_service + 完整流 → questioner/followuper 走 light(turbo)、evaluator 走 heavy(plus)
"""

import pytest

from app.exceptions import LLMAPIError
from app.services.agent.model_gateway import (
    LEVEL_HEAVY,
    LEVEL_LIGHT,
    BailianAdapter,
    GenerationResult,
    ModelGateway,
    TaskSpec,
)


class FakeAdapter:
    """记录调用的适配器；fail_models 中的模型调用抛 LLMAPIError。"""

    def __init__(self, fail_models=()):
        self.calls = []
        self.fail_models = set(fail_models)

    async def chat(self, prompt, system=None, session_id=None, model=None):
        self.calls.append({"model": model, "prompt": prompt, "system": system, "session_id": session_id})
        if model in self.fail_models:
            raise LLMAPIError(f"model {model} failed")
        return f"reply:{model}"


@pytest.mark.asyncio
async def test_light_uses_turbo():
    a = FakeAdapter()
    g = ModelGateway(None, adapter=a)
    r = await g.generate(TaskSpec(role_level=LEVEL_LIGHT, prompt="p"))
    assert r.model == "qwen-turbo"
    assert r.text == "reply:qwen-turbo"
    assert a.calls[0]["model"] == "qwen-turbo"


@pytest.mark.asyncio
async def test_heavy_uses_plus():
    a = FakeAdapter()
    g = ModelGateway(None, adapter=a)
    r = await g.generate(TaskSpec(role_level=LEVEL_HEAVY, prompt="p"))
    assert r.model == "qwen-plus"


@pytest.mark.asyncio
async def test_heavy_plus_failure_falls_back_to_turbo():
    a = FakeAdapter(fail_models={"qwen-plus"})
    g = ModelGateway(None, adapter=a)
    r = await g.generate(TaskSpec(role_level=LEVEL_HEAVY, prompt="p"))
    assert r.model == "qwen-turbo"
    assert r.retries == 1  # 降级 1 次
    assert r.text == "reply:qwen-turbo"
    assert [c["model"] for c in a.calls] == ["qwen-plus", "qwen-turbo"]


@pytest.mark.asyncio
async def test_light_has_no_fallback_chain():
    a = FakeAdapter(fail_models={"qwen-turbo"})
    g = ModelGateway(None, adapter=a)
    with pytest.raises(LLMAPIError):
        await g.generate(TaskSpec(role_level=LEVEL_LIGHT, prompt="p"))
    assert len(a.calls) == 1  # turbo 即链底，不重试


@pytest.mark.asyncio
async def test_chain_exhausted_raises():
    a = FakeAdapter(fail_models={"qwen-plus", "qwen-turbo"})
    g = ModelGateway(None, adapter=a)
    with pytest.raises(LLMAPIError):
        await g.generate(TaskSpec(role_level=LEVEL_HEAVY, prompt="p"))


@pytest.mark.asyncio
async def test_cost_and_model_recorded():
    a = FakeAdapter()
    g = ModelGateway(None, adapter=a)
    r = await g.generate(TaskSpec(role_level=LEVEL_HEAVY, prompt="p"))
    assert isinstance(r, GenerationResult)
    assert r.model == "qwen-plus"
    assert r.latency_ms >= 0
    assert r.cost == 0.0  # 成本由 monitor/session_cost 记录（LLMClient 内），网关不重复计算


@pytest.mark.asyncio
async def test_bailian_adapter_forwards_model_to_llmclient():
    """不绕过 LLMClient：BailianAdapter 只调 llm.chat(..., model=...)。"""

    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, prompt, system=None, session_id=None, model=None):
            self.calls.append({"prompt": prompt, "system": system, "session_id": session_id, "model": model})
            return "x"

    llm = FakeLLM()
    adapter = BailianAdapter(llm)
    await adapter.chat("p", system="s", session_id="sid", model="qwen-plus")
    assert llm.calls == [{"prompt": "p", "system": "s", "session_id": "sid", "model": "qwen-plus"}]


@pytest.mark.asyncio
async def test_gateway_through_bailian_adapter_uses_llmclient():
    """gateway → BailianAdapter → LLMClient.chat（无第二套 HTTP 请求逻辑）。"""

    class FakeLLM:
        def __init__(self):
            self.calls = []

        async def chat(self, prompt, system=None, session_id=None, model=None):
            self.calls.append(model)
            return f"ok:{model}"

    llm = FakeLLM()
    g = ModelGateway(llm)  # 默认 BailianAdapter(llm)
    r = await g.generate(TaskSpec(role_level=LEVEL_LIGHT, prompt="p"))
    assert r.model == "qwen-turbo"
    assert llm.calls == ["qwen-turbo"]


@pytest.mark.asyncio
async def test_agent_wiring_light_heavy_roles(env_dir):
    """接线集成：完整 agent 流中，出题/追问走 light(turbo)、评估走 heavy(plus)。"""
    from app.services.agent.agent_service import build_agent_service
    from app.services.agent.state_machine import EscapeHatchConfig
    from app.services.topic_tracker import TopicTracker
    from app.storage.interview_store import InterviewStore
    from tests.services.agent._helpers import make_llm

    class Recorder:
        def __init__(self):
            self.models = []
            self._inner = make_llm()

        async def chat(self, prompt, system=None, session_id=None, model=None):
            self.models.append(model)
            return await self._inner(prompt, system)

    store = InterviewStore(db_path=str(env_dir / "gw.db"))
    llm = Recorder()
    tracker = TopicTracker(interview_store=store, tree_dir=str(env_dir))
    svc = build_agent_service(
        store=store, llm=llm, facade=None, topic_tracker=tracker,
        trace_dir=str(env_dir / "traces"),
        escape_config=EscapeHatchConfig(max_rounds=2),
        light_model="qwen-turbo", heavy_model="qwen-plus",
    )
    res = await svc.start("Java后端", username="u1")
    await svc.answer(res["question"]["id"], "短答触发追问", username="u1")
    # questioner / followuper → light；evaluator → heavy
    assert "qwen-turbo" in llm.models
    assert "qwen-plus" in llm.models
