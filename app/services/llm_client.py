import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

from app.config import settings
from app.exceptions import LLMAPIError
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def _chat_with_retry(self, payload: dict, headers: dict) -> str:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(BAILIAN_API, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPError as e:
            raise LLMAPIError(f"LLM API request failed: {e}") from e
