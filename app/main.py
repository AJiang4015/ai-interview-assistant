from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api.routes import router
from app.api.auth import router as auth_router
from app.api.interview import router as interview_router
from app.services.embedding import EmbeddingService
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService
from app.services.index_service import IndexService
from app.services.auth_service import AuthService
from app.services.interview_service import InterviewService
from app.services.resume_parser import ResumeParser
from app.api.deep_dive import router as deep_dive_router
from app.services.deep_dive_service import DeepDiveService
from app.storage.deep_dive_store import DeepDiveStore
from app.services.topic_tracker import TopicTracker
from app.storage.faiss_store import FaissStore
from app.storage.doc_store import DocStore
from app.storage.session_store import SessionStore
from app.storage.search_store import SearchStore
from app.storage.user_store import UserStore
from app.storage.interview_store import InterviewStore
from app.utils.logger import get_logger
from app.services.query_rewrite import QueryRewriteService
from app.services.rerank_service import RerankService
from app.services.retrieval_service import HybridRetriever
from app.services.cache_service import ResponseCache

logger = get_logger(__name__)

faiss_store: FaissStore | None = None
doc_store: DocStore | None = None
embedding_service: EmbeddingService | None = None
llm_client: LLMClient | None = None
rag_service: RAGService | None = None
index_service: IndexService | None = None
session_store: SessionStore | None = None
search_store: SearchStore | None = None
user_store: UserStore | None = None
auth_service: AuthService | None = None
interview_store: InterviewStore | None = None
interview_service: InterviewService | None = None
resume_parser: ResumeParser | None = None
query_rewrite_service: QueryRewriteService | None = None
hybrid_retriever: HybridRetriever | None = None
rerank_service: RerankService | None = None
response_cache: ResponseCache | None = None
deep_dive_service: DeepDiveService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global faiss_store, doc_store, embedding_service, llm_client, rag_service
    global index_service, session_store, search_store, user_store, auth_service
    global interview_store, interview_service, resume_parser
    global query_rewrite_service, hybrid_retriever, rerank_service, response_cache
    global deep_dive_service

    logger.info("Initializing services...")

    faiss_store = FaissStore()
    doc_store = DocStore(settings.idx_path)
    embedding_service = EmbeddingService()
    llm_client = LLMClient()

    # Initialize Redis session store
    session_store = SessionStore(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password or None,
        ttl_seconds=settings.session_ttl,
        max_history_turns=settings.max_history_turns,
    )
    await session_store.connect()

    # Initialize Redis user store
    user_store = UserStore(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password or None,
    )
    await user_store.connect()

    auth_service = AuthService(user_store)

    # 初始化 SQLite 搜索存储
    search_store = SearchStore()

    # 查询改写
    query_rewrite_service = QueryRewriteService(
        llm=llm_client,
        enabled=settings.enable_query_rewrite,
    )

    # 混合检索 + BM25
    hybrid_retriever = HybridRetriever(
        faiss_store=faiss_store,
        embedding=embedding_service,
        bm25_index_path=settings.bm25_index_path,
        enabled=settings.enable_hybrid_search,
    )
    hybrid_retriever.load_bm25()

    # 重排序
    rerank_service = RerankService(
        api_key=settings.siliconflow_api_key,
        model_name=settings.rerank_model,
        enabled=settings.enable_rerank,
    )

    # 响应缓存
    response_cache = ResponseCache(
        session_store=session_store,
        ttl=settings.cache_ttl,
    )

    index_service = IndexService(faiss_store, doc_store, embedding_service, hybrid_retriever=hybrid_retriever)
    rag_service = RAGService(
        faiss_store, embedding_service, llm_client,
        session_store=session_store,
        search_store=search_store,
        query_rewriter=query_rewrite_service,
        hybrid_retriever=hybrid_retriever,
        reranker=rerank_service,
        cache_service=response_cache,
    )

    # Initialize resume parser
    resume_parser = ResumeParser(llm=llm_client)

    # Initialize interview service
    interview_store = InterviewStore()
    topic_tracker = TopicTracker(interview_store=interview_store)
    interview_service = InterviewService(
        interview_store, llm_client, faiss_store, embedding_service,
        resume_parser=resume_parser,
        topic_tracker=topic_tracker,
    )

    global deep_dive_service
    deep_dive_service = DeepDiveService(store=DeepDiveStore(), llm=llm_client)

    idx_path = Path(settings.idx_path)
    if (idx_path / "index.faiss").exists():
        faiss_store.load(settings.idx_path)
        logger.info(f"Loaded existing index with {faiss_store.size} vectors")
    else:
        logger.info("No existing index found, index is empty")

    if session_store.is_connected:
        logger.info("Redis session store connected successfully")
    else:
        logger.warning("Redis session store not available, session features disabled")

    if user_store.is_connected:
        logger.info("Redis user store connected successfully")
    else:
        logger.warning("Redis user store not available, auth features disabled")

    logger.info("Services initialized successfully")
    yield

    # Cleanup
    logger.info("Shutting down...")
    if session_store and session_store.is_connected:
        await session_store.close()
    if user_store and user_store.is_connected:
        await user_store.close()
    logger.info("Redis connections closed")


app = FastAPI(
    title="Java 程序员智能面试助手",
    description="基于 RAG + LLM 的 Java/后端技术问答系统",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(auth_router)
app.include_router(interview_router)
app.include_router(deep_dive_router)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
