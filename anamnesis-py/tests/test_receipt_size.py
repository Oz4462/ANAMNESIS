"""Receipt size + payload stress tests.

Find where the DSSE envelope / Ed25519 signature stops scaling. A receipt
referencing 10 000 retrieved_step_ids is plausible for a long-running
agent that reuses dozens of prior reasoning fragments per call.
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


def _make(retrieved_count: int, suffix_size: int = 0) -> Receipt:
    return Receipt(
        tenant_id="size-stress",
        request_id="rid",
        model=ModelRef(provider="anthropic", name="claude-opus-4-7"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="heuristic-v1",
        retrieved_step_ids=[f"step_{i:08d}_" + ("x" * suffix_size) for i in range(retrieved_count)],
        bound=BoundRef(tau=0.18, alpha=0.1, n_calibration=512),
        cost_saved_tokens=retrieved_count * 100,
    )


@pytest.mark.parametrize("count", [1, 10, 100, 1000, 5000, 10000])
def test_receipt_sign_verify_at_size(count: int):
    signer = ReceiptSigner.generate("size-key")
    verifier = ReceiptVerifier.from_public_key_b64("size-key", signer.public_key_b64())
    receipt = _make(retrieved_count=count)

    t0 = time.perf_counter()
    env = signer.sign(receipt)
    sign_ms = (time.perf_counter() - t0) * 1000

    payload_bytes = base64.b64decode(env.payload)
    print(f"  count={count:>5}  payload_size={len(payload_bytes):>9} bytes  sign={sign_ms:6.1f} ms")

    t0 = time.perf_counter()
    recovered = verifier.verify(env)
    verify_ms = (time.perf_counter() - t0) * 1000
    print(f"  count={count:>5}  verify={verify_ms:6.1f} ms")

    assert len(recovered.retrieved_step_ids) == count
    assert recovered.cost_saved_tokens == count * 100


def test_receipt_with_very_long_step_ids():
    receipt = _make(retrieved_count=100, suffix_size=512)
    signer = ReceiptSigner.generate("long-id-key")
    env = signer.sign(receipt)
    payload_bytes = base64.b64decode(env.payload)
    assert len(payload_bytes) > 50_000
    verifier = ReceiptVerifier.from_public_key_b64("long-id-key", signer.public_key_b64())
    recovered = verifier.verify(env)
    assert all(s.endswith("x" * 512) for s in recovered.retrieved_step_ids)


def test_receipt_serialised_envelope_is_under_2mb_at_10k_steps():
    receipt = _make(retrieved_count=10_000)
    signer = ReceiptSigner.generate("size-2mb")
    env = signer.sign(receipt)
    serialised = env.to_json()
    size_mb = len(serialised) / (1024 * 1024)
    assert size_mb < 2.0, f"envelope too large at 10K steps: {size_mb:.2f} MB"


def test_receipt_payload_hash_stable_per_input_size():
    """Determinism: same receipt, same payload bytes, same hash regardless of size."""
    a = _make(retrieved_count=1000)
    b = _make(retrieved_count=1000)
    # Override timestamps + id so the only diff is bytes
    b.issued_at = a.issued_at
    b.receipt_id = a.receipt_id
    assert a.payload_hash() == b.payload_hash()
