import asyncio
from pathlib import Path

from app.config import settings
from app.api.schemas import BuildIndexResponse, IndexStatusResponse
from app.services.embedding import EmbeddingService
from app.storage.faiss_store import FaissStore
from app.storage.doc_store import DocStore
from app.utils.text_splitter import MarkdownSplitter
from app.utils.logger import get_logger

logger = get_logger(__name__)


class IndexService:
    def __init__(
        self,
        faiss_store: FaissStore,
        doc_store: DocStore,
        embedding: EmbeddingService,
        hybrid_retriever=None,
        sparse=None,
    ):
        self.faiss = faiss_store
        self.doc_store = doc_store
        self.embedding = embedding
        self.hybrid_retriever = hybrid_retriever  # 可选
        self.sparse = sparse  # 可选 SparseRetriever；存在则喂给稀疏检索而非 BM25
        self.splitter = MarkdownSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap
        )
        self._pipeline_obj = None
        # 进程内索引互斥锁：build / add_document 串行执行，防止并发重建/追加
        # 互相覆盖 FAISS 与 ingest_state 落盘状态（单 worker 约束下的最小并发保护）
        self._index_lock = asyncio.Lock()

    async def build_index(self, rebuild: bool = False) -> BuildIndexResponse:
        async with self._index_lock:
            return await self._build_index_locked(rebuild)

    async def _build_index_locked(self, rebuild: bool = False) -> BuildIndexResponse:
        kb_files = self.splitter.scan_md_files(settings.kb_path)
        if not kb_files:
            logger.warning("No document files found in knowledge base directory")
            return BuildIndexResponse(
                status="warning",
                total_chunks=0,
                files_processed=0
            )

        logger.info(f"Found {len(kb_files)} files, processing...")
        docs = []
        failed_files = []
        for f in kb_files:
            try:
                text = f.read_text(encoding="utf-8")
            except Exception as e:
                logger.error(f"Failed to read {f.name}: {e}")
                failed_files.append(f.name)
                continue
            docs.append((f.name, text))

        if not docs:
            logger.warning("No valid chunks produced from any file")
            return BuildIndexResponse(
                status="warning",
                total_chunks=0,
                files_processed=len(kb_files) - len(failed_files)
            )

        # I-1 兜底：索引文件被清但 ingest_state 尚存（陈旧 done）时，非 rebuild 会
        # 遇到全部 done → pending=0 → 永不重建。故 faiss 未加载/为空时强制按 rebuild
        # 处理以覆盖陈旧 state。保持正常重复 build（faiss 已加载）时幂等跳过不重复嵌入。
        if not rebuild and not self.faiss.is_loaded():
            rebuild = True

        # 走 IndexPipeline：新 Chunker + 并发 + 幂等 + 进度（内部使用 aadd_vectors 写锁）
        rep = await self._pipeline().ingest_documents(docs, rebuild=rebuild)
        chunks = rep.get("chunks") or []
        if rep["total_chunks"] > 0 and chunks:
            try:
                self.faiss.save(settings.idx_path)
                if rebuild:
                    self.doc_store.save(chunks)
                else:
                    self.doc_store.append(chunks)
            except Exception as e:
                # I-2：落盘失败不得吞掉。管道内向量已写入并标记 done，此刻 state 已 done
                # 但 faiss/doc_store 未落盘 —— 由 I-1（faiss 未加载强制 rebuild）兜底恢复。
                logger.error(f"build_index: index/doc_store persist failed: {e}")
                raise

        # 喂给稀疏检索（真实全局 _id），无 sparse 时回退到 BM25
        self._feed_sparse_or_bm25()

        status_msg = f"Index built: {rep['total_chunks']} chunks from {rep['files_processed']} files"
        if failed_files:
            status_msg += f" (failed: {', '.join(failed_files)})"
        logger.info(status_msg)

        return BuildIndexResponse(
            status="success" if rep["total_chunks"] > 0 else "warning",
            total_chunks=rep["total_chunks"],
            files_processed=rep["files_processed"]
        )

    def get_status(self) -> IndexStatusResponse:
        doc_status = self.doc_store.get_status()
        faiss_loaded = self.faiss.is_loaded() if self.faiss else False
        return IndexStatusResponse(
            index_exists=doc_status["index_exists"] and faiss_loaded,
            total_chunks=doc_status["total_chunks"],
            last_build_time=doc_status["last_build_time"],
            knowledge_base_files=doc_status["knowledge_base_files"]
        )

    async def add_document(self, file_path) -> BuildIndexResponse:
        async with self._index_lock:
            return await self._add_document_locked(file_path)

    async def _add_document_locked(self, file_path) -> BuildIndexResponse:
        """增量索引单个文件：走 IndexPipeline（新 Chunker + 并发 + 幂等），
        追加到已有索引，不全量重建（内部 aadd_vectors 写锁）。"""
        file_path = Path(file_path)
        if not file_path.exists():
            logger.warning(f"add_document: file not found {file_path}")
            return BuildIndexResponse(status="error", total_chunks=0, files_processed=0)

        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read file {file_path.name}: {e}")
            return BuildIndexResponse(status="error", total_chunks=0, files_processed=0)

        rep = await self._pipeline().ingest_documents([(file_path.name, text)], rebuild=False)
        chunks = rep.get("chunks") or []
        if rep["total_chunks"] > 0 and chunks:
            try:
                self.faiss.save(settings.idx_path)
                self.doc_store.append(chunks)
            except Exception as e:
                # I-2：落盘失败不得吞掉；state 已 done 未落盘由 I-1 兜底恢复。
                logger.error(f"add_document: index/doc_store persist failed: {e}")
                raise

        self._feed_sparse_or_bm25()

        logger.info(f"add_document: indexed {rep['total_chunks']} chunks from {file_path.name}")
        return BuildIndexResponse(
            status="success" if rep["total_chunks"] > 0 else "warning",
            total_chunks=rep["total_chunks"],
            files_processed=rep["files_processed"],
        )

    def _feed_sparse_or_bm25(self):
        """将当前 faiss 全量元数据喂给稀疏检索（真实全局 _id）；
        无 sparse 时回退到 BM25，保持向后兼容。"""
        all_meta = self.faiss.get_all_metadata()
        if self.sparse is not None:
            self.sparse.add_documents([
                {"_id": m.get("_id", i), "content": m.get("content", ""),
                 "source_file": m.get("source_file", ""), "chunk_index": m.get("chunk_index", 0)}
                for i, m in enumerate(all_meta)
            ])
        elif self.hybrid_retriever:
            bm25_docs = [{"_id": m.get("_id", i), **m} for i, m in enumerate(all_meta)]
            self.hybrid_retriever.save_bm25(bm25_docs)

    @staticmethod
    def _public_rep(rep: dict) -> dict:
        """剥离 chunks 等原始全文字段，避免公开返回泄漏文档内容。"""
        return {k: v for k, v in rep.items() if k != "chunks"}

    def _pipeline(self):
        from app.services.index_pipeline import IndexPipeline
        from app.services.chunker import Chunker
        if self._pipeline_obj is None:
            self._pipeline_obj = IndexPipeline(
                chunker=Chunker(),
                embedding=self.embedding,
                vector_store=self.faiss,
                sparse=None,  # 稀疏检索由检索侧按需加载
            )
        return self._pipeline_obj

    async def rebuild_index_pipeline(self) -> dict:
        """全量重建：扫描 KB → 走 IndexPipeline 管道入库 → 落 doc_store + 保存向量。"""
        files = self.splitter.scan_md_files(settings.kb_path)
        docs = []
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("skip %s: %s", f.name, e)
                continue
            docs.append((f.name, text))
        rep = await self._pipeline().ingest_documents(docs, rebuild=True)
        chunks = rep.get("chunks") or []
        if rep["total_chunks"] > 0 and chunks:
            self.faiss.save(settings.idx_path)
            self.doc_store.save(chunks)
        return self._public_rep(rep)

    async def add_document_pipeline(self, file_path) -> dict:
        """增量入库单个文件：走 IndexPipeline，追加 doc_store 与向量。"""
        file_path = Path(file_path)
        if not file_path.exists():
            logger.warning("add_document_pipeline: file not found %s", file_path)
            return {
                "status": "error",
                "total_chunks": 0,
                "files_processed": 0,
                "failed_docs": [],
                "progress": {"processed": 0, "total": 0},
            }
        try:
            text = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("add_document_pipeline: failed to read %s: %s",
                         file_path.name, e)
            return {
                "status": "error",
                "total_chunks": 0,
                "files_processed": 0,
                "failed_docs": [file_path.name],
                "progress": {"processed": 0, "total": 1},
            }
        rep = await self._pipeline().ingest_documents([(file_path.name, text)],
                                                       rebuild=False)
        chunks = rep.get("chunks") or []
        if rep["total_chunks"] > 0 and chunks:
            self.faiss.save(settings.idx_path)
            self.doc_store.append(chunks)
        return self._public_rep(rep)
