from app.config import settings
from app.api.schemas import BuildIndexResponse, IndexStatusResponse
from app.services.embedding import EmbeddingService
from app.storage.faiss_store import FaissStore
from app.storage.doc_store import DocStore
from app.utils.text_splitter import MarkdownSplitter
from app.utils.logger import get_logger

logger = get_logger(__name__)


class IndexService:
    def __init__(self, faiss_store: FaissStore, doc_store: DocStore, embedding: EmbeddingService):
        self.faiss = faiss_store
        self.doc_store = doc_store
        self.embedding = embedding
        self.splitter = MarkdownSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap
        )

    async def build_index(self, rebuild: bool = False) -> BuildIndexResponse:
        md_files = self.splitter.scan_md_files(settings.kb_path)
        if not md_files:
            logger.warning("No .md files found in knowledge base directory")
            return BuildIndexResponse(
                status="warning",
                total_chunks=0,
                files_processed=0
            )

        logger.info(f"Found {len(md_files)} md files, processing...")
        chunks = []
        for f in md_files:
            file_chunks = self.splitter.split_file(f)
            chunks.extend(file_chunks)
        logger.info(f"Split into {len(chunks)} chunks")

        contents = [c["content"] for c in chunks]
        vectors = await self.embedding.encode(contents)
        logger.info(f"Embedded {len(vectors)} vectors")

        if rebuild:
            self.faiss.reset()

        self.faiss.add_vectors(vectors, chunks)
        self.faiss.save(settings.idx_path)
        self.doc_store.save(chunks)

        logger.info(f"Index built: {len(chunks)} chunks from {len(md_files)} files")
        return BuildIndexResponse(
            status="success",
            total_chunks=len(chunks),
            files_processed=len(md_files)
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
