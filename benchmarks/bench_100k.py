"""Heavy-stress benchmark: 100K steps, latency degradation curve.

Compared to bench_10k.py this asks: does our naive in-memory numpy matrix
hold up at 10x the data, or do we hit memory or latency walls?

Reports:
  * insert wall-time and throughput
  * memory growth (current/peak via tracemalloc)
  * retrieval p50/p95/p99 at 10K, 25K, 50K, 100K checkpoints
"""

from __future__ import annotations

import random
import statistics
import time
import tracemalloc

from anamnesis.storage import ReasoningStep, TraceStore, hash_embedder


def _seed_text(rng: random.Random, n_words: int = 12) -> str:
    pool = ["triangle", "area", "base", "height", "equation", "linear", "quadratic", "eigenvalue", "sphere", "volume", "radius", "bake", "sourdough", "cake", "recipe", "contract", "clause", "legal", "court", "budget", "revenue", "translate", "German", "English", "dictionary", "derivative", "integral", "matrix", "kernel", "hash"]
    return " ".join(rng.choice(pool) for _ in range(n_words))


def main() -> None:
    rng = random.Random(99)
    store = TraceStore(embedder=hash_embedder(dim=128))

    print("=== 100K stress test ===")
    tracemalloc.start()

    checkpoints = [10_000, 25_000, 50_000, 100_000]
    next_idx = 0
    batch: list[ReasoningStep] = []
    t0 = time.perf_counter()
    queries = [_seed_text(rng) for _ in range(50)]

    for i in range(100_000):
        batch.append(
            ReasoningStep.make(
                capture_id=f"cap_{i // 64}",
                text=_seed_text(rng),
                intent=f"i_{i}",
            )
        )
        if len(batch) >= 1000:
            store.add_steps(batch)
            batch.clear()
        if next_idx < len(checkpoints) and (i + 1) == checkpoints[next_idx]:
            elapsed = time.perf_counter() - t0
            cur_mb, peak_mb = (m / 1e6 for m in tracemalloc.get_traced_memory())
            # measure retrieval latency at this scale
            lat = []
            for q in queries:
                s = time.perf_counter()
                store.query_similar_steps(q, k=5)
                lat.append((time.perf_counter() - s) * 1000)
            lat.sort()
            p50 = statistics.median(lat)
            p95 = lat[int(0.95 * len(lat))]
            p99 = lat[int(0.99 * len(lat))]
            print(
                f"  @{i + 1:>6}: elapsed={elapsed:6.1f}s  "
                f"throughput={(i + 1) / elapsed:5.0f}/s  "
                f"mem cur/peak={cur_mb:5.1f}/{peak_mb:5.1f} MB  "
                f"p50/p95/p99={p50:5.1f}/{p95:5.1f}/{p99:5.1f} ms"
            )
            next_idx += 1

    if batch:
        store.add_steps(batch)

    tracemalloc.stop()
    print("\n100K STRESS OK")


if __name__ == "__main__":
    main()
