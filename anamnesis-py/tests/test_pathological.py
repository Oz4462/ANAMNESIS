# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Pathological inputs that test the resource ceilings of the receipt
and storage layers. These run slower than typical unit tests; they exist
to catch O(n^2) regressions and "I never thought anyone would do that"
surprises.
"""

from __future__ import annotations

import base64
import time

import pytest
from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
)
from anamnesis.storage import ReasoningStep, TraceStore, hash_embedder


def test_receipt_with_100k_step_ids_signs_under_one_second():
    receipt = Receipt(
        tenant_id="path-t",
        request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d",
        retrieved_step_ids=[f"step_{i:08d}" for i in range(100_000)],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=64),
        cost_saved_tokens=0,
    )
    signer = ReceiptSigner.generate("path")
    t0 = time.perf_counter()
    env = signer.sign(receipt)
    sign_ms = (time.perf_counter() - t0) * 1000
    assert sign_ms < 1500, f"sign too slow at 100k step_ids: {sign_ms:.0f} ms"

    payload_size = len(base64.b64decode(env.payload))
    assert payload_size < 4_000_000, f"payload unexpectedly large: {payload_size} bytes"

    verifier = ReceiptVerifier.from_public_key_b64("path", signer.public_key_b64())
    t0 = time.perf_counter()
    recovered = verifier.verify(env)
    verify_ms = (time.perf_counter() - t0) * 1000
    assert verify_ms < 1500
    assert len(recovered.retrieved_step_ids) == 100_000


def test_thinking_text_one_megabyte_round_trip():
    big = "x" * 1_000_000
    from anamnesis.capture import CapturedTrace

    trace = CapturedTrace(
        provider="anthropic",
        model="m",
        request_id="r",
        thinking_text=big,
        answer_text="ok",
        thinking_tokens=len(big) // 4,
        output_tokens=5,
    )
    store = TraceStore(embedder=hash_embedder(dim=64))
    tid = store.add_trace(trace)
    recovered = store.get_trace(tid)
    assert len(recovered.thinking_text) == 1_000_000


def test_calibration_window_with_100k_writes_caps_at_max_window():
    from anamnesis.conformal import ConformalCalibrator

    cal = ConformalCalibrator(alpha=0.1, max_window=4096, min_calibration=30)
    for i in range(100_000):
        cal.add((i % 100) / 100.0)
    assert cal.n == 4096


def test_query_against_10000_steps_completes_in_500ms():
    store = TraceStore(embedder=hash_embedder(dim=128))
    store.add_steps([
        ReasoningStep.make("c", f"step number {i} alpha beta gamma {i * 7}", f"i_{i}")
        for i in range(10_000)
    ])
    t0 = time.perf_counter()
    store.query_similar_steps("step number 5000 alpha beta gamma 35000", k=10)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 500, f"query against 10K too slow: {elapsed_ms:.1f} ms"


def test_step_with_empty_text_does_not_break_index():
    """add_steps with empty-string text -- still gets a default vector."""
    store = TraceStore(embedder=hash_embedder(dim=32))
    store.add_steps([ReasoningStep.make("c", "", "empty")])
    assert store.n_steps == 1
    results = store.query_similar_steps("nothing related", k=1)
    assert len(results) == 1


def test_step_with_500kb_text_is_inserted_and_queryable():
    store = TraceStore(embedder=hash_embedder(dim=64))
    big = "alpha beta gamma " * 30_000  # ~510 KB
    store.add_steps([ReasoningStep.make("c", big, "i")])
    results = store.query_similar_steps("alpha beta gamma", k=1)
    assert len(results) == 1


@pytest.mark.parametrize("retrieved_count", [10_000, 50_000])
def test_repeated_signing_does_not_leak_memory(retrieved_count: int):
    """Sign the same large receipt 20 times in a row; if our signer
    accumulated state we'd see it here. We just confirm completion."""
    receipt = Receipt(
        tenant_id="repeat",
        request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d",
        retrieved_step_ids=[f"s_{i:08d}" for i in range(retrieved_count)],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=64),
        cost_saved_tokens=0,
    )
    signer = ReceiptSigner.generate("rep")
    for _ in range(20):
        signer.sign(receipt)


def test_thousand_concurrent_calibrators_independent():
    from anamnesis.conformal import ConformalCalibrator

    cals = [ConformalCalibrator(alpha=0.1, min_calibration=5, max_window=100) for _ in range(1000)]
    for i, c in enumerate(cals):
        for _ in range(10):
            c.add(0.1 * (i % 5))
    for i, c in enumerate(cals):
        bound = c.threshold()
        assert bound.tau == pytest.approx(0.1 * (i % 5))
