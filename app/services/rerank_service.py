from dataclasses import dataclass
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RerankResult:
    index: int
    score: float
    content: str


class RerankService:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", enabled: bool = True):
        self._model_name = model_name
        self._enabled = enabled
        self._model = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load_model(self):
        if self._model is not None:
            return
        logger.info(f"Loading reranker model: {self._model_name}")
        from sentence_transformers import CrossEncoder
        self._model = CrossEncoder(self._model_name)
        logger.info(f"Reranker model loaded: {self._model_name}")

    async def rerank(
        self, query: str, documents: list[str], top_k: int = 5
    ) -> list[RerankResult]:
        if not self._enabled or not documents:
            return [
                RerankResult(index=i, score=1.0, content=doc)
                for i, doc in enumerate(documents[:top_k])
            ]

        if self._model is None:
            self.load_model()

        pairs = [[query, doc] for doc in documents]
        scores = self._model.predict(pairs)
        scored = list(enumerate(zip(scores, documents)))
        scored.sort(key=lambda x: x[1][0], reverse=True)

        return [
            RerankResult(index=idx, score=float(score), content=doc)
            for idx, (score, doc) in scored[:top_k]
        ]