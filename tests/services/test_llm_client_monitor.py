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