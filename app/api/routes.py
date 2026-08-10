from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    QueryRequest, QueryResponse,
    BuildIndexRequest, BuildIndexResponse,
    IndexStatusResponse, HealthResponse
)
from app.exceptions import (
    IndexNotFoundError, EmbeddingAPIError,
    LLMAPIError, IndexBuildError
)
from app.services.rag_service import RAGService
from app.services.index_service import IndexService
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


def _get_rag() -> RAGService:
    from app.main import rag_service
    if rag_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return rag_service


def _get_indexer() -> IndexService:
    from app.main import index_service
    if index_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return index_service


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    rag = _get_rag()
    try:
        return await rag.query(request.question)
    except IndexNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (EmbeddingAPIError, LLMAPIError) as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/build", response_model=BuildIndexResponse)
async def build_index(request: BuildIndexRequest):
    indexer = _get_indexer()
    try:
        return await indexer.build_index(rebuild=request.rebuild)
    except IndexBuildError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception(f"Index build failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index/status", response_model=IndexStatusResponse)
async def index_status():
    indexer = _get_indexer()
    return indexer.get_status()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    from app.main import faiss_store, embedding_service, llm_client
    return HealthResponse(
        status="ok",
        faiss_index="loaded" if faiss_store and faiss_store.is_loaded() else "empty",
        embedding_service="available" if embedding_service else "unavailable",
        llm_service="available" if llm_client else "unavailable"
    )