import numpy as np
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

from app.config import settings
from app.exceptions import EmbeddingAPIError
from app.utils.logger import get_logger

logger = get_logger(__name__)

SILICONFLOW_API = "https://api.siliconflow.cn/v1/embeddings"
BATCH_SIZE = 32


class EmbeddingService:
    def __init__(self):
        self.api_key = settings.siliconflow_api_key
        self.model = settings.siliconflow_model
        self.timeout = settings.request_timeout

    async def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.array([]).reshape(0, 1024)

        all_vectors = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for i in range(0, len(texts), BATCH_SIZE):
                    batch = texts[i:i + BATCH_SIZE]
                    vectors = await self._encode_batch_with_retry(client, batch)
                    all_vectors.append(vectors)
        except EmbeddingAPIError:
            raise
        except RetryError as e:
            raise EmbeddingAPIError(f"Embedding API retry exhausted: {e.last_attempt.exception()}") from e
        except httpx.HTTPError as e:
            raise EmbeddingAPIError(f"Embedding API request failed: {e}") from e
        except Exception as e:
            raise EmbeddingAPIError(f"Embedding encoding failed: {e}") from e

        result = np.vstack(all_vectors)
        if result.size > 0:
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            norms[norms == 0] = 1
            result = result / norms
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def _encode_batch_with_retry(self, client: httpx.AsyncClient, texts: list[str]) -> np.ndarray:
        try:
            return await self._encode_batch(client, texts)
        except httpx.HTTPError as e:
            raise EmbeddingAPIError(f"Embedding API request failed: {e}") from e

    async def _encode_batch(self, client: httpx.AsyncClient, texts: list[str]) -> np.ndarray:
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float"
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        response = await client.post(SILICONFLOW_API, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        vectors = [item["embedding"] for item in data["data"]]
        return np.array(vectors, dtype=np.float32)
