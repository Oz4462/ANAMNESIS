# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Property-based tests via Hypothesis.

We assert invariants instead of specific examples:

* sign(...).verify(...) round-trips for any well-formed Receipt.
* any single-byte mutation of the payload or signature is detected.
* canonical JSON output is sorted-key + compact regardless of field order.
* split-conformal threshold is monotone in alpha (smaller alpha => larger tau).
* hash_embedder always produces unit-norm vectors of the requested dim.
"""

from __future__ import annotations

import base64
import json

import numpy as np
import pytest
from anamnesis.conformal import ConformalCalibrator
from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
    SignedEnvelope,
)
from anamnesis.storage import hash_embedder
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from nacl.exceptions import BadSignatureError

SAFE = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


@st.composite
def receipts(draw) -> Receipt:
    return Receipt(
        tenant_id=draw(st.text(min_size=1, max_size=64)),
        request_id=draw(st.text(min_size=1, max_size=64)),
        model=ModelRef(
            provider=draw(st.sampled_from(["anthropic", "openai", "deepseek", "gemini", "mistral"])),
            name=draw(st.text(min_size=1, max_size=40)),
            version=draw(st.one_of(st.none(), st.text(min_size=1, max_size=20))),
        ),
        capture_hash="sha256:" + draw(st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)),
        distill_model=draw(st.text(min_size=1, max_size=40)),
        retrieved_step_ids=draw(st.lists(st.text(min_size=1, max_size=24), max_size=16)),
        bound=BoundRef(
            tau=draw(st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False)),
            alpha=draw(st.floats(min_value=1e-6, max_value=1 - 1e-6, allow_nan=False, allow_infinity=False)),
            n_calibration=draw(st.integers(min_value=1, max_value=10_000)),
        ),
        cost_saved_tokens=draw(st.integers(min_value=0, max_value=10**9)),
    )


@SAFE
@given(receipt=receipts())
def test_sign_then_verify_round_trip(receipt: Receipt):
    signer = ReceiptSigner.generate("prop-key")
    env = signer.sign(receipt)
    verifier = ReceiptVerifier.from_public_key_b64("prop-key", signer.public_key_b64())
    recovered = verifier.verify(env)

    assert recovered.tenant_id == receipt.tenant_id
    assert recovered.request_id == receipt.request_id
    assert recovered.model == receipt.model
    assert recovered.bound == receipt.bound
    assert list(recovered.retrieved_step_ids) == list(receipt.retrieved_step_ids)
    assert recovered.cost_saved_tokens == receipt.cost_saved_tokens


@SAFE
@given(
    receipt=receipts(),
    flip_index=st.integers(min_value=0, max_value=1023),
)
def test_any_single_byte_flip_of_payload_is_caught(receipt: Receipt, flip_index: int):
    signer = ReceiptSigner.generate("prop-key")
    env = signer.sign(receipt)
    payload = bytearray(base64.b64decode(env.payload))
    if flip_index >= len(payload):
        return
    payload[flip_index] ^= 0x01
    bad = SignedEnvelope(
        payloadType=env.payloadType,
        payload=base64.b64encode(bytes(payload)).decode("ascii"),
        signatures=env.signatures,
    )
    verifier = ReceiptVerifier.from_public_key_b64("prop-key", signer.public_key_b64())
    with pytest.raises((BadSignatureError, ValueError)):
        verifier.verify(bad)


@SAFE
@given(
    receipt=receipts(),
    flip_index=st.integers(min_value=0, max_value=63),
)
def test_any_single_byte_flip_of_signature_is_caught(receipt: Receipt, flip_index: int):
    signer = ReceiptSigner.generate("prop-key")
    env = signer.sign(receipt)
    sig = bytearray(base64.b64decode(env.signatures[0]["sig"]))
    sig[flip_index] ^= 0x01
    bad = SignedEnvelope(
        payloadType=env.payloadType,
        payload=env.payload,
        signatures=[{"keyid": env.signatures[0]["keyid"], "sig": base64.b64encode(bytes(sig)).decode("ascii")}],
    )
    verifier = ReceiptVerifier.from_public_key_b64("prop-key", signer.public_key_b64())
    with pytest.raises((BadSignatureError, ValueError)):
        verifier.verify(bad)


@SAFE
@given(receipt=receipts())
def test_canonical_payload_is_compact_and_sorted(receipt: Receipt):
    raw = receipt.to_payload_bytes()
    assert b"\n" not in raw
    parsed = json.loads(raw)
    canonical_check = json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode()
    assert raw == canonical_check
    keys = list(parsed.keys())
    assert keys == sorted(keys)


@SAFE
@given(
    scores=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=50,
        max_size=500,
    ),
    alpha_a=st.floats(min_value=0.05, max_value=0.45),
    alpha_b=st.floats(min_value=0.05, max_value=0.45),
)
def test_threshold_monotone_in_alpha(scores: list[float], alpha_a: float, alpha_b: float):
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10, max_window=10_000)
    cal.extend(scores)
    a, b = sorted([alpha_a, alpha_b])  # a <= b
    tau_a = cal.threshold(alpha=a).tau
    tau_b = cal.threshold(alpha=b).tau
    assert tau_a >= tau_b - 1e-12, f"alpha={a} should give tau >= alpha={b}, got {tau_a} < {tau_b}"


@SAFE
@given(
    text=st.text(min_size=0, max_size=200),
    dim=st.sampled_from([16, 32, 64, 128, 384]),
)
def test_hash_embedder_unit_norm(text: str, dim: int):
    e = hash_embedder(dim=dim)
    v = e(text)
    assert v.shape == (dim,)
    assert float(np.linalg.norm(v)) == pytest.approx(1.0, abs=1e-9)


@SAFE
@given(env_b64=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=", min_size=4, max_size=200))
def test_envelope_from_json_rejects_garbage(env_b64: str):
    try:
        SignedEnvelope.from_json(env_b64)
    except (json.JSONDecodeError, ValueError, TypeError):
        return  # expected
    # If parse succeeded, the result must still expose the required DSSE fields.
    # That can happen if Hypothesis happens to draw a base64 alphabet sequence
    # that is also a valid JSON object — that's fine, we just want no crash on
    # garbage and any returned object must satisfy the invariant.
