"""NaN / Infinity must never pass silently into calibrators or receipts.

JSON technically allows NaN/Infinity via non-standard extensions, and
buggy callers absolutely send them. Anywhere a float would be stored,
serialised, or compared, the system must either reject loudly or coerce
deterministically -- never produce a receipt whose bound contains NaN.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from anamnesis.conformal import ConformalCalibrator, one_minus_cosine
from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
)


def test_calibrator_rejects_nan_score():
    cal = ConformalCalibrator()
    with pytest.raises(ValueError):
        cal.add(float("nan"))


def test_calibrator_rejects_positive_infinity():
    cal = ConformalCalibrator()
    with pytest.raises(ValueError):
        cal.add(float("inf"))


def test_calibrator_rejects_negative_infinity():
    cal = ConformalCalibrator()
    with pytest.raises(ValueError):
        cal.add(float("-inf"))


def test_calibrator_extend_rejects_any_nan_in_batch():
    cal = ConformalCalibrator()
    scores = [0.1, 0.2, math.nan, 0.3]
    with pytest.raises(ValueError):
        cal.extend(scores)
    # Whatever was added before the bad one stays; the call doesn't roll back.
    assert cal.n == 2


def test_one_minus_cosine_with_nan_embedding_propagates_or_raises():
    nan_vec = np.array([float("nan"), 0.0, 1.0])
    ok_vec = np.array([1.0, 0.0, 0.0])
    # numpy will produce NaN if it computes; our function doesn't filter that out.
    # The honest test is that a NaN result is mathematically detectable.
    result = one_minus_cosine(nan_vec, ok_vec)
    assert math.isnan(result), "NaN-in => NaN-out, never silently 0"


def test_receipt_with_nan_in_bound_serialises_but_signs_distinctly():
    """JSON.dumps by default emits NaN/Infinity tokens — we should NOT.

    Our receipt serialisation must reject NaN explicitly so it never lands
    in a signed envelope (some verifiers reject non-standard JSON).
    """
    receipt = Receipt(
        tenant_id="t",
        request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:0",
        distill_model="d",
        retrieved_step_ids=[],
        bound=BoundRef(tau=float("nan"), alpha=0.1, n_calibration=10),
        cost_saved_tokens=0,
    )
    # Round-trip must either reject, or sign+verify a deterministic encoding.
    signer = ReceiptSigner.generate("nan-key")
    try:
        env = signer.sign(receipt)
    except ValueError:
        return  # honest rejection is acceptable

    # If signing succeeded, the encoded payload must not contain literal "NaN"
    # (Python json.dumps emits "NaN" by default which violates RFC 8259).
    import base64
    payload = base64.b64decode(env.payload).decode()
    if "NaN" in payload:
        pytest.fail("receipt payload contains literal 'NaN' — RFC 8259 violation")
    verifier = ReceiptVerifier.from_public_key_b64("nan-key", signer.public_key_b64())
    verifier.verify(env)


def test_receipt_with_infinity_in_cost_saved_tokens_should_fail():
    """cost_saved_tokens is typed int; passing inf via the API is impossible,
    but if someone constructs a Receipt directly with float('inf'), the
    deterministic JSON must not silently emit 'Infinity'."""
    # cost_saved_tokens is typed int. Python lets you pass a float, json.dumps
    # turns it into 'Infinity'. We catch this by signing then inspecting bytes.
    receipt = Receipt(
        tenant_id="t",
        request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:0",
        distill_model="d",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=float("inf"),  # type: ignore
    )
    try:
        raw = receipt.to_payload_bytes()
    except (ValueError, TypeError):
        return
    assert b"Infinity" not in raw, "payload contains 'Infinity' — non-canonical JSON"


def test_conformal_threshold_with_legitimate_zeros():
    """All-zero scores yield a tau of 0.0 — valid mathematically."""
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10)
    cal.extend([0.0] * 30)
    bound = cal.threshold()
    assert bound.tau == 0.0
    assert bound.alpha == 0.1


def test_conformal_threshold_with_negative_scores_is_accepted():
    """The math doesn't require non-negative scores — distances are 0..2 but
    arbitrary non-conformity scores work too."""
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10)
    cal.extend([-1.0, -0.5, 0.0, 0.5, 1.0] * 6)
    bound = cal.threshold()
    assert -1.0 <= bound.tau <= 1.0
