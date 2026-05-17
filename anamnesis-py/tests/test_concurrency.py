"""Concurrency torture tests against shared in-process state.

These mirror what happens when one tenant pushes many parallel HTTP requests
into the FastAPI app: every worker thread ends up sharing the same TraceStore
and ConformalCalibrator instance through the TenantRegistry. We need to
prove no rows are lost, no step ids collide, and counters reflect reality.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from anamnesis.conformal import ConformalCalibrator
from anamnesis.storage import ReasoningStep, TraceStore, hash_embedder


def test_trace_store_add_steps_concurrent_no_loss():
    store = TraceStore(embedder=hash_embedder(dim=64))
    n_threads = 16
    per_thread = 200
    barrier = threading.Barrier(n_threads)

    def writer(tid: int) -> None:
        steps = [
            ReasoningStep.make(
                capture_id=f"cap_{tid}",
                text=f"step text t{tid} i{i}",
                intent=f"i_{tid}_{i}",
            )
            for i in range(per_thread)
        ]
        barrier.wait()
        store.add_steps(steps)

    with ThreadPoolExecutor(max_workers=n_threads) as ex:
        list(ex.map(writer, range(n_threads)))

    assert store.n_steps == n_threads * per_thread


def test_trace_store_concurrent_query_during_writes():
    store = TraceStore(embedder=hash_embedder(dim=64))
    # seed
    seed_steps = [
        ReasoningStep.make("cap_seed", f"seed step number {i}", f"i_{i}")
        for i in range(50)
    ]
    store.add_steps(seed_steps)

    stop_event = threading.Event()
    errors: list[Exception] = []

    def reader() -> None:
        while not stop_event.is_set():
            try:
                store.query_similar_steps("anything", k=5)
            except Exception as e:
                errors.append(e)

    def writer() -> None:
        for i in range(500):
            try:
                store.add_steps([
                    ReasoningStep.make("cap_w", f"writer step {i}", f"i_{i}")
                ])
            except Exception as e:
                errors.append(e)

    threads = [
        threading.Thread(target=reader)
        for _ in range(4)
    ] + [
        threading.Thread(target=writer)
        for _ in range(2)
    ]
    for t in threads:
        t.start()
    # let writers finish
    for t in threads[4:]:
        t.join()
    stop_event.set()
    for t in threads[:4]:
        t.join()

    assert not errors, f"concurrent r/w produced errors: {errors[:3]}"
    assert store.n_steps == 50 + 2 * 500


def test_calibrator_concurrent_add_counts_correctly():
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10, max_window=100_000)
    n_threads = 16
    per_thread = 250
    barrier = threading.Barrier(n_threads)

    def writer(tid: int) -> None:
        rng = np.random.default_rng(tid)
        scores = rng.uniform(0.0, 1.0, size=per_thread)
        barrier.wait()
        for s in scores:
            cal.add(float(s))

    with ThreadPoolExecutor(max_workers=n_threads) as ex:
        list(ex.map(writer, range(n_threads)))

    # ConformalCalibrator has no internal lock by design (it's a value object
    # and the GIL keeps list.append atomic), but the count must still match
    # to ensure no scores were silently dropped on this CPython.
    assert cal.n == n_threads * per_thread


def test_trace_store_unique_step_ids_under_contention():
    """ReasoningStep.make uses uuid4 -- IDs must remain unique under racing creates."""
    n_threads = 8
    per_thread = 1000
    seen: set[str] = set()
    lock = threading.Lock()

    def maker() -> None:
        local = [
            ReasoningStep.make("cap", "x", "i").step_id
            for _ in range(per_thread)
        ]
        with lock:
            seen.update(local)

    threads = [threading.Thread(target=maker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(seen) == n_threads * per_thread
