# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Determinism: identical inputs + identical key material must produce
identical bytes, signatures, and hashes. This is critical for any auditor
who wants to recompute a receipt and compare byte-for-byte.

Ed25519 signatures from the same seed + same message are deterministic by
design (unlike ECDSA), so we get a strong test surface for free.
"""

from __future__ import annotations

from anamnesis.capture import CapturedTrace
from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
)
from anamnesis.storage import hash_embedder


def _fixed_receipt() -> Receipt:
    return Receipt(
        tenant_id="det-tenant",
        request_id="det-req",
        model=ModelRef(provider="anthropic", name="claude-opus-4-7"),
        capture_hash="sha256:" + ("a" * 64),
        distill_model="heuristic-v1",
        retrieved_step_ids=["s1", "s2", "s3"],
        bound=BoundRef(tau=0.18, alpha=0.1, n_calibration=64),
        cost_saved_tokens=42,
        issued_at="2026-05-17T00:00:00+00:00",
        receipt_id="fixed-uuid-1234",
    )


def test_canonical_payload_bytes_are_byte_exact_for_identical_receipts():
    a = _fixed_receipt()
    b = _fixed_receipt()
    assert a.to_payload_bytes() == b.to_payload_bytes()


def test_ed25519_signature_is_deterministic_for_same_seed_and_message():
    a = _fixed_receipt()
    signer1 = ReceiptSigner.generate("det-key")
    seed = signer1.export_seed_b64()

    sig1 = signer1.sign(a)
    # Recover same key from seed, sign same receipt -- signature must match bit-for-bit.
    signer2 = ReceiptSigner.from_seed_b64(seed, key_id="det-key")
    sig2 = signer2.sign(a)
    assert sig1.signatures[0]["sig"] == sig2.signatures[0]["sig"]
    assert sig1.payload == sig2.payload


def test_signature_changes_when_only_one_field_differs():
    signer = ReceiptSigner.generate("det-key")
    a = _fixed_receipt()
    a_env = signer.sign(a)

    b = _fixed_receipt()
    b.cost_saved_tokens = 43  # one bit of difference
    b_env = signer.sign(b)

    assert a_env.signatures[0]["sig"] != b_env.signatures[0]["sig"]
    assert a_env.payload != b_env.payload


def test_payload_hash_is_byte_deterministic():
    a = _fixed_receipt()
    b = _fixed_receipt()
    assert a.payload_hash() == b.payload_hash()


def test_capture_content_hash_deterministic_across_constructions():
    fields = dict(
        provider="anthropic",
        model="claude-opus-4-7",
        request_id="r",
        thinking_text="step one step two",
        answer_text="42",
        thinking_tokens=10,
        output_tokens=5,
    )
    a = CapturedTrace(**fields)
    b = CapturedTrace(**fields)
    assert a.content_hash == b.content_hash


def test_hash_embedder_byte_exact_for_same_input():
    e = hash_embedder(dim=64)
    v1 = e("Determinism test string with several words for hashing")
    v2 = e("Determinism test string with several words for hashing")
    assert (v1 == v2).all()


def test_canonical_payload_field_order_is_alphabetical():
    """Insertion order in the dict construction must not affect output order."""
    receipt = _fixed_receipt()
    raw = receipt.to_payload_bytes().decode()
    keys = []
    depth = 0
    in_string = False
    buf = ""
    for ch in raw:
        if ch == '"' and (not buf or buf[-1] != "\\"):
            in_string = not in_string
            buf += ch
            continue
        if in_string:
            buf += ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ":" and depth == 1:
            keys.append(buf.split('"')[-2])
            buf = ""
            continue
        elif ch == "," and depth == 1:
            buf = ""
            continue
        buf += ch
    assert keys == sorted(keys), f"top-level keys not sorted: {keys}"


def test_receipt_with_identical_field_values_but_different_object_instances():
    """Equality / hashing via to_payload_bytes is structural, not by-reference."""
    r1 = _fixed_receipt()
    r2 = _fixed_receipt()
    assert r1.payload_hash() == r2.payload_hash()
    assert r1.to_payload_bytes() == r2.to_payload_bytes()


def test_two_signers_with_same_seed_yield_same_public_key():
    sk = ReceiptSigner.generate("orig")
    seed = sk.export_seed_b64()
    restored = ReceiptSigner.from_seed_b64(seed, key_id="restored")
    assert sk.public_key_b64() == restored.public_key_b64()
