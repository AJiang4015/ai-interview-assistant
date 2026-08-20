"""IndexPipeline：并发 + 幂等（doc_hash 跳过 done）入库管道。

单进程约束：state 与 faiss/index 落盘假定单 worker，多 worker 部署需自行加
进程级文件锁或换外部存储。
"""
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class _IngestProgress:
    processed: int = 0
    total: int = 0
    failed: list[str] = field(default_factory=list)


class IndexPipeline:
    def __init__(self, chunker, embedding, vector_store, sparse=None,
                 state_path: str | None = None,
                 concurrent_batches: int | None = None):
        self.chunker = chunker
        self.embedding = embedding
        self.store = vector_store
        self.sparse = sparse
        self.state_path = state_path or settings.ingest_state_path
        self.sem = asyncio.Semaphore(concurrent_batches or settings.concurrent_batches)
        self._state: dict[str, str] = {}
        self._load_state()

    def _load_state(self):
        p = Path(self.state_path)
        if p.exists():
            try:
                self._state = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                self._state = {}
        elif self.state_path == ":memory:":
            self._state = {}

    def _save_state(self):
        if self.state_path == ":memory:":
            return
        Path(self.state_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.state_path).write_text(
            json.dumps(self._state, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _doc_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def _ingest_one(self, name: str, text: str, all_chunks: list[dict],
                          progress: _IngestProgress) -> list[dict]:
        async with self.sem:
            try:
                chunks = self.chunker.split_text(text, source_file=name)
                contents = [c["content"] for c in chunks]
                vectors = await self.embedding.encode(contents)
                await self.store.aadd_vectors(vectors, chunks)
            except Exception as e:
                logger.error("ingest failed for %s: %s", name, e)
                progress.failed.append(name)
                return []
            all_chunks.extend(chunks)
            progress.processed += 1
            self._state[self._doc_hash(text)] = "done"
            try:
                self._save_state()
            except Exception as e:
                logger.error("save_state failed for %s: %s", name, e)
            return chunks

    async def ingest_documents(self, documents: list[tuple[str, str]],
                               rebuild: bool = False) -> dict:
        progress = _IngestProgress(total=len(documents))
        all_chunks: list[dict] = []
        if rebuild:
            # 清空既有状态与索引由调用方/上层处理，此处仅重置本地状态
            if hasattr(self.store, "reset"):
                self.store.reset()
            self._state = {}
            try:
                self._save_state()
            except Exception as e:
                logger.error("save_state failed in rebuild: %s", e)
        pending = []
        for name, text in documents:
            key = self._doc_hash(text)
            if self._state.get(key) == "done":
                continue          # 幂等：已入库跳过
            pending.append((name, text))
        progress.total = len(pending)

        async def work(item):
            return await self._ingest_one(item[0], item[1], all_chunks, progress)

        results = await asyncio.gather(*(work(p) for p in pending),
                                       return_exceptions=False)
        new_chunks = [c for r in results for c in r]

        if self.sparse is not None and new_chunks:
            try:
                self.sparse.add_documents([
                    {"_id": c["chunk_index"], "content": c["content"],
                     "source_file": c["source_file"], "chunk_index": c["chunk_index"]}
                    for c in new_chunks])
            except Exception as e:
                logger.error("sparse add failed: %s", e)

        return {
            "status": "success" if not progress.failed else "partial",
            "total_chunks": len(all_chunks),
            "files_processed": progress.processed,
            "failed_docs": progress.failed,
            "progress": {"processed": progress.processed, "total": progress.total},
            "chunks": all_chunks,  # 本次实际入库的 chunk（供 doc_store 落盘，避免伪造）
        }