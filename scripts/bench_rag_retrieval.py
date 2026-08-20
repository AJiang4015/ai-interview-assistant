"""大规模 RAG 检索微基准：flat vs hnsw 的 search 耗时与内存占用估计。

脚手架，不参与 pytest。无需应用内部模块，仅依赖 faiss/numpy/argparse/time。
用法：
    python scripts/bench_rag_retrieval.py --n 10000
    python scripts/bench_rag_retrieval.py --n 20000 --dim 128 --k 20 --reps 50 --seed 7
"""
from __future__ import annotations

import argparse
import time

import faiss
import numpy as np


def _nbytes_estimate(index, hnsw_m: int = 16) -> int:
    """粗估某个 faiss 索引占用的内存字节数（flat：全量向量；hnsw：向量 + 邻居表）。"""
    d = index.d
    n = index.ntotal
    if n == 0:
        return 0
    vec_bytes = d * n * 4  # float32 向量
    extra = 0
    if hasattr(index, "hnsw"):
        extra = n * hnsw_m * 2 * 8  # 每个向量 ~ M*2 条邻居指针链路
    return vec_bytes + extra


def search(index, qv: np.ndarray, k: int) -> None:
    index.search(qv, k)


def _bench(name: str, index, queries: np.ndarray, k: int, reps: int) -> float:
    total = 0.0
    for q in queries:
        qv = np.ascontiguousarray(q.reshape(1, -1).astype(np.float32))
        faiss.normalize_L2(qv)
        t0 = time.perf_counter()
        for _ in range(reps):
            search(index, qv, k)
        total += time.perf_counter() - t0
    ms = total / (len(queries) * reps) * 1000.0
    print(f"  {name}: 平均 {ms:.3f} ms/query (k={k}, reps={reps})")
    return ms


def main() -> None:
    ap = argparse.ArgumentParser(description="flat vs hnsw 检索微基准")
    ap.add_argument("--n", type=int, default=10000, help="向量数量")
    ap.add_argument("--dim", type=int, default=128, help="向量维度")
    ap.add_argument("--k", type=int, default=20, help="top_k")
    ap.add_argument("--reps", type=int, default=20, help="每个查询的重复次数")
    ap.add_argument("--nq", type=int, default=50, help="查询向量数量（从向量集中取前 nq 个）")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--m", type=int, default=16, help="HNSW M")
    ap.add_argument("--ef-construction", type=int, default=200, help="HNSW efConstruction")
    ap.add_argument("--ef-search", type=int, default=64, help="HNSW efSearch")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    vecs = rng.normal(size=(args.n, args.dim)).astype(np.float32)
    faiss.normalize_L2(vecs)
    queries = np.ascontiguousarray(vecs[: args.nq])

    print(f"向量数={args.n} 维度={args.dim} top_k={args.k} "
          f"(HNSW M={args.m}, efConstruction={args.ef_construction}, efSearch={args.ef_search})")
    print(f"查询数={args.nq} 每查询reps={args.reps}")
    print()

    flat = faiss.IndexFlatIP(args.dim)
    hnsw = faiss.IndexHNSWFlat(args.dim, args.m)
    hnsw.hnsw.efConstruction = args.ef_construction
    hnsw.hnsw.efSearch = args.ef_search

    t0 = time.perf_counter()
    flat.add(vecs)
    t_flat_build = time.perf_counter() - t0

    t0 = time.perf_counter()
    hnsw.add(vecs)
    t_hnsw_build = time.perf_counter() - t0

    print(f"构建 flat: {t_flat_build:.3f}s | ntotal={flat.ntotal}")
    print(f"构建 hnsw: {t_hnsw_build:.3f}s | ntotal={hnsw.ntotal}")
    print()

    t_flat = _bench("flat", flat, queries, args.k, args.reps)
    t_hnsw = _bench("hnsw", hnsw, queries, args.k, args.reps)

    print()
    print(f"速度对比: hnsw 是 flat 的 {t_flat / t_hnsw:.2f}x")
    print()

    kb_flat = _nbytes_estimate(flat, args.m)
    kb_hnsw = _nbytes_estimate(hnsw, args.m)
    print(f"内存估算 flat: {kb_flat / (1024 ** 2):.2f} MiB (approx)")
    print(f"内存估算 hnsw: {kb_hnsw / (1024 ** 2):.2f} MiB (approx)")


if __name__ == "__main__":
    main()