import json
from datetime import datetime
from pathlib import Path


class DocStore:
    def __init__(self, base_path: str | Path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._meta_file = self.base_path / "doc_metadata.json"

    def save(self, chunks: list[dict]) -> None:
        data = {
            "chunks": [
                {
                    "id": i,
                    "source_file": c["source_file"],
                    "chunk_index": c["chunk_index"],
                    "content": c["content"]
                }
                for i, c in enumerate(chunks)
            ],
            "last_build_time": datetime.now().isoformat(),
            "total_chunks": len(chunks)
        }
        with open(self._meta_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self) -> dict | None:
        if not self._meta_file.exists():
            return None
        with open(self._meta_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_file_list(self) -> list[str]:
        data = self.load()
        if not data:
            return []
        files = sorted(set(c["source_file"] for c in data["chunks"]))
        return files

    def get_status(self) -> dict:
        data = self.load()
        if not data:
            return {
                "index_exists": False,
                "total_chunks": 0,
                "last_build_time": None,
                "knowledge_base_files": []
            }
        return {
            "index_exists": True,
            "total_chunks": data["total_chunks"],
            "last_build_time": data["last_build_time"],
            "knowledge_base_files": self.get_file_list()
        }