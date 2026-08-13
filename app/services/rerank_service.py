import json
from dataclasses import dataclass
from typing import Optional

import httpx

from app.utils.logger import get_logger

logger = get_logger(__name__)

SILICONFLOW_RERANK_URL = "https://api.siliconflow.cn/v1/rerank"


@dataclass
class RerankResult:
    index: int
    score: float
    content: str


class RerankService:
    def __init__(
        self,
        api_key: str,
        model_name: str = "Qwen/Qwen3-Reranker-4B",
        enabled: bool = True,
    ):
        self._api_key = api_key
        self._model_name = model_name
        self._enabled = enabled
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def loaded(self) -> bool:
        return self._client is not None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def rerank(
        self, query: str, documents: list[str], top_k: int = 5
    ) -> list[RerankResult]:
        if not self._enabled or not documents:
            return [
                RerankResult(index=i, score=1.0, content=doc)
                for i, doc in enumerate(documents[:top_k])
            ]

        if not self._api_key:
            logger.warning("SiliconFlow API key not set, skipping rerank")
            return [
                RerankResult(index=i, score=1.0, content=doc)
                for i, doc in enumerate(documents[:top_k])
            ]

        try:
            client = self._get_client()
            payload = {
                "model": self._model_name,
                "query": query,
                "documents": documents,
                "top_k": top_k,
            }
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }

            logger.info(
                f"Reranking {len(documents)} docs with {self._model_name}..."
            )
            resp = await client.post(
                SILICONFLOW_RERANK_URL, json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            reranked = []
            for r in results:
                idx = r.get("index", 0)
                score = r.get("relevance_score", 0.0)
                doc_text = r.get("document", {}).get("text", "")
                reranked.append(RerankResult(index=idx, score=score, content=doc_text))

            logger.info(f"Rerank complete, top score: {reranked[0].score:.4f}")
            return reranked

        except Exception as e:
            logger.error(f"Rerank API call failed: {e}")
            # Fallback: return original order
            return [
                RerankResult(index=i, score=1.0, content=doc)
                for i, doc in enumerate(documents[:top_k])
            ]

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None