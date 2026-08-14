from dataclasses import dataclass

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

SILICONFLOW_RERANK_API = "https://api.siliconflow.cn/v1/rerank"


@dataclass
class RerankResult:
    index: int
    score: float
    content: str


class RerankService:
    """基于 SiliconFlow API 的语义重排序服务。

    通过调用硅基流动的 Qwen/Qwen3-Reranker-4B 模型对检索结果进行相关性重排，
    避免本地加载模型带来的依赖下载与 OMP 冲突问题。API 调用失败时自动降级为原始顺序。
    """

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "Qwen/Qwen3-Reranker-4B",
        enabled: bool = True,
        timeout: int = 30,
    ):
        self._api_key = api_key or getattr(settings, "siliconflow_api_key", "")
        self._model_name = model_name
        self._enabled = enabled
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def loaded(self) -> bool:
        # API 方式无需加载本地模型
        return True

    def load_model(self):
        # API 方式无需加载本地模型
        return

    async def rerank(
        self, query: str, documents: list[str], top_k: int = 5
    ) -> list[RerankResult]:
        if not self._enabled or not documents:
            return [
                RerankResult(index=i, score=1.0, content=doc)
                for i, doc in enumerate(documents[:top_k])
            ]

        if not self._api_key:
            logger.warning("SiliconFlow API key 未配置，重排序降级为原始顺序")
            return [
                RerankResult(index=i, score=1.0, content=doc)
                for i, doc in enumerate(documents[:top_k])
            ]

        try:
            scores = await self._call_rerank_api(query, documents, top_k)
        except RetryError as e:
            logger.error(f"Rerank API retry exhausted: {e.last_attempt.exception()}")
            return self._fallback(documents, top_k)
        except Exception as e:
            logger.error(f"Rerank API failed, fallback to original order: {e}")
            return self._fallback(documents, top_k)

        # scores: {index: relevance_score}
        sorted_indices = sorted(scores.keys(), key=lambda i: scores[i], reverse=True)
        return [
            RerankResult(index=idx, score=float(scores[idx]), content=documents[idx])
            for idx in sorted_indices[:top_k]
        ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def _call_rerank_api(
        self, query: str, documents: list[str], top_n: int
    ) -> dict[int, float]:
        payload = {
            "model": self._model_name,
            "query": query,
            "documents": documents,
            "top_n": min(top_n, len(documents)),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                SILICONFLOW_RERANK_API, json=payload, headers=headers
            )
            response.raise_for_status()
            data = response.json()

        scores: dict[int, float] = {}
        for item in data.get("results", []):
            scores[item.get("index")] = item.get("relevance_score", 0.0)
        return scores

    @staticmethod
    def _fallback(documents: list[str], top_k: int) -> list[RerankResult]:
        return [
            RerankResult(index=i, score=1.0, content=doc)
            for i, doc in enumerate(documents[:top_k])
        ]