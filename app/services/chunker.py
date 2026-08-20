import hashlib
import re

from app.config import settings

_HEADER = re.compile(r"^(#{1,3})\s+(.+)$")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class Chunker:
    def __init__(self, chunk_size: int | None = None,
                 chunk_overlap: int | None = None,
                 min_chunk_size: int | None = None):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None \
            else settings.chunk_overlap
        self.min_chunk_size = min_chunk_size or settings.chunk_min_size

    def split_file(self, path) -> list[dict]:
        with open(path, "r", encoding="utf-8") as f:
            return self.split_text(f.read(), source_file=path.name)

    def split_text(self, text: str, source_file: str) -> list[dict]:
        sections = self._split_by_headers(text)
        chunks = []
        idx = 0
        for heading_path, body in sections:
            for block in self._split_into_blocks(body):
                chunks.append({
                    "content": block,
                    "source_file": source_file,
                    "chunk_index": idx,
                    "headings": heading_path,
                    "parent_id": None,
                    "content_hash": hashlib.sha256(
                        normalize(block).encode("utf-8")).hexdigest(),
                })
                idx += 1
        return chunks

    def _split_by_headers(self, text: str) -> list[tuple[list[str], str]]:
        sections = []
        stack = []          # 标题栈：["# A", "## B"]
        current = []
        for line in text.split("\n"):
            m = _HEADER.match(line)
            if m:
                if current:
                    sections.append((list(stack), "\n".join(current)))
                    current = []
                level = len(m.group(1))
                title_text = m.group(2)
                # 出栈到同级
                while len(stack) >= level:
                    stack.pop()
                stack.append("#" * level + " " + title_text)
            else:
                current.append(line)
        if current:
            sections.append((list(stack), "\n".join(current)))
        return sections

    def _split_into_blocks(self, body: str) -> list[str]:
        body = body.strip()
        if not body:
            return []
        if len(body) <= self.chunk_size:
            return [body]
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        blocks = []
        buf = ""
        for p in paragraphs:
            if len(buf) + len(p) <= self.chunk_size:
                buf = (buf + "\n\n" + p) if buf else p
            else:
                if buf:
                    blocks.append(buf)
                if len(p) <= self.chunk_size:
                    buf = p
                else:
                    blocks.extend(self._sliding_split(p))
                    buf = ""
        if buf:
            blocks.append(buf)
        return [b for b in blocks if len(b) >= self.min_chunk_size or len(b) == len(body)]

    def _sliding_split(self, text: str) -> list[str]:
        step = self.chunk_size - self.chunk_overlap
        if step <= 0:
            step = self.chunk_size
        out = []
        for i in range(0, len(text), step):
            out.append(text[i:i + self.chunk_size])
        return [b for b in out if b]


def assign_parents(chunks: list[dict]) -> None:
    """把同文件、同 headings 前缀的相邻块回填 parent_id 到上一父块。
    父块 = 同文件且 headings 相同的连续块的组合（近似）。"""
    from collections import defaultdict
    by_sig = defaultdict(list)
    for i, c in enumerate(chunks):
        by_sig[(c["source_file"], tuple(c["headings"]))].append(i)
    for indices in by_sig.values():
        for k in range(1, len(indices)):
            chunks[indices[k]]["parent_id"] = indices[k - 1]