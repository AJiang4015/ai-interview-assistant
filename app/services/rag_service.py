import asyncio
import json
import uuid

from app.config import settings
from app.observability import tracer
from app.api.schemas import QueryResponse, SourceInfo
from app.services import monitor, session_cost
from app.services.eval_monitor import EvalMonitor
from app.services.embedding import EmbeddingService
from app.services.llm_client import LLMClient
from app.storage.faiss_store import FaissStore
from app.storage.session_store import SessionStore
from app.storage.search_store import SearchStore
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
        search_store: SearchStore | None = None,
        query_rewriter=None,      # QueryRewriteService | None
        hybrid_retriever=None,    # HybridRetriever | None
        reranker=None,            # RerankService | None
        cache_service=None,       # ResponseCache | None
    ):
        self.faiss = faiss_store
        self.embedding = embedding
        self.llm = llm
        self.session_store = session_store
        self.search_store = search_store
        self.query_rewriter = query_rewriter
        self.hybrid_retriever = hybrid_retriever
        self.reranker = reranker
        self.cache = cache_service
        self.top_k = settings.top_k
        self.eval_monitor = EvalMonitor(self.llm)

    async def _eval_stream(self, query: str, context: str, answer: str,
                           session_id: str) -> None:
        """后台执行流式路径的幻觉评估与指标记账，失败不中断主流程。"""
        try:
            halluc = await self.eval_monitor.maybe_eval(
                query, context, answer, session_id=session_id
            )
            if halluc:
                logger.error(f"会话 {session_id} 检测到幻觉")
            if session_cost.is_over_budget(session_id):
                logger.warning(f"会话 {session_id} Token 成本超预算")
            monitor.record_faithfulness(bool(halluc))
        except Exception:
            logger.exception(f"流式幻觉评估失败：{session_id}")

    async def query(
        self, question: str, session_id: str | None = None
    ) -> QueryResponse:
        if not self.faiss.is_loaded():
            raise IndexNotFoundError("索引未构建，请先调用 /api/index/build")
        logger.info(f"Processing query: {question[:50]}... (session: {session_id})")
        session_id = await self._ensure_session(session_id)

        # 1. 查询改写
        retrieval_query = question
        if self.query_rewriter and self.query_rewriter.enabled:
            retrieval_query = await self.query_rewriter.rewrite(question)

        # 2. 混合检索
        if self.hybrid_retriever and self.hybrid_retriever.enabled:
            raw_results = await self.hybrid_retriever.retrieve(retrieval_query, top_k=20)
        else:
            query_vector = await self.embedding.encode([retrieval_query])
            if query_vector.size == 0:
                raise ValueError("Failed to encode question")
            raw_results = self.faiss.search(query_vector[0], self.top_k)

        if not raw_results:
            return QueryResponse(
                answer="抱歉，我在知识库中没有找到相关内容。请尝试重新构建索引或添加更多相关文档。",
                sources=[], retrieved_chunks=[], session_id=session_id,
            )

        # 3. 重排序
        if self.reranker and self.reranker.enabled:
            docs = [r.content for r in raw_results]
            reranked = await self.reranker.rerank(retrieval_query, docs, top_k=self.top_k)
            content_to_result = {r.content: r for r in raw_results}
            final_results = []
            for rr in reranked:
                if rr.content in content_to_result:
                    final_results.append(content_to_result[rr.content])
        else:
            final_results = raw_results[:self.top_k]

        unique_results = self._deduplicate_results(final_results)
        context = "\n---\n".join([r.content for r in unique_results])
        prompt = await self._build_prompt(session_id, question, context)
        if tracer is not None:
            with tracer.start_as_current_span("rag.llm_call") as span:
                answer = await self.llm.chat(prompt, SYSTEM_PROMPT, session_id=session_id)
                span.set_attribute("llm.prompt_chars", len(prompt))
                span.set_attribute("llm.answer_chars", len(answer) if answer else 0)
        else:
            answer = await self.llm.chat(prompt, SYSTEM_PROMPT, session_id=session_id)

        if session_cost.is_over_budget(session_id):
            logger.warning(f"会话 {session_id} Token 成本超预算")

        try:
            halluc = await self.eval_monitor.maybe_eval(
                question, context, answer, session_id=session_id
            )
            if halluc:
                logger.error(f"会话 {session_id} 检测到幻觉")
            monitor.record_faithfulness(bool(halluc))
        except Exception:
            logger.exception(f"幻觉评估失败：{session_id}")

        await self._save_to_session(session_id, question, answer, unique_results)

        sources = [
            SourceInfo(file=r.source_file, chunk_index=r.chunk_index, score=r.score)
            for r in unique_results
        ]
        return QueryResponse(
            answer=answer, sources=sources,
            retrieved_chunks=[r.content for r in unique_results],
            session_id=session_id,
        )

    async def stream_query(
        self, question: str, session_id: str | None = None
    ):
        if not self.faiss.is_loaded():
            raise IndexNotFoundError("索引未构建，请先调用 /api/index/build")

        logger.info(f"Processing stream query: {question[:50]}... (session: {session_id})")
        session_id = await self._ensure_session(session_id)
        yield self._sse_event("session", {"session_id": session_id})

        # 1. 查询改写
        retrieval_query = question
        if self.query_rewriter and self.query_rewriter.enabled:
            retrieval_query = await self.query_rewriter.rewrite(question)
            logger.info(f"Rewritten query: '{question[:30]}' -> '{retrieval_query[:50]}'")

        # 2. 检查缓存
        if self.cache and self.cache.available:
            msg_count = await self._get_message_count(session_id)
            cache_key = self.cache.make_key(question, session_id, msg_count)
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for session {session_id}")
                yield self._sse_event("retrieval", {
                    "sources": cached["sources"],
                    "chunks": [],
                })
                yield self._sse_event("done", {
                    "answer": cached["answer"],
                    "sources": cached["sources"],
                    "session_id": session_id,
                })
                return

        # 3. 混合检索
        if self.hybrid_retriever and self.hybrid_retriever.enabled:
            raw_results = await self.hybrid_retriever.retrieve(retrieval_query, top_k=20)
        else:
            query_vector = await self.embedding.encode([retrieval_query])
            if query_vector.size == 0:
                yield self._sse_event("error", {"message": "Failed to encode question"})
                return
            raw_results = self.faiss.search(query_vector[0], self.top_k)

        if not raw_results:
            logger.warning("No relevant chunks found")
            yield self._sse_event("retrieval", {"sources": [], "chunks": []})
            yield self._sse_event("done", {
                "answer": "抱歉，我在知识库中没有找到相关内容。请尝试重新构建索引或添加更多相关文档。",
                "sources": [],
                "session_id": session_id,
            })
            return

        # 4. 重排序
        if self.reranker and self.reranker.enabled:
            docs = [r.content for r in raw_results]
            reranked = await self.reranker.rerank(retrieval_query, docs, top_k=self.top_k)
            # 用重排序结果替换原始结果
            final_results = []
            content_to_result = {r.content: r for r in raw_results}
            for rr in reranked:
                if rr.content in content_to_result:
                    orig = content_to_result[rr.content]
                    final_results.append(orig)
        else:
            final_results = raw_results[:self.top_k]

        unique_results = self._deduplicate_results(final_results)

        sources_data = [
            {"file": r.source_file, "chunk_index": r.chunk_index, "score": r.score}
            for r in unique_results
        ]
        yield self._sse_event("retrieval", {
            "sources": sources_data,
            "chunks": [r.content for r in unique_results],
        })

        # 5. LLM 生成
        context = "\n---\n".join([r.content for r in unique_results])
        prompt = await self._build_prompt(session_id, question, context)

        answer_parts = []
        try:
            async for chunk in self.llm.chat_stream(prompt, SYSTEM_PROMPT, session_id=session_id):
                answer_parts.append(chunk)
                yield self._sse_event("token", {"content": chunk})
        except Exception as e:
            logger.error(f"Stream generation failed: {e}")
            yield self._sse_event("error", {"message": str(e)})
            return

        answer = "".join(answer_parts)

        if session_cost.is_over_budget(session_id):
            logger.warning(f"会话 {session_id} Token 成本超预算")

        # 后台幻觉评估，不阻塞 SSE
        asyncio.create_task(self._eval_stream(
            query=question, context=context, answer=answer, session_id=session_id,
        ))

        await self._save_to_session(session_id, question, answer, unique_results)

        # 6. 写入缓存
        if self.cache and self.cache.available:
            msg_count = await self._get_message_count(session_id)
            cache_key = self.cache.make_key(question, session_id, msg_count)
            await self.cache.set(cache_key, answer, sources_data)

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
            if self.search_store:
                self.search_store.index_session(session_id)
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

    async def _get_message_count(self, session_id: str) -> int:
        """获取会话的消息数量，用于缓存 key 计算。"""
        if not self.session_store or not self.session_store.is_connected:
            return 0
        try:
            history = await self.session_store.get_history(session_id)
            return len(history)
        except Exception:
            return 0

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
                # 同步写入 SQLite 搜索索引
                if self.search_store:
                    self.search_store.index_message(session_id, "user", question)
                    self.search_store.index_message(session_id, "assistant", answer)
                    # 用用户提问更新会话标题（截断 30 字符，与 Redis 逻辑一致）
                    title = question[:30] + "..." if len(question) > 30 else question
                    self.search_store.index_session(session_id, title=title)
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

        result = await self.session_store.create_session(session_id)
        if self.search_store:
            self.search_store.index_session(session_id)
        return result

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

        result = await self.session_store.delete_session(session_id)
        if self.search_store:
            self.search_store.delete_session(session_id)
        return result

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

        result = await self.session_store.clear_all_sessions()
        if self.search_store:
            self.search_store.clear_all()
        return result
