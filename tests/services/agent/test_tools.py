"""W1 Day 3：Tool 层单元测试（impl-spec v2 附录 F）。

先于实现编写（TDD）。覆盖：
- ToolRegistry：register 幂等 / get / list / has / 未注册异常
- input_schema / output_schema 校验（缺参/类型错/多余字段/非法输出）
- timeout（degrade→ToolTimeoutError；abort→ToolAbortError）
- error_policy（degrade→ToolExecutionError；abort→ToolAbortError）
- 六个内置 tool：正常路径 + 失败路径（mock 外部依赖）
"""

from types import SimpleNamespace

import pytest

from app.services.agent.tools import (
    Tool,
    ToolAbortError,
    ToolError,
    ToolExecutionError,
    ToolInputError,
    ToolNotFoundError,
    ToolOutputError,
    ToolRegistry,
    ToolTimeoutError,
    build_default_tools,
    make_eval_rules_tool,
    make_get_profile_tool,
    make_kb_retrieve_tool,
    make_mock_resume_tool,
    make_pick_next_topic_tool,
    make_update_profile_tool,
)


def _tool(name="t1", handler=None, timeout=1.0, error_policy="degrade", input_schema=None, output_schema=None):
    async def _default_handler(**kw):
        return {"y": kw.get("x", 0)}

    return Tool(
        name=name,
        description=f"desc {name}",
        input_schema=input_schema or {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"], "additionalProperties": False},
        output_schema=output_schema or {"type": "object", "properties": {"y": {"type": "integer"}}, "required": ["y"], "additionalProperties": False},
        handler=handler or _default_handler,
        timeout_sec=timeout,
        error_policy=error_policy,
    )


# ---------------------------------------------------------------- 注册表

def test_register_get_list_has():
    reg = ToolRegistry()
    reg.register(_tool("a"))
    reg.register(_tool("b"))
    assert reg.has("a") and reg.has("b") and not reg.has("c")
    assert reg.get("a").name == "a"
    assert {t.name for t in reg.list()} == {"a", "b"}
    assert len(reg.list()) == 2


def test_register_idempotent():
    reg = ToolRegistry()
    reg.register(_tool("a"))
    reg.register(_tool("a"))  # 同名重复注册：覆盖，幂等
    assert len(reg.list()) == 1
    assert reg.get("a").name == "a"


def test_get_missing_raises():
    reg = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        reg.get("nope")


def test_execute_missing_tool_raises():
    reg = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        reg.get("nope")


@pytest.mark.asyncio
async def test_execute_missing_tool_raises_async():
    reg = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        await reg.execute("nope", x=1)


# ---------------------------------------------------------------- schema 校验

@pytest.mark.asyncio
async def test_input_schema_missing_required():
    reg = ToolRegistry()
    reg.register(_tool("a"))
    with pytest.raises(ToolInputError):
        await reg.execute("a")  # 缺 x


@pytest.mark.asyncio
async def test_input_schema_wrong_type():
    reg = ToolRegistry()
    reg.register(_tool("a"))
    with pytest.raises(ToolInputError):
        await reg.execute("a", x="not-int")


@pytest.mark.asyncio
async def test_input_schema_extra_property():
    reg = ToolRegistry()
    reg.register(_tool("a"))
    with pytest.raises(ToolInputError):
        await reg.execute("a", x=1, extra=2)


@pytest.mark.asyncio
async def test_output_schema_invalid():
    async def bad_handler(**kw):
        return {"wrong": 1}

    reg = ToolRegistry()
    reg.register(_tool("a", handler=bad_handler))
    with pytest.raises(ToolOutputError):
        await reg.execute("a", x=1)


@pytest.mark.asyncio
async def test_output_schema_ok():
    reg = ToolRegistry()
    reg.register(_tool("a"))
    out = await reg.execute("a", x=3)
    assert out == {"y": 3}


# ---------------------------------------------------------------- timeout / error_policy

@pytest.mark.asyncio
async def test_timeout_degrade():
    async def slow(**kw):
        await __import__("asyncio").sleep(0.3)
        return {"y": 1}
    reg = ToolRegistry()
    reg.register(_tool("a", handler=slow, timeout=0.05, error_policy="degrade"))
    with pytest.raises(ToolTimeoutError):
        await reg.execute("a", x=1)


@pytest.mark.asyncio
async def test_timeout_abort():
    async def slow(**kw):
        await __import__("asyncio").sleep(0.3)
        return {"y": 1}
    reg = ToolRegistry()
    reg.register(_tool("a", handler=slow, timeout=0.05, error_policy="abort"))
    with pytest.raises(ToolAbortError):
        await reg.execute("a", x=1)


@pytest.mark.asyncio
async def test_handler_error_degrade():
    def boom(**kw):
        raise RuntimeError("boom")
    reg = ToolRegistry()
    reg.register(_tool("a", handler=boom, error_policy="degrade"))
    with pytest.raises(ToolExecutionError) as ei:
        await reg.execute("a", x=1)
    assert "boom" in str(ei.value)


@pytest.mark.asyncio
async def test_handler_error_abort():
    def boom(**kw):
        raise RuntimeError("boom")
    reg = ToolRegistry()
    reg.register(_tool("a", handler=boom, error_policy="abort"))
    with pytest.raises(ToolAbortError):
        await reg.execute("a", x=1)


@pytest.mark.asyncio
async def test_tool_errors_share_hierarchy():
    assert issubclass(ToolTimeoutError, ToolError)
    assert issubclass(ToolExecutionError, ToolError)
    assert issubclass(ToolAbortError, ToolError)
    assert issubclass(ToolInputError, ToolError)
    assert issubclass(ToolOutputError, ToolError)
    assert issubclass(ToolNotFoundError, ToolError)


# ---------------------------------------------------------------- 内置工具：正常路径

@pytest.mark.asyncio
async def test_kb_retrieve_normal():
    async def fake_retrieve(query, top_k=5):
        return SimpleNamespace(
            chunks=[SimpleNamespace(content="c1", source_file="f.md", chunk_index=0, score=0.9)],
            sources=[SimpleNamespace(file="f.md", chunk_index=0, score=0.9)],
        )
    facade = SimpleNamespace(retrieve=fake_retrieve)
    tool = make_kb_retrieve_tool(facade)
    reg = ToolRegistry()
    reg.register(tool)
    out = await reg.execute("kb_retrieve", query="什么是 JVM？", top_k=3)
    assert out["chunks"][0]["content"] == "c1"
    assert out["sources"][0]["file"] == "f.md"
    assert out["chunks"][0]["score"] == 0.9


@pytest.mark.asyncio
async def test_get_profile_normal():
    store = SimpleNamespace(get=lambda uid: {"weak_points": ["JVM"], "level": "P6", "accuracy": 0.7, "history": []})
    reg = ToolRegistry()
    reg.register(make_get_profile_tool(store))
    out = await reg.execute("get_profile", user_id="u1")
    assert out["weak_points"] == ["JVM"] and out["level"] == "P6"


@pytest.mark.asyncio
async def test_update_profile_normal():
    calls = []

    class Store:
        def update(self, uid, patch):
            calls.append((uid, patch))

    reg = ToolRegistry()
    reg.register(make_update_profile_tool(Store()))
    out = await reg.execute("update_profile", user_id="u1", patch={"level": "P7"})
    assert out == {"ok": True}
    assert calls == [("u1", {"level": "P7"})]


@pytest.mark.asyncio
async def test_mock_resume_normal():
    reg = ToolRegistry()
    reg.register(make_mock_resume_tool())
    out = await reg.execute("mock_resume", user_id="u1")
    assert out["projects"] and out["technologies"]
    assert all("technologies" in p for p in out["projects"])


@pytest.mark.asyncio
async def test_pick_next_topic_normal():
    tracker = SimpleNamespace(
        get_next_suggestion=lambda sid, pos: {"category": "JVM", "topic": "类加载", "reason": "薄弱方向"}
    )
    reg = ToolRegistry()
    reg.register(make_pick_next_topic_tool(tracker))
    out = await reg.execute("pick_next_topic", session_id="s1", position="Java后端")
    assert out["topic"] == "类加载" and out["category"] == "JVM"


@pytest.mark.asyncio
async def test_pick_next_topic_tree_missing_normal():
    tracker = SimpleNamespace(
        get_next_suggestion=lambda sid, pos: {"category": None, "topic": None, "reason": "知识树未加载"}
    )
    reg = ToolRegistry()
    reg.register(make_pick_next_topic_tool(tracker))
    out = await reg.execute("pick_next_topic", session_id="s1", position="Java后端")
    assert out["topic"] is None and out["reason"] == "知识树未加载"


@pytest.mark.asyncio
async def test_eval_rules_with_score():
    reg = ToolRegistry()
    reg.register(make_eval_rules_tool())
    out = await reg.execute("eval_rules", score=9.0, reask_allowed=False, round=3, max_rounds=15)
    assert out["action"] == "next" and out["delta"] == 1 and out["score"] == 9.0


@pytest.mark.asyncio
async def test_eval_rules_with_hit_ratio():
    reg = ToolRegistry()
    reg.register(make_eval_rules_tool())
    out = await reg.execute("eval_rules", hit_ratio=0.5, reask_allowed=False, round=3, max_rounds=15)
    assert out["score"] == 8  # round(5 + 5*0.5)
    assert out["action"] == "next"


@pytest.mark.asyncio
async def test_eval_rules_reask():
    reg = ToolRegistry()
    reg.register(make_eval_rules_tool())
    out = await reg.execute("eval_rules", score=3.0, reask_allowed=True, round=3, max_rounds=15)
    assert out["action"] == "reask" and out["delta"] == -1


# ---------------------------------------------------------------- 内置工具：失败路径

@pytest.mark.asyncio
async def test_kb_retrieve_failure_degrade():
    async def fake_retrieve(query, top_k=5):
        raise RuntimeError("facade down")

    reg = ToolRegistry()
    reg.register(make_kb_retrieve_tool(SimpleNamespace(retrieve=fake_retrieve)))
    with pytest.raises(ToolExecutionError):
        await reg.execute("kb_retrieve", query="q")


@pytest.mark.asyncio
async def test_get_profile_failure():
    def boom(uid):
        raise RuntimeError("store down")
    reg = ToolRegistry()
    reg.register(make_get_profile_tool(SimpleNamespace(get=boom)))
    with pytest.raises(ToolExecutionError):
        await reg.execute("get_profile", user_id="u1")


@pytest.mark.asyncio
async def test_update_profile_failure():
    def boom(uid, patch):
        raise RuntimeError("store down")
    reg = ToolRegistry()
    reg.register(make_update_profile_tool(SimpleNamespace(update=boom)))
    with pytest.raises(ToolExecutionError):
        await reg.execute("update_profile", user_id="u1", patch={})


@pytest.mark.asyncio
async def test_mock_resume_input_schema_failure():
    reg = ToolRegistry()
    reg.register(make_mock_resume_tool())
    with pytest.raises(ToolInputError):
        await reg.execute("mock_resume")  # 缺 user_id


@pytest.mark.asyncio
async def test_pick_next_topic_failure():
    def boom(sid, pos):
        raise RuntimeError("tracker down")
    reg = ToolRegistry()
    reg.register(make_pick_next_topic_tool(SimpleNamespace(get_next_suggestion=boom)))
    with pytest.raises(ToolExecutionError):
        await reg.execute("pick_next_topic", session_id="s1", position="Java后端")


@pytest.mark.asyncio
async def test_eval_rules_missing_inputs_failure():
    reg = ToolRegistry()
    reg.register(make_eval_rules_tool())
    with pytest.raises(ToolInputError):
        await reg.execute("eval_rules", reask_allowed=False, round=3, max_rounds=15)  # score/hit_ratio 均缺


@pytest.mark.asyncio
async def test_build_default_tools_registers_all_six():
    facade = SimpleNamespace(retrieve=lambda *a, **k: SimpleNamespace(chunks=[], sources=[]))
    tracker = SimpleNamespace(get_next_suggestion=lambda *a, **k: {"category": None, "topic": None, "reason": ""})
    store = SimpleNamespace(get=lambda uid: {}, update=lambda uid, patch: None)
    tools = build_default_tools(facade=facade, topic_tracker=tracker, profile_store=store)
    assert set(tools) == {"kb_retrieve", "get_profile", "update_profile", "mock_resume", "pick_next_topic", "eval_rules"}
