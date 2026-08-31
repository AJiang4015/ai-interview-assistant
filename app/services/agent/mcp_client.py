"""MCP 客户端/服务端适配（impl-spec v2 附录 F「MCP 化」；W2 上，决策 2「MCP 真实现」）。

对应关系（spec → 本模块）：
- 决策 2：官方 Python MCP SDK（mcp 2.1.1），真实 MCP 协议（JSON-RPC over transport）。
- 附录 F：`kb_retrieve` + `mock_resume` 暴露为 MCP 工具；handler **复用 tools.py 的本地 handler**
  （不重复实现业务逻辑）。
- 附录 F「本地注册表保留为降级路径」：MCP 连接失败 → 不注册 MCP 版本，本地工具照常（自动回退）。
- B4「运输方式」：本环境探测结论——**stdio 被沙箱拒绝**（PermissionError，子进程管道），
  **streamable HTTP 通过**（真实 HTTP 传输）。故运行时默认 streamable HTTP；
  单测用内存 transport（`create_client_server_memory_streams`，真实协议、无 IO）。

设计约束：
- 本模块只做「MCP 协议 ↔ 统一 Tool 契约」的桥接：产出标准 :class:`Tool` 对象，
  注册进 ToolRegistry 后，编排层（orchestrator）经统一 Tool 接口使用 MCP——**零编排层改动**。
- MCP 不可用 → `attach_mcp_tools` 返回 False，本地工具保持（不破坏 W1 链路）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from mcp import types
from mcp.client.session import ClientSession
from mcp.server import Server

from app.services.agent.tools import Tool, ToolRegistry

logger = logging.getLogger(__name__)

MCP_ENDPOINT_PATH = "/mcp"
MCP_SERVER_NAME = "agent-interview-mcp"


# ---------------------------------------------------------------- 服务端（暴露两个工具）

def build_mcp_server(facade: Any) -> Server:
    """创建 MCP server：暴露 kb_retrieve + mock_resume（handler 复用 tools.py，行为与本地一致）。

    传入 facade 供 kb_retrieve 使用（检索能力由宿主注入，MCP 层不实现 RAG）。
    """
    from app.services.agent.tools import make_kb_retrieve_tool, make_mock_resume_tool

    local_tools: dict[str, Tool] = {
        "kb_retrieve": make_kb_retrieve_tool(facade),
        "mock_resume": make_mock_resume_tool(),
    }
    mcp_tools = [
        types.Tool(name=t.name, description=t.description, input_schema=t.input_schema)
        for t in local_tools.values()
    ]

    async def on_list_tools(ctx, params=None):  # noqa: ANN001
        return types.ListToolsResult(tools=mcp_tools)

    async def on_call_tool(ctx, params):  # noqa: ANN001
        tool = local_tools.get(params.name)
        if tool is None:
            return types.CallToolResult(content=[
                types.TextContent(type="text", text=json.dumps({"error": f"unknown tool: {params.name}"}, ensure_ascii=False)),
            ])
        try:
            result = await tool.handler(**(params.arguments or {}))
        except Exception as e:  # noqa: BLE001 —— 工具异常序列化为错误结果（MCP 协议允许）
            logger.warning("MCP tool %s failed: %s", params.name, e)
            return types.CallToolResult(content=[
                types.TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False)),
            ])
        return types.CallToolResult(content=[
            types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False)),
        ])

    return Server(MCP_SERVER_NAME, on_list_tools=on_list_tools, on_call_tool=on_call_tool)


# ---------------------------------------------------------------- 客户端适配（MCP → Tool）

def _wrap_mcp_tool(session: ClientSession, mcp_tool: types.Tool, output_schema: dict, timeout_sec: float) -> Tool:
    """把 MCP 远端工具包装为本地统一 :class:`Tool`（handler = 经 MCP 协议调用远端）。"""

    async def handler(**kwargs: Any) -> dict:
        result = await session.call_tool(mcp_tool.name, kwargs)
        text = "".join(getattr(c, "text", "") for c in result.content)
        try:
            return json.loads(text) if text else {}
        except json.JSONDecodeError:
            return {"raw": text}

    return Tool(
        name=mcp_tool.name,
        description=f"mcp:{MCP_SERVER_NAME}|{mcp_tool.name}: {mcp_tool.description}",
        input_schema=mcp_tool.input_schema,
        output_schema=output_schema,
        handler=handler,
        timeout_sec=timeout_sec,
        error_policy="degrade",
    )


class McpClientAdapter:
    """连接 MCP server → 把远端工具暴露为本地 Tool 对象。

    transport：
    - "streamable_http"（默认，运行时）：进程内起 uvicorn 服务 streamable_http_app，经 HTTP 连接；
    - "memory"（单测）：create_client_server_memory_streams 进程内真实协议，无 IO。
    """

    def __init__(
        self,
        server: Server,
        *,
        transport: str = "streamable_http",
        host: str = "127.0.0.1",
        port: int = 18123,
        output_schemas: Optional[dict[str, dict]] = None,
        tool_timeout_sec: float = 10.0,
    ):
        self._server = server
        self._transport = transport
        self._host = host
        self._port = port
        self._output_schemas = output_schemas or {}
        self._tool_timeout = tool_timeout_sec
        self._session: Optional[ClientSession] = None
        self._transport_ctx: Any = None
        self._server_task: Optional[asyncio.Task] = None
        self._uvicorn_runner: Any = None
        self._mem_ctx: Any = None
        self._tools: dict[str, Tool] = {}
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """建立 MCP 会话并列出工具（失败返回 False，不抛）。"""
        try:
            if self._transport == "memory":
                await self._connect_memory()
            elif self._transport == "streamable_http":
                await self._connect_http()
            else:
                raise ValueError(f"unsupported MCP transport: {self._transport}")
            tools_result = await self._session.list_tools()
            for t in tools_result.tools:
                self._tools[t.name] = _wrap_mcp_tool(
                    self._session, t, self._output_schemas.get(t.name, {"type": "object"}), self._tool_timeout,
                )
            self._connected = bool(self._tools)
            return self._connected
        except Exception as e:  # noqa: BLE001 —— MCP 不可用 → 回退本地
            logger.warning("MCP connect failed (%s): %s", self._transport, e)
            await self.close()
            return False

    async def _connect_memory(self) -> None:
        """官方 SDK 内存 transport（mcp.client._memory.InMemoryTransport）：进程内真实协议，
        自动在后台任务运行 server 并优雅关闭，避免 run/initialize 竞态。"""
        from mcp.client._memory import InMemoryTransport

        self._transport_ctx = InMemoryTransport(self._server)
        read_stream, write_stream = await self._transport_ctx.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()

    async def _connect_http(self) -> None:
        import socket

        import uvicorn
        from mcp.client.streamable_http import streamable_http_client

        # 端口预检：避免 uvicorn 绑定失败时 sys.exit 逃逸（BaseException，connect 无法捕获）
        probe = socket.socket()
        try:
            probe.bind((self._host, self._port))
        except OSError as e:
            raise RuntimeError(f"MCP port {self._port} unavailable: {e}") from e
        finally:
            probe.close()

        config = uvicorn.Config(
            self._server.streamable_http_app(), host=self._host, port=self._port, log_level="error",
        )
        runner = uvicorn.Server(config)
        self._uvicorn_runner = runner
        self._server_task = asyncio.create_task(runner.serve())
        for _ in range(100):
            if runner.started:
                break
            await asyncio.sleep(0.05)
        if not runner.started:
            raise RuntimeError("MCP streamable HTTP server failed to start")
        url = f"http://{self._host}:{self._port}{MCP_ENDPOINT_PATH}"
        self._transport_ctx = streamable_http_client(url)
        read_stream, write_stream = await self._transport_ctx.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()

    def tools(self) -> dict[str, Tool]:
        return dict(self._tools)

    async def close(self) -> None:
        try:
            if self._session is not None:
                await self._session.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        self._session = None
        try:
            if self._transport_ctx is not None:
                await self._transport_ctx.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        self._transport_ctx = None
        try:
            if self._mem_ctx is not None:
                await self._mem_ctx.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        self._mem_ctx = None
        if self._uvicorn_runner is not None:
            self._uvicorn_runner.should_exit = True
        if self._server_task is not None:
            self._server_task.cancel()
            try:
                await self._server_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._uvicorn_runner = None
        self._server_task = None
        self._tools = {}
        self._connected = False


async def attach_mcp_tools(
    registry: ToolRegistry,
    facade: Any,
    *,
    transport: str = "streamable_http",
    host: str = "127.0.0.1",
    port: int = 18123,
) -> Optional[McpClientAdapter]:
    """装配：启动 MCP server + 连接 → 把 kb_retrieve/mock_resume 的 MCP 版本注册进 registry。

    - 成功 → 返回 adapter（**调用方必须持有它**，其内部持有 uvicorn 任务/会话生命周期；
      结束时应 `await adapter.close()`）；
    - 失败 → 返回 None，registry 保持本地工具（**自动回退**，不破坏 W1 链路）。
    """
    server = build_mcp_server(facade)
    from app.services.agent.tools import make_kb_retrieve_tool, make_mock_resume_tool

    output_schemas = {
        t.name: t.output_schema
        for t in (make_kb_retrieve_tool(facade), make_mock_resume_tool())
    }
    adapter = McpClientAdapter(
        server, transport=transport, host=host, port=port, output_schemas=output_schemas,
    )
    ok = await adapter.connect()
    if not ok:
        await adapter.close()
        return None
    for tool in adapter.tools().values():
        registry.register(tool)
    return adapter
