import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Body, Query, UploadFile, File
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    QueryRequest, QueryResponse,
    BuildIndexRequest, BuildIndexResponse,
    IndexStatusResponse, HealthResponse,
    CreateSessionRequest, SessionResponse,
    SessionListResponse, SessionHistoryResponse,
    DeleteSessionResponse, ClearSessionsResponse,
    FileInfo, FileListResponse, FileUploadResponse, FileDeleteResponse,
    SearchResultItem, SearchResponse,
)
from app.exceptions import (
    IndexNotFoundError, EmbeddingAPIError,
    LLMAPIError, IndexBuildError
)
from app.services.rag_service import RAGService
from app.services.index_service import IndexService
from app.utils.logger import get_logger
from app.config import settings

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


async def _rebuild_index_async():
    """后台异步重建索引，不阻塞响应"""
    try:
        indexer = _get_indexer()
        result = await indexer.build_index(rebuild=True)
        logger.info(f"Background index rebuild completed: {result.total_chunks} chunks, {result.files_processed} files")
    except Exception as e:
        logger.exception(f"Background index rebuild failed: {e}")


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


# ==================== File Management ====================

ALLOWED_EXTENSIONS = {".md", ".pdf", ".docx"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.get("/files", response_model=FileListResponse)
async def list_files():
    """列出知识库中的所有文件"""
    kb_path = settings.kb_path
    if not kb_path.exists():
        return FileListResponse(total_files=0, files=[])

    files = []
    for entry in kb_path.iterdir():
        if not entry.is_file():
            continue
        # 过滤 Word 临时文件
        if entry.name.startswith("~$"):
            continue
        ext = entry.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        stat = entry.stat()
        files.append(FileInfo(
            filename=entry.name,
            size=stat.st_size,
            modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            file_type=ext.lstrip(".")
        ))

    return FileListResponse(total_files=len(files), files=files)


@router.post("/files/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """上传文件到知识库，上传后自动重建索引"""
    # 校验文件扩展名
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}，仅支持 {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # 过滤 Word 临时文件
    if filename.startswith("~$"):
        raise HTTPException(status_code=400, detail="不支持上传 Word 临时文件")

    kb_path = settings.kb_path
    kb_path.mkdir(parents=True, exist_ok=True)
    file_path = kb_path / filename

    # 写入文件
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"文件大小超过限制 ({MAX_FILE_SIZE // 1024 // 1024}MB)")

    with open(file_path, "wb") as f:
        f.write(content)

    logger.info(f"File uploaded: {filename} ({len(content)} bytes)")

    # 后台异步重建索引
    asyncio.create_task(_rebuild_index_async())
    return FileUploadResponse(
        success=True,
        filename=filename,
        message="文件上传成功，索引正在后台重建...",
        index_rebuilt=False
    )


@router.delete("/files/{filename}", response_model=FileDeleteResponse)
async def delete_file(filename: str):
    """删除知识库中的指定文件，删除后自动重建索引"""
    # 防止路径穿越
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    kb_path = settings.kb_path
    file_path = kb_path / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")

    try:
        file_path.unlink()
        logger.info(f"File deleted: {filename}")
    except Exception as e:
        logger.exception(f"Failed to delete file: {e}")
        raise HTTPException(status_code=500, detail=f"删除文件失败: {e}")

    # 后台异步重建索引
    asyncio.create_task(_rebuild_index_async())
    return FileDeleteResponse(
        success=True,
        filename=filename,
        message="文件已删除，索引正在后台重建...",
        index_rebuilt=False
    )


# ==================== Search ====================

@router.get("/search", response_model=SearchResponse)
async def search_messages(q: str = Query(..., min_length=1)):
    """跨会话搜索历史对话"""
    from app.main import search_store
    if search_store is None:
        raise HTTPException(status_code=503, detail="搜索服务未初始化")

    results = search_store.search(q)

    # 构建带上下文的关键词高亮片段
    search_results = []
    for r in results:
        content = r["content"]
        lower_content = content.lower()
        lower_keyword = q.lower()
        pos = lower_content.find(lower_keyword)

        if pos >= 0:
            start = max(0, pos - 40)
            end = min(len(content), pos + len(q) + 40)
            snippet = content[start:end]
            if start > 0:
                snippet = "..." + snippet
            if end < len(content):
                snippet = snippet + "..."
        else:
            snippet = content[:80] + "..." if len(content) > 80 else content

        search_results.append(SearchResultItem(
            session_id=r["session_id"],
            title=r.get("title"),
            role=r["role"],
            content=content,
            content_snippet=snippet,
            created_at=r.get("created_at")
        ))

    return SearchResponse(query=q, total=len(search_results), results=search_results)
