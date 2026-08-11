import json

from fastapi import APIRouter, HTTPException, Body, Query
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    QueryRequest, QueryResponse,
    BuildIndexRequest, BuildIndexResponse,
    IndexStatusResponse, HealthResponse,
    CreateSessionRequest, SessionResponse,
    SessionListResponse, SessionHistoryResponse,
    DeleteSessionResponse, ClearSessionsResponse,
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
        return await rag.query(request.question, session_id=request.session_id)
    except IndexNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e) or "索引未构建")
    except EmbeddingAPIError as e:
        raise HTTPException(status_code=502, detail=str(e) or "Embedding 服务不可用")
    except LLMAPIError as e:
        raise HTTPException(status_code=502, detail=str(e) or "LLM 服务不可用")
    except Exception as e:
        logger.exception(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e) or "内部服务器错误")


@router.post("/query/stream")
async def query_stream(request: QueryRequest):
    """Stream query results via Server-Sent Events."""
    rag = _get_rag()

    async def event_generator():
        try:
            async for event in rag.stream_query(
                request.question, session_id=request.session_id
            ):
                yield event
        except IndexNotFoundError as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e) or '索引未构建'}, ensure_ascii=False)}\n\n"
        except EmbeddingAPIError as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e) or 'Embedding 服务不可用'}, ensure_ascii=False)}\n\n"
        except LLMAPIError as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e) or 'LLM 服务不可用'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception(f"Stream query failed: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e) or '内部服务器错误'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/index/build", response_model=BuildIndexResponse)
async def build_index(request: BuildIndexRequest = Body(default_factory=BuildIndexRequest)):
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
    from app.main import faiss_store, embedding_service, llm_client, session_store
    redis_status = "available" if session_store and session_store.is_connected else "disconnected"
    return HealthResponse(
        status="ok",
        faiss_index="loaded" if faiss_store and faiss_store.is_loaded() else "empty",
        embedding_service="available" if embedding_service else "unavailable",
        llm_service="available" if llm_client else "unavailable",
        redis_status=redis_status,
    )


# ==================== Session Management ====================

@router.post("/sessions", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest = Body(default_factory=CreateSessionRequest)):
    """Create a new conversation session."""
    rag = _get_rag()
    try:
        session = await rag.create_session(request.session_id)
        return SessionResponse(**session)
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Create session failed: {e}")
        raise HTTPException(status_code=500, detail=str(e) or "创建会话失败")


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions():
    """List all active sessions."""
    rag = _get_rag()
    try:
        result = await rag.list_sessions()
        return SessionListResponse(
            total_sessions=result["total_sessions"],
            sessions=[SessionResponse(**s) for s in result["sessions"]],
        )
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"List sessions failed: {e}")
        raise HTTPException(status_code=500, detail=str(e) or "获取会话列表失败")


@router.get("/sessions/{session_id}", response_model=SessionHistoryResponse)
async def get_session_history(session_id: str):
    """Get conversation history for a specific session."""
    rag = _get_rag()
    try:
        history = await rag.get_session_history(session_id)
        return SessionHistoryResponse(
            session_id=session_id,
            history=history,
            total_turns=len(history),
        )
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Get session history failed: {e}")
        raise HTTPException(status_code=500, detail=str(e) or "获取会话历史失败")


@router.delete("/sessions/{session_id}", response_model=DeleteSessionResponse)
async def delete_session(session_id: str):
    """Delete a specific session."""
    rag = _get_rag()
    try:
        success = await rag.delete_session(session_id)
        return DeleteSessionResponse(success=success, session_id=session_id)
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Delete session failed: {e}")
        raise HTTPException(status_code=500, detail=str(e) or "删除会话失败")


@router.delete("/sessions", response_model=ClearSessionsResponse)
async def clear_all_sessions(confirm: bool = Query(default=False)):
    """Clear all sessions (requires confirm=true)."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="请添加 confirm=true 参数以确认清空所有会话",
        )
    rag = _get_rag()
    try:
        deleted_count = await rag.clear_all_sessions()
        return ClearSessionsResponse(success=True, deleted_count=deleted_count)
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Clear sessions failed: {e}")
        raise HTTPException(status_code=500, detail=str(e) or "清空会话失败")
