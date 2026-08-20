from app.services.chunker import Chunker, normalize


def test_normalize_removes_whitespace():
    assert normalize("a\n b\t c") == "a b c"


def test_split_by_headers_produces_paths():
    chunker = Chunker(chunk_size=1000, chunk_overlap=200, min_chunk_size=50)
    text = "# 并发\n## 线程池\n线程池是...\n" * 1
    chunks = chunker.split_text(text, source_file="c.md")
    assert chunks
    assert all(c["headings"] for c in chunks)
    assert all(c["content_hash"] for c in chunks)


def test_runs_increment_chunk_index():
    chunker = Chunker(chunk_size=100, chunk_overlap=20, min_chunk_size=20)
    text = "段落一。" * 30 + "\n\n段落二。" * 30
    chunks = chunker.split_text(text, source_file="d.md")
    idxs = [c["chunk_index"] for c in chunks]
    assert idxs == list(range(len(chunks)))