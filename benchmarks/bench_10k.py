"""Performance smoke test on 10K reasoning steps.

Measures:
  * insert throughput (steps/sec) for the local sqlite + numpy index
  * cold and warm retrieval latency (p50, p95, p99) over 200 queries
  * memory after load via tracemalloc

Runs entirely on the hash_embedder so the result is dominated by the data
plane, not the embedding model.
"""

from __future__ import annotations

import random
import statistics
import time
import tracemalloc
from pathlib import Path

from anamnesis.storage import ReasoningStep, TraceStore, hash_embedder


def _seed_text(rng: random.Random, n_words: int = 24) -> str:
    pool = ["triangle", "area", "base", "height", "equation", "linear", "quadratic", "eigenvalue", "sphere", "volume", "radius", "bake", "sourdough", "cake", "recipe", "contract", "clause", "legal", "court", "budget", "revenue", "translate", "German", "English", "dictionary", "derivative", "integral", "matrix", "kernel", "hash", "ed25519", "receipt", "signature", "anomaly", "drift", "conformal", "calibration", "cosine"]
    return " ".join(rng.choice(pool) for _ in range(n_words))


def main(n_steps: int = 10_000, n_queries: int = 200, seed: int = 17) -> None:
    rng = random.Random(seed)
    store = TraceStore(embedder=hash_embedder(dim=128))

    print(f"=== inserting {n_steps} steps ===")
    tracemalloc.start()
    t0 = time.perf_counter()
    batch = []
    for i in range(n_steps):
        step = ReasoningStep.make(
            capture_id=f"cap_{i // 64}",
            text=_seed_text(rng),
            intent=f"intent_{i}",
            tags=("bench",),
        )
        batch.append(step)
        if len(batch) >= 500:
            store.add_steps(batch)
            batch.clear()
    if batch:
        store.add_steps(batch)
    t_insert = time.perf_counter() - t0
    cur_mb, peak_mb = (m / 1e6 for m in tracemalloc.get_traced_memory())
    tracemalloc.stop()

    print(f"  insert wall-time: {t_insert:.2f} s")
    print(f"  insert throughput: {n_steps / t_insert:,.0f} steps/sec")
    print(f"  store.n_steps: {store.n_steps}")
    print(f"  python memory (current/peak MB): {cur_mb:.1f} / {peak_mb:.1f}")

    print(f"\n=== running {n_queries} retrieval queries (k=5) ===")
    queries = [_seed_text(rng) for _ in range(n_queries)]
    lat = []
    for q in queries:
        s = time.perf_counter()
        store.query_similar_steps(q, k=5)
        lat.append((time.perf_counter() - s) * 1000)
    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[int(0.95 * len(lat))]
    p99 = lat[int(0.99 * len(lat))]
    print(f"  p50 latency: {p50:.2f} ms")
    print(f"  p95 latency: {p95:.2f} ms")
    print(f"  p99 latency: {p99:.2f} ms")
    print(f"  qps (single-threaded): {1000.0 / p50:,.0f}")

    print("\n=== file-backed run (sqlite-on-disk) ===")
    tmp = Path("./bench_persist.db")
    if tmp.exists():
        tmp.unlink()
    persistent = TraceStore(embedder=hash_embedder(dim=128), db_path=tmp)
    t0 = time.perf_counter()
    persistent.add_steps([ReasoningStep.make(f"cap_{i}", _seed_text(rng), f"i_{i}") for i in range(1000)])
    print(f"  insert 1000 on-disk: {(time.perf_counter() - t0) * 1000:.0f} ms")
    persistent.close()
    print(f"  db file size: {tmp.stat().st_size / 1024:.1f} KB")
    tmp.unlink()

    print("\nBENCHMARK OK")


if __name__ == "__main__":
    main()
