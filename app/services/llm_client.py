import json
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

from app.config import settings
from app.exceptions import LLMAPIError
from app.services import monitor
from app.utils.logger import get_logger

logger = get_logger(__name__)

BAILIAN_API = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


class LLMClient:
    def __init__(self):
        self.api_key = settings.bailian_api_key
        self.model = settings.bailian_model
        self.temperature = settings.llm_temperature
        self.timeout = settings.request_timeout

    async def chat(self, prompt: str, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            return await self._chat_with_retry(payload, headers)
        except LLMAPIError:
            raise
        except RetryError as e:
            raise LLMAPIError(f"LLM API retry exhausted: {e.last_attempt.exception()}") from e
        except Exception as e:
            raise LLMAPIError(f"LLM chat failed: {e}") from e

    async def chat_stream(self, prompt: str, system: str | None = None):
        """Stream chat completions, yielding text chunks as they arrive."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        try:
            async for chunk in self._chat_stream_retry(payload, headers):
                yield chunk
        except LLMAPIError:
            raise
        except RetryError as e:
            raise LLMAPIError(f"LLM API retry exhausted: {e.last_attempt.exception()}") from e
        except Exception as e:
            raise LLMAPIError(f"LLM chat stream failed: {e}") from e

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def _chat_with_retry(self, payload: dict, headers: dict) -> str:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(BAILIAN_API, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage", {})
                monitor.emit_cost(
                    self.model,
                    in_n=usage.get("prompt_tokens", 0),
                    out_n=usage.get("completion_tokens", 0),
                    session_id="unknown",  # 单次 chat 无会话上下文；会话级由上层注入
                )
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPError as e:
            raise LLMAPIError(f"LLM API request failed: {e}") from e

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def _chat_stream_retry(self, payload: dict, headers: dict):
        try:
            async with httpx.AsyncClient(timeout=self.timeout * 3) as client:
                async with client.stream("POST", BAILIAN_API, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse stream data: {data_str[:100]}")
        except httpx.HTTPError as e:
            raise LLMAPIError(f"LLM API stream request failed: {e}") from e
