import json
import uuid

from app.config import settings
from app.api.schemas import QueryResponse, SourceInfo
from app.services.embedding import EmbeddingService
from app.services.llm_client import LLMClient
from app.storage.faiss_store import FaissStore
from app.storage.session_store import SessionStore
from app.exceptions import IndexNotFoundError
from app.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "你是一个专业的 Java/后端技术面试官助手。"
    "请基于提供的参考资料回答问题。"
    "如果参考资料中的内容与问题相关，请尽可能详细地回答。"
    "如果参考资料中确实没有相关内容，请简要说明。"
    "回答要准确、简洁、结构清晰。"
    "在多轮对话中，请结合上下文历史理解问题。"
)


class RAGService:
    def __init__(
        self,
        faiss_store: FaissStore,
        embedding: EmbeddingService,
        llm: LLMClient,
        session_store: SessionStore | None = None,
    ):
        self.faiss = faiss_store
        self.embedding = embedding
        self.llm = llm
        self.session_store = session_store
        self.top_k = settings.top_k

    async def query(
        self, question: str, session_id: str | None = None
    ) -> QueryResponse:
        if not self.faiss.is_loaded():
            raise IndexNotFoundError("索引未构建，请先调用 /api/index/build")

        logger.info(f"Processing query: {question[:50]}... (session: {session_id})")

        session_id = await self._ensure_session(session_id)

        query_vector = await self.embedding.encode([question])
        if query_vector.size == 0:
            raise ValueError("Failed to encode question")

        results = self.faiss.search(query_vector[0], self.top_k)
        if not results:
            logger.warning("No relevant chunks found")
            return QueryResponse(
                answer="抱歉，我在知识库中没有找到相关内容。请尝试重新构建索引或添加更多相关文档。",
                sources=[],
                retrieved_chunks=[],
                session_id=session_id,
            )

        unique_results = self._deduplicate_results(results)
        context = "\n---\n".join([r.content for r in unique_results])
        prompt = await self._build_prompt(session_id, question, context)

        answer = await self.llm.chat(prompt, SYSTEM_PROMPT)

        await self._save_to_session(session_id, question, answer, unique_results)

        sources = [
            SourceInfo(
                file=r.source_file,
                chunk_index=r.chunk_index,
                score=r.score,
            )
            for r in unique_results
        ]

        return QueryResponse(
            answer=answer,
            sources=sources,
            retrieved_chunks=[r.content for r in unique_results],
            session_id=session_id,
        )

    async def stream_query(
        self, question: str, session_id: str | None = None
    ):
        """Stream query results via SSE events."""
        if not self.faiss.is_loaded():
            raise IndexNotFoundError("索引未构建，请先调用 /api/index/build")

        logger.info(f"Processing stream query: {question[:50]}... (session: {session_id})")

        session_id = await self._ensure_session(session_id)

        yield self._sse_event("session", {"session_id": session_id})

        query_vector = await self.embedding.encode([question])
        if query_vector.size == 0:
            yield self._sse_event("error", {"message": "Failed to encode question"})
            return

        results = self.faiss.search(query_vector[0], self.top_k)
        if not results:
            logger.warning("No relevant chunks found")
            yield self._sse_event("retrieval", {
                "sources": [],
                "chunks": [],
            })
            yield self._sse_event("done", {
                "answer": "抱歉，我在知识库中没有找到相关内容。请尝试重新构建索引或添加更多相关文档。",
                "sources": [],
                "session_id": session_id,
            })
            return

        unique_results = self._deduplicate_results(results)

        sources_data = [
            {"file": r.source_file, "chunk_index": r.chunk_index, "score": r.score}
            for r in unique_results
        ]
        yield self._sse_event("retrieval", {
            "sources": sources_data,
            "chunks": [r.content for r in unique_results],
        })

        context = "\n---\n".join([r.content for r in unique_results])
        prompt = await self._build_prompt(session_id, question, context)

        answer_parts = []
        try:
            async for chunk in self.llm.chat_stream(prompt, SYSTEM_PROMPT):
                answer_parts.append(chunk)
                yield self._sse_event("token", {"content": chunk})
        except Exception as e:
            logger.error(f"Stream generation failed: {e}")
            yield self._sse_event("error", {"message": str(e)})
            return

        answer = "".join(answer_parts)

        await self._save_to_session(session_id, question, answer, unique_results)

        yield self._sse_event("done", {
            "answer": answer,
            "sources": sources_data,
            "session_id": session_id,
        })

    def _sse_event(self, event_type: str, data: dict) -> str:
        """Format an SSE event."""
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def _ensure_session(self, session_id: str | None) -> str:
        """Ensure a session exists, creating one if needed."""
        if not session_id and self.session_store and self.session_store.is_connected:
            session_id = str(uuid.uuid4())
            await self.session_store.create_session(session_id)
            logger.info(f"Auto-created session: {session_id}")
        return session_id

    def _deduplicate_results(self, results: list) -> list:
        """Remove duplicate results based on content."""
        seen_contents = set()
        unique_results = []
        for r in results:
            if r.content not in seen_contents:
                seen_contents.add(r.content)
                unique_results.append(r)
        return unique_results

    async def _build_prompt(self, session_id: str | None, question: str, context: str) -> str:
        """Build prompt with conversation history if session exists."""
        if session_id and self.session_store and self.session_store.is_connected:
            return await self._build_prompt_with_history(
                session_id, question, context
            )
        return f"参考资料：\n{context}\n\n问题：{question}"

    async def _save_to_session(
        self, session_id: str, question: str, answer: str, unique_results: list
    ):
        """Save conversation to session."""
        if session_id and self.session_store and self.session_store.is_connected:
            try:
                await self.session_store.add_message(session_id, "user", question)
                await self.session_store.add_message(
                    session_id,
                    "assistant",
                    answer,
                    metadata={
                        "sources": [
                            {"file": r.source_file, "score": r.score}
                            for r in unique_results
                        ]
                    },
                )
                logger.info(f"Conversation saved to session: {session_id}")
            except Exception as e:
                logger.error(f"Failed to save conversation: {e}")

    async def _build_prompt_with_history(
        self, session_id: str, question: str, context: str
    ) -> str:
        """Build prompt including recent conversation history."""
        try:
            # Get recent conversation history (last 5 turns)
            history = await self.session_store.get_recent_messages(
                session_id, turns=5
            )

            if not history:
                return f"参考资料：\n{context}\n\n问题：{question}"

            # Build conversation history string
            history_str = ""
            for msg in history:
                role_label = "用户" if msg["role"] == "user" else "助手"
                history_str += f"{role_label}：{msg['content']}\n\n"

            # Combine history with context and current question
            prompt = (
                f"以下是之前的对话历史：\n"
                f"{history_str}"
                f"参考资料：\n{context}\n\n"
                f"当前问题：{question}\n\n"
                f"请结合对话历史和参考资料回答当前问题。"
            )

            logger.debug(f"Prompt built with {len(history)} history messages")
            return prompt

        except Exception as e:
            logger.error(f"Failed to build prompt with history: {e}")
            # Fallback to simple prompt
            return f"参考资料：\n{context}\n\n问题：{question}"

    async def create_session(self, session_id: str | None = None) -> dict:
        """Create a new conversation session."""
        if not self.session_store or not self.session_store.is_connected:
            raise ConnectionError("Redis session store is not available")

        if not session_id:
            import uuid

            session_id = str(uuid.uuid4())

        return await self.session_store.create_session(session_id)

    async def get_session_history(self, session_id: str) -> list[dict]:
        """Get conversation history for a session."""
        if not self.session_store or not self.session_store.is_connected:
            raise ConnectionError("Redis session store is not available")

        raw_history = await self.session_store.get_history(session_id)

        history = []
        for msg in raw_history:
            transformed = {
                "role": msg["role"],
                "content": msg["content"],
                "timestamp": msg.get("timestamp", ""),
                "sources": msg.get("metadata", {}).get("sources", None),
            }
            history.append(transformed)

        return history

    async def delete_session(self, session_id: str) -> bool:
        """Delete a conversation session."""
        if not self.session_store or not self.session_store.is_connected:
            raise ConnectionError("Redis session store is not available")

        return await self.session_store.delete_session(session_id)

    async def list_sessions(self) -> dict:
        """List all active sessions."""
        if not self.session_store or not self.session_store.is_connected:
            raise ConnectionError("Redis session store is not available")

        sessions = await self.session_store.list_sessions()
        return {
            "total_sessions": len(sessions),
            "sessions": sessions,
        }

    async def clear_all_sessions(self) -> int:
        """Clear all conversation sessions."""
        if not self.session_store or not self.session_store.is_connected:
            raise ConnectionError("Redis session store is not available")

        return await self.session_store.clear_all_sessions()
