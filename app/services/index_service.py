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
    ):
        self.faiss = faiss_store
        self.doc_store = doc_store
        self.embedding = embedding
        self.hybrid_retriever = hybrid_retriever  # 可选
        self.splitter = MarkdownSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap
        )
        self._pipeline_obj = None

    async def build_index(self, rebuild: bool = False) -> BuildIndexResponse:
        kb_files = self.splitter.scan_md_files(settings.kb_path)
        if not kb_files:
            logger.warning("No document files found in knowledge base directory")
            return BuildIndexResponse(
                status="warning",
                total_chunks=0,
                files_processed=0
            )

        logger.info(f"Found {len(kb_files)} files, processing...")
        chunks = []
        failed_files = []
        for f in kb_files:
            try:
                file_chunks = self.splitter.split_file(f)
                if file_chunks:
                    chunks.extend(file_chunks)
                else:
                    logger.warning(f"No chunks produced for file: {f.name}")
                    failed_files.append(f.name)
            except Exception as e:
                logger.error(f"Failed to process {f.name}: {e}")
                failed_files.append(f.name)

        if not chunks:
            logger.warning("No valid chunks produced from any file")
            return BuildIndexResponse(
                status="warning",
                total_chunks=0,
                files_processed=len(kb_files) - len(failed_files)
            )

        logger.info(f"Split into {len(chunks)} chunks from {len(kb_files) - len(failed_files)} files")

        contents = [c["content"] for c in chunks]
        vectors = await self.embedding.encode(contents)
        logger.info(f"Embedded {len(vectors)} vectors")

        if rebuild:
            self.faiss.reset()

        self.faiss.add_vectors(vectors, chunks)
        self.faiss.save(settings.idx_path)
        self.doc_store.save(chunks)

        # 同步构建 BM25 索引
        if self.hybrid_retriever:
            bm25_docs = []
            for idx, c in enumerate(chunks):
                doc = {**c, "_id": idx}
                bm25_docs.append(doc)
            self.hybrid_retriever.save_bm25(bm25_docs)

        status_msg = f"Index built: {len(chunks)} chunks from {len(kb_files) - len(failed_files)} files"
        if failed_files:
            status_msg += f" (failed: {', '.join(failed_files)})"
        logger.info(status_msg)

        return BuildIndexResponse(
            status="success",
            total_chunks=len(chunks),
            files_processed=len(kb_files) - len(failed_files)
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
        """增量索引单个文件：拆分→嵌入→追加到已有索引，不全量重建。

        适用于上传新文档时，避免全量重建造成的向量重复与耗时。
        """
        file_path = Path(file_path)
        if not file_path.exists():
            logger.warning(f"add_document: file not found {file_path}")
            return BuildIndexResponse(status="error", total_chunks=0, files_processed=0)

        try:
            chunks = self.splitter.split_file(file_path)
        except Exception as e:
            logger.error(f"Failed to split file {file_path.name}: {e}")
            return BuildIndexResponse(status="error", total_chunks=0, files_processed=0)

        if not chunks:
            logger.warning(f"No chunks produced for file: {file_path.name}")
            return BuildIndexResponse(status="warning", total_chunks=0, files_processed=0)

        contents = [c["content"] for c in chunks]
        vectors = await self.embedding.encode(contents)
        logger.info(f"add_document: embedded {len(vectors)} vectors for {file_path.name}")

        self.faiss.add_vectors(vectors, chunks)
        self.faiss.save(settings.idx_path)
        self.doc_store.append(chunks)

        # 基于 faiss 全量元数据重建 BM25（BM25 需整体重建）
        if self.hybrid_retriever:
            all_meta = self.faiss.get_all_metadata()
            bm25_docs = [{"_id": m.get("_id", i), **m} for i, m in enumerate(all_meta)]
            self.hybrid_retriever.save_bm25(bm25_docs)

        logger.info(f"add_document: indexed {len(chunks)} chunks from {file_path.name}")
        return BuildIndexResponse(
            status="success",
            total_chunks=len(chunks),
            files_processed=1,
        )

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
        return rep

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
        return rep
