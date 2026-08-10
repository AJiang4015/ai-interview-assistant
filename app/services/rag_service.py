from app.config import settings
from app.api.schemas import QueryResponse, SourceInfo
from app.services.embedding import EmbeddingService
from app.services.llm_client import LLMClient
from app.storage.faiss_store import FaissStore
from app.exceptions import IndexNotFoundError
from app.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "你是一个专业的 Java/后端技术面试官助手。"
    "请严格基于提供的参考资料回答问题。"
    "如果参考资料中没有相关内容，请明确说明。"
    "回答要准确、简洁、结构清晰。"
)


class RAGService:
    def __init__(self, faiss_store: FaissStore, embedding: EmbeddingService, llm: LLMClient):
        self.faiss = faiss_store
        self.embedding = embedding
        self.llm = llm
        self.top_k = settings.top_k

    async def query(self, question: str) -> QueryResponse:
        if not self.faiss.is_loaded():
            raise IndexNotFoundError("索引未构建，请先调用 /api/index/build")

        logger.info(f"Processing query: {question[:50]}...")

        query_vector = await self.embedding.encode([question])
        if query_vector.size == 0:
            raise ValueError("Failed to encode question")

        results = self.faiss.search(query_vector[0], self.top_k)
        if not results:
            logger.warning("No relevant chunks found")
            return QueryResponse(
                answer="抱歉，我在知识库中没有找到相关内容。请尝试重新构建索引或添加更多相关文档。",
                sources=[],
                retrieved_chunks=[]
            )

        context = "\n---\n".join([r.content for r in results])
        prompt = f"参考资料：\n{context}\n\n问题：{question}"

        answer = await self.llm.chat(prompt, SYSTEM_PROMPT)

        sources = [
            SourceInfo(
                file=r.source_file,
                chunk_index=r.chunk_index,
                score=r.score
            )
            for r in results
        ]

        return QueryResponse(
            answer=answer,
            sources=sources,
            retrieved_chunks=[r.content for r in results]
        )
