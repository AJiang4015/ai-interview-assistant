import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from app.services.index_service import IndexService


def _make_service():
    faiss = type("F", (), {
        "aadd_vectors": AsyncMock(),
        "save": Mock(),
        "reset": Mock(),
        "is_loaded": Mock(return_value=False),
    })()
    doc_store = type("D", (), {
        "save": Mock(),
        "append": Mock(),
        "get_status": Mock(return_value={
            "index_exists": False, "total_chunks": 0,
            "last_build_time": None, "knowledge_base_files": [],
        }),
    })()
    embedding = type("E", (), {"encode": AsyncMock(return_value=[[0.1] * 8])})()
    return IndexService(faiss_store=faiss, doc_store=doc_store,
                        embedding=embedding)


def test_pipeline_methods_exist():
    svc = object.__new__(IndexService)
    assert hasattr(svc, "rebuild_index_pipeline")
    assert hasattr(svc, "add_document_pipeline")


def test_rebuild_index_pipeline_ingests_and_persists_real_chunks():
    svc = _make_service()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "a.md"
        p.write_text("# 标题\n这是一段足够长的用于验证切分与入库的正文内容，Java HashMap 相关描述。",
                     encoding="utf-8")
        svc.splitter.scan_md_files = lambda directory: [p]

        async def go():
            return await svc.rebuild_index_pipeline()

        rep = asyncio.run(go())
    assert rep["status"] == "success"
    assert rep["total_chunks"] >= 1
    assert rep["files_processed"] == 1
    assert rep["failed_docs"] == []
    assert svc.faiss.reset.called
    assert svc.faiss.save.called
    assert svc.doc_store.save.called
    # doc_store 收到的是真实 chunk（非伪造元数据）
    saved = svc.doc_store.save.call_args.args[0]
    assert saved and saved[0]["source_file"] == "a.md"
    assert saved[0]["content"]


def test_add_document_pipeline_ingests_single_file():
    svc = _make_service()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "b.md"
        p.write_text("# 新增\n这是增量入库文档的用于测试切分的正文内容，长度足以产生至少一个块。",
                     encoding="utf-8")

        async def go():
            return await svc.add_document_pipeline(p)

        rep = asyncio.run(go())
    assert rep["status"] == "success"
    assert rep["files_processed"] == 1
    assert rep["progress"]["processed"] == 1
    assert svc.faiss.save.called
    assert svc.doc_store.append.called
    saved = svc.doc_store.append.call_args.args[0]
    assert saved and saved[0]["source_file"] == "b.md"


def test_add_document_pipeline_missing_file_returns_error():
    svc = _make_service()

    async def go():
        return await svc.add_document_pipeline(Path("nonexistent_xyz.md"))

    rep = asyncio.run(go())
    assert rep["status"] == "error"
    assert rep["total_chunks"] == 0
    assert rep["files_processed"] == 0
    assert not svc.faiss.save.called
    assert not svc.doc_store.append.called