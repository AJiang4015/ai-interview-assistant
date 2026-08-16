import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_client import LLMClient


def _run(coro):
    return asyncio.run(coro)


def _build_usage_response(fake_resp):
    """构造 `async with httpx.AsyncClient(...) as client: response = await client.post(...)` 的 mock。"""
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=fake_resp)

    client_ctx = AsyncMock()
    client_ctx.post = AsyncMock(return_value=response)

    client_class = MagicMock()
    client_class.return_value.__aenter__ = AsyncMock(return_value=client_ctx)
    client_class.return_value.__aexit__ = AsyncMock(return_value=False)
    return client_class


def test_chat_records_usage_and_returns_answer():
    fake_resp = {
        "choices": [{"message": {"content": "answer"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    client_class = _build_usage_response(fake_resp)

    with patch("app.services.llm_client.httpx.AsyncClient", client_class), \
         patch("app.services.llm_client.monitor.emit_cost") as emit:
        result = _run(LLMClient().chat("hi"))

    assert result == "answer"
    emit.assert_called_once_with(
        "qwen3.7-max",
        in_n=100,
        out_n=50,
        session_id="unknown",
    )


def test_chat_without_usage_defaults_to_zero():
    fake_resp = {"choices": [{"message": {"content": "answer"}}]}
    client_class = _build_usage_response(fake_resp)

    with patch("app.services.llm_client.httpx.AsyncClient", client_class), \
         patch("app.services.llm_client.monitor.emit_cost") as emit:
        result = _run(LLMClient().chat("hi"))

    assert result == "answer"
    emit.assert_called_once_with(
        "qwen3.7-max",
        in_n=0,
        out_n=0,
        session_id="unknown",
    )


def test_chat_passes_session_id():
    fake_resp = {
        "choices": [{"message": {"content": "answer"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    client_class = _build_usage_response(fake_resp)

    client = LLMClient()
    payload = {"model": client.model, "messages": []}
    headers = {"Authorization": "Bearer x"}

    with patch("app.services.llm_client.httpx.AsyncClient", client_class), \
         patch("app.services.llm_client.monitor.emit_cost") as emit:
        result = _run(client._chat_with_retry(payload, headers, session_id="s-x"))

    assert result == "answer"
    emit.assert_called_once_with(
        "qwen3.7-max",
        in_n=100,
        out_n=50,
        session_id="s-x",
    )


def _build_stream_client_class(lines):
    """构造 `async with httpx.AsyncClient(...) as client: async with client.stream(...) as response`
    的 mock，让 response.aiter_lines() 依次产出给定行。"""
    response = MagicMock()
    response.raise_for_status = MagicMock()

    async def _aiter_lines():
        for ln in lines:
            yield ln

    response.aiter_lines = _aiter_lines

    stream_ctx = AsyncMock()
    stream_ctx.__aenter__ = AsyncMock(return_value=response)
    stream_ctx.__aexit__ = AsyncMock(return_value=False)

    client_ctx = AsyncMock()
    client_ctx.stream = MagicMock(return_value=stream_ctx)

    client_class = MagicMock()
    client_class.return_value.__aenter__ = AsyncMock(return_value=client_ctx)
    client_class.return_value.__aexit__ = AsyncMock(return_value=False)
    return client_class


def test_chat_stream_usage_takes_last_nonempty():
    # 两条 data 行都带 usage，第二条覆盖第一条，且只 emit 一次
    lines = [
        'data: {"choices":[{"delta":{"content":"hi"}}],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}',
        'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":100,"completion_tokens":50,"total_tokens":150}}',
    ]
    client_class = _build_stream_client_class(lines)

    async def _collect():
        out = []
        async for c in LLMClient().chat_stream("hi"):
            out.append(c)
        return out

    with patch("app.services.llm_client.httpx.AsyncClient", client_class), \
         patch("app.services.llm_client.monitor.emit_cost") as emit:
        chunks = _run(_collect())

    assert chunks == ["hi"]
    emit.assert_called_once_with(
        "qwen3.7-max",
        in_n=100,
        out_n=50,
        session_id="unknown",
    )