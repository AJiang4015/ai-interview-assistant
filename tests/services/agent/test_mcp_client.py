"""W2 上：MCP 客户端/服务端适配单元测试（impl-spec v2 附录 F「MCP 化」）。

先于实现编写（TDD）。覆盖：
- 内存 transport（真实 MCP 协议，进程内）暴露 kb_retrieve + mock_resume
- 经统一 Tool 接口（ToolRegistry）执行 MCP 工具
- input schema 在 MCP 路径上仍生效
- attach 成功 → 本地同名工具被 MCP 版本覆盖（description 带 mcp: 标记）
- attach 失败（server 起不来）→ 自动回退本地工具
"""

from types import SimpleNamespace

import pytest

from app.services.agent.mcp_client import (
    McpClientAdapter,
    attach_mcp_tools,
    build_mcp_server,
)
from app.services.agent.tools import ToolInputError, ToolRegistry, make_kb_retrieve_tool, make_mock_resume_tool


class _EmptyFacade:
    async def retrieve(self, query, top_k=5):
        return SimpleNamespace(chunks=[], sources=[])


@pytest.mark.asyncio
async def test_memory_transport_exposes_two_tools():
    server = build_mcp_server(_EmptyFacade())
    adapter = McpClientAdapter(server, transport="memory")
    assert await adapter.connect() is True
    assert set(adapter.tools()) == {"kb_retrieve", "mock_resume"}
    await adapter.close()


@pytest.mark.asyncio
async def test_mcp_tool_call_via_registry():
    reg = ToolRegistry()
    server = build_mcp_server(_EmptyFacade())
    adapter = McpClientAdapter(server, transport="memory")
    await adapter.connect()
    for t in adapter.tools().values():
        reg.register(t)

    out = await reg.execute("kb_retrieve", query="什么是 JVM？", top_k=3)
    assert out == {"chunks": [], "sources": []}
    res = await reg.execute("mock_resume", user_id="u1")
    assert res["projects"] and res["technologies"]
    await adapter.close()


@pytest.mark.asyncio
async def test_input_schema_validated_through_mcp():
    reg = ToolRegistry()
    server = build_mcp_server(_EmptyFacade())
    adapter = McpClientAdapter(server, transport="memory")
    await adapter.connect()
    for t in adapter.tools().values():
        reg.register(t)
    with pytest.raises(ToolInputError):
        await reg.execute("kb_retrieve")  # 缺 query
    await adapter.close()


@pytest.mark.asyncio
async def test_attach_success_overrides_local_with_mcp():
    reg = ToolRegistry()
    facade = _EmptyFacade()
    reg.register(make_kb_retrieve_tool(facade))
    reg.register(make_mock_resume_tool())
    adapter = await attach_mcp_tools(reg, facade, transport="memory")
    assert adapter is not None
    assert reg.get("kb_retrieve").description.startswith("mcp:")
    assert reg.get("mock_resume").description.startswith("mcp:")
    # 编排层照常经统一 Tool 接口执行（实际走 MCP 协议）
    out = await reg.execute("kb_retrieve", query="q")
    assert out == {"chunks": [], "sources": []}
    await adapter.close()


@pytest.mark.asyncio
async def test_streamable_http_transport_success():
    """真实 streamable HTTP 传输（本环境探测 PASS 的 transport）：端到端经 HTTP 走 MCP。"""
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    reg = ToolRegistry()
    facade = _EmptyFacade()
    adapter = await attach_mcp_tools(reg, facade, transport="streamable_http", host="127.0.0.1", port=port)
    assert adapter is not None
    assert reg.get("kb_retrieve").description.startswith("mcp:")
    out = await reg.execute("kb_retrieve", query="q")
    assert out == {"chunks": [], "sources": []}
    await adapter.close()


@pytest.mark.asyncio
async def test_attach_failure_falls_back_to_local():
    import socket

    reg = ToolRegistry()
    facade = _EmptyFacade()
    reg.register(make_kb_retrieve_tool(facade))  # 本地工具先行

    # 占用一个端口 → uvicorn 绑定失败 → MCP 连接失败 → 自动回退本地
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    occupied_port = sock.getsockname()[1]
    try:
        adapter = await attach_mcp_tools(
            reg, facade, transport="streamable_http", host="127.0.0.1", port=occupied_port,
        )
    finally:
        sock.close()
    assert adapter is None
    assert not reg.get("kb_retrieve").description.startswith("mcp:")
    # 本地工具照常可用（W1 链路未破坏）
    out = await reg.execute("kb_retrieve", query="q")
    assert out == {"chunks": [], "sources": []}
