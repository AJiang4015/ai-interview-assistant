from app.services.retrieval_service import HybridRetriever, RetrievalResult


def test_rrf_ranks_by_union():
    dense = [type("R", (), {"chunk_id": i, "source_file": "f", "chunk_index": i,
                            "content": f"c{i}", "score": 0.9})() for i in range(3)]
    sparse = [type("R", (), {"chunk_id": i, "source_file": "f", "chunk_index": i,
                             "content": f"c{i}", "score": 0.5})() for i in (2, 1)]
    merged = HybridRetriever._rrf_merge(None, dense, sparse, top_k=5)
    assert len(merged) == 3
    assert {r.chunk_id for r in merged} == {0, 1, 2}


def test_expand_with_parents_merges_parent_and_scores():
    candidates = [
        RetrievalResult(chunk_id=1, source_file="f", chunk_index=0, content="leaf1", score=0.9),
        RetrievalResult(chunk_id=2, source_file="f", chunk_index=1, content="leaf2", score=0.8),
        RetrievalResult(chunk_id=3, source_file="f", chunk_index=0, content="leaf3", score=0.7),
    ]
    chunks_by_id = {
        1: {"chunk_id": 1, "content": "leaf1", "parent_id": 10},
        2: {"chunk_id": 2, "content": "leaf2", "parent_id": None},
        3: {"chunk_id": 3, "content": "leaf3", "parent_id": 30},
        10: {"chunk_id": 10, "content": "parent1 content", "parent_id": None},
        30: {"chunk_id": 30, "content": "parent3 content", "parent_id": None},
    }
    expanded = HybridRetriever.expand_with_parents(candidates, chunks_by_id, top_k=10)
    ids = [r.chunk_id for r in expanded]
    assert 1 in ids and 10 in ids
    assert 3 in ids and 30 in ids
    parent = [r for r in expanded if r.chunk_id == 10][0]
    assert parent.content == "parent1 content"
    assert parent.score == 0.9 * 0.9


def test_expand_with_parents_dedups_and_truncates_top_k():
    candidates = [
        RetrievalResult(chunk_id=1, source_file="f", chunk_index=0, content="leaf1", score=0.9),
        RetrievalResult(chunk_id=10, source_file="f", chunk_index=0, content="parent1 content", score=0.6),
    ]
    chunks_by_id = {
        1: {"chunk_id": 1, "content": "leaf1", "parent_id": 10},
        10: {"chunk_id": 10, "content": "parent1 content", "parent_id": None},
    }
    expanded = HybridRetriever.expand_with_parents(candidates, chunks_by_id, top_k=10)
    # 父块已作为候选出现，不得重复并入
    assert [r.chunk_id for r in expanded] == [1, 10]

    no_parent = [
        RetrievalResult(chunk_id=i, source_file="f", chunk_index=i, content=f"c{i}", score=0.5)
        for i in range(5)
    ]
    collapsed = {i: {"chunk_id": i, "content": f"c{i}", "parent_id": None} for i in range(5)}
    truncated = HybridRetriever.expand_with_parents(no_parent, collapsed, top_k=3)
    assert len(truncated) == 3