import numpy as np
from rank_bm25 import BM25Okapi

from app.config import settings
from app.services.retrieval_service import RetrievalResult
from app.utils.logger import get_logger

logger = get_logger(__name__)

INDEXED = {"memory", "whoosh", "sqlite_fts"}


class SparseRetriever:
    def __init__(self, backend: str | None = None):
        self._requested = backend or settings.sparse_backend
        self._backend = self._resolve()
        self._docs: list[dict] = []
        self._bm25: BM25Okapi | None = None
        self._whoosh_idx = None
        if self._backend == "whoosh":
            self._init_whoosh()
        elif self._backend == "sqlite_fts":
            self._init_sqlite()

    def _resolve(self) -> str:
        if self._requested in ("memory", "whoosh", "sqlite_fts"):
            name = self._requested if self._can_use(self._requested) else "memory"
        else:  # auto
            for cand in ("whoosh", "sqlite_fts", "memory"):
                if self._can_use(cand):
                    name = cand
                    break
            else:
                name = "memory"
        logger.info(f"SparseRetriever backend = {name}")
        return name

    @staticmethod
    def _can_use(backend: str) -> bool:
        if backend == "whoosh":
            try:
                import whoosh  # noqa: F401
                return True
            except ImportError:
                return False
        if backend == "sqlite_fts":
            import sqlite3
            conn = sqlite3.connect(":memory:")
            try:
                conn.execute("CREATE VIRTUAL TABLE t USING FTS5(x)")
                return True
            except sqlite3.OperationalError:
                return False
        return True

    def _init_whoosh(self):
        from whoosh.index import create_in
        from whoosh.fields import Schema, TEXT, ID
        import tempfile
        schema = Schema(id=ID(stored=True), content=TEXT)
        self._whoosh_dir = tempfile.mkdtemp(prefix="sparse_")
        self._whoosh_idx = create_in(self._whoosh_dir, schema)
        self._writer = self._whoosh_idx.writer()

    def _init_sqlite(self):
        import sqlite3
        self._sqlite = sqlite3.connect(settings.bm25_index_path + ".fts.sqlite")
        self._sqlite.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks "
                             "USING FTS5(id, content UNINDEXED, payload)")

    def add_documents(self, documents: list[dict]) -> None:
        self._docs = list(documents)
        if self._backend == "memory":
            tokenized = [d["content"].lower().split() for d in documents]
            self._bm25 = BM25Okapi(tokenized)
        elif self._backend == "whoosh":
            for d in documents:
                self._writer.add_document(id=str(d["_id"]), content=d["content"])
            self._writer.commit()
        elif self._backend == "sqlite_fts":
            for d in documents:
                self._sqlite.execute(
                    "INSERT INTO chunks(id, payload) VALUES (?, ?)",
                    (str(d["_id"]), d["content"]))

    def search(self, query: str, top_k: int = 20) -> list[RetrievalResult]:
        if self._backend == "memory":
            return self._search_memory(query, top_k)
        if self._backend == "whoosh":
            return self._search_whoosh(query, top_k)
        if self._backend == "sqlite_fts":
            return self._search_sqlite(query, top_k)
        return []

    def _search_memory(self, query, top_k):
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(query.lower().split())
        order = np.argsort(scores)[::-1][:top_k]
        out = []
        for idx in order:
            if scores[idx] <= 0:
                continue
            d = self._docs[idx]
            out.append(RetrievalResult(**{
                "chunk_id": d.get("_id", idx), "source_file": d.get("source_file", ""),
                "chunk_index": d.get("chunk_index", 0), "content": d["content"],
                "score": float(scores[idx])}))
        return out

    def _search_whoosh(self, query, top_k):
        from whoosh.qparser import QueryParser
        with self._whoosh_idx.searcher() as searcher:
            parser = QueryParser("content", self._whoosh_idx.schema)
            try:
                results = searcher.search(parser.parse(query), limit=top_k)
            except Exception:
                return []
            return [
                RetrievalResult(chunk_id=int(r["id"]), source_file="",
                                chunk_index=0, content="", score=float(r.score))
                for r in results
            ]

    def _search_sqlite(self, query, top_k):
        try:
            rows = self._sqlite.execute(
                "SELECT id FROM chunks WHERE chunks MATCH ? LIMIT ?",
                (query, top_k)).fetchall()
        except Exception:
            return []
        return [
            RetrievalResult(chunk_id=int(r[0]), source_file="", chunk_index=0,
                            content="", score=1.0)
            for r in rows
        ]