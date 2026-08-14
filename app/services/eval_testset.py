import json
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger(__name__)

GEN_PROMPT = """你正在为 RAG 知识库构建评测集。请根据下面这段文档内容，生成一个用户可能提出的问题。
文档来源：{source}
文档内容：{chunk}

请只以 JSON 输出：{{"question": "问题"}}
"""


class TestSetGenerator:
    def __init__(self, llm, testset_path: str = "data/eval_testset.json",
                 chunks: list | None = None, evaluate_every: int = 1):
        self.llm = llm
        self.testset_path = Path(testset_path)
        self.chunks = chunks or []
        self.evaluate_every = evaluate_every

    def load(self):
        if not self.testset_path.exists():
            return []
        with open(self.testset_path, encoding="utf-8") as f:
            return json.load(f)

    def clear(self):
        if self.testset_path.exists():
            self.testset_path.unlink()

    async def generate(self, limit: int | None = None):
        existing = self.load()
        seen_sources = {e["source_file"] for e in existing}
        created = 0
        for chunk in self.chunks:
            if limit is not None and created >= limit:
                break
            src = chunk.get("source") or chunk.get("source_file") or "unknown"
            if src in seen_sources:
                continue
            try:
                text = await self.llm.chat(GEN_PROMPT.format(source=src, chunk=chunk["content"]))
                parsed = json.loads(text) if text.strip().startswith("{") else {}
                question = parsed.get("question", "")
            except Exception as e:
                logger.warning(f"Testset gen failed for {src}: {e}")
                question = ""
            if not question:
                continue
            existing.append({
                "question": question,
                "expected_answer": chunk["content"],
                "expected_source": src,
                "source_file": src,
            })
            seen_sources.add(src)
            created += 1
        with open(self.testset_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        return {"total": len(existing), "created": created}