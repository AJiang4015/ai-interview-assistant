from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.api.routes import router
from app.services.embedding import EmbeddingService
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService
from app.services.index_service import IndexService
from app.storage.faiss_store import FaissStore
from app.storage.doc_store import DocStore
from app.utils.logger import get_logger

logger = get_logger(__name__)

faiss_store: FaissStore | None = None
doc_store: DocStore | None = None
embedding_service: EmbeddingService | None = None
llm_client: LLMClient | None = None
rag_service: RAGService | None = None
index_service: IndexService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global faiss_store, doc_store, embedding_service, llm_client, rag_service, index_service

    logger.info("Initializing services...")

    faiss_store = FaissStore()
    doc_store = DocStore(settings.idx_path)
    embedding_service = EmbeddingService()
    llm_client = LLMClient()

    index_service = IndexService(faiss_store, doc_store, embedding_service)
    rag_service = RAGService(faiss_store, embedding_service, llm_client)

    idx_path = Path(settings.idx_path)
    if (idx_path / "index.faiss").exists():
        faiss_store.load(settings.idx_path)
        logger.info(f"Loaded existing index with {faiss_store.size} vectors")
    else:
        logger.info("No existing index found, index is empty")

    logger.info("Services initialized successfully")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Java 程序员智能面试助手",
    description="基于 RAG + LLM 的 Java/后端技术问答系统",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
