# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Tests for Ed25519 DSSE receipt signing and verification."""

from __future__ import annotations

import base64
import json

import pytest
from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
    SignedEnvelope,
    _pae,
)
from nacl.exceptions import BadSignatureError


def _make_receipt(retrieved=("step_a", "step_b"), saved=1234) -> Receipt:
    return Receipt(
        tenant_id="tenant_xyz",
        request_id="req_42",
        model=ModelRef(provider="anthropic", name="claude-opus-4-7", version="2026-05-01"),
        capture_hash="sha256:abc123",
        distill_model="claude-haiku-4-5",
        retrieved_step_ids=list(retrieved),
        bound=BoundRef(tau=0.18, alpha=0.1, n_calibration=512),
        cost_saved_tokens=saved,
    )


def test_pae_format_matches_dsse_spec():
    pae = _pae("application/vnd.anamnesis.receipt+json", b'{"k":"v"}')
    assert pae.startswith(b"DSSEv1 ")
    parts = pae.split(b" ", 4)
    assert parts[0] == b"DSSEv1"
    assert parts[1] == str(len("application/vnd.anamnesis.receipt+json")).encode()
    assert parts[2] == b"application/vnd.anamnesis.receipt+json"
    assert parts[3] == b"9"
    assert parts[4] == b'{"k":"v"}'


def test_pae_is_unique_per_payload():
    a = _pae("application/x+json", b"hello")
    b = _pae("application/x+json", b"hello world")
    assert a != b


def test_signer_generate_produces_distinct_keys():
    s1 = ReceiptSigner.generate("k1")
    s2 = ReceiptSigner.generate("k2")
    assert s1.public_key_b64() != s2.public_key_b64()
    assert s1.key_id == "k1"
    assert s2.key_id == "k2"


def test_signer_round_trip_via_seed_b64():
    s = ReceiptSigner.generate("k_orig")
    seed = s.export_seed_b64()
    s2 = ReceiptSigner.from_seed_b64(seed, key_id="k_restored")
    assert s.public_key_b64() == s2.public_key_b64()


def test_sign_and_verify_round_trip():
    signer = ReceiptSigner.generate("issuer_001")
    receipt = _make_receipt()
    env = signer.sign(receipt)

    verifier = ReceiptVerifier.from_public_key_b64("issuer_001", signer.public_key_b64())
    recovered = verifier.verify(env)

    assert recovered.tenant_id == receipt.tenant_id
    assert recovered.request_id == receipt.request_id
    assert recovered.model == receipt.model
    assert recovered.bound == receipt.bound
    assert recovered.retrieved_step_ids == receipt.retrieved_step_ids
    assert recovered.cost_saved_tokens == receipt.cost_saved_tokens


def test_verify_rejects_tampered_payload():
    signer = ReceiptSigner.generate("issuer_002")
    env = signer.sign(_make_receipt())

    payload_bytes = base64.b64decode(env.payload)
    data = json.loads(payload_bytes)
    data["cost_saved_tokens"] = 9_999_999
    bad_payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    bad_env = SignedEnvelope(
        payloadType=env.payloadType,
        payload=base64.b64encode(bad_payload).decode("ascii"),
        signatures=env.signatures,
    )
    verifier = ReceiptVerifier.from_public_key_b64("issuer_002", signer.public_key_b64())
    with pytest.raises(BadSignatureError):
        verifier.verify(bad_env)


def test_verify_rejects_wrong_payload_type():
    signer = ReceiptSigner.generate("issuer_003")
    env = signer.sign(_make_receipt())
    mutated = SignedEnvelope(
        payloadType="application/json",
        payload=env.payload,
        signatures=env.signatures,
    )
    verifier = ReceiptVerifier.from_public_key_b64("issuer_003", signer.public_key_b64())
    with pytest.raises(ValueError, match="payloadType"):
        verifier.verify(mutated)


def test_verify_rejects_unknown_keyid():
    signer = ReceiptSigner.generate("real_issuer")
    env = signer.sign(_make_receipt())
    verifier = ReceiptVerifier.from_public_key_b64("OTHER_KEY", signer.public_key_b64())
    with pytest.raises(BadSignatureError):
        verifier.verify(env)


def test_verify_rejects_swapped_signature_from_other_signer():
    s_a = ReceiptSigner.generate("issuer_a")
    s_b = ReceiptSigner.generate("issuer_b")
    env_a = s_a.sign(_make_receipt())

    forged_sigs = [{"keyid": "issuer_a", "sig": s_b.sign(_make_receipt()).signatures[0]["sig"]}]
    forged_env = SignedEnvelope(
        payloadType=env_a.payloadType,
        payload=env_a.payload,
        signatures=forged_sigs,
    )
    verifier = ReceiptVerifier.from_public_key_b64("issuer_a", s_a.public_key_b64())
    with pytest.raises(BadSignatureError):
        verifier.verify(forged_env)


def test_envelope_json_round_trip():
    signer = ReceiptSigner.generate("rt_key")
    env = signer.sign(_make_receipt())
    text = env.to_json()
    parsed = SignedEnvelope.from_json(text)
    assert parsed == env


def test_envelope_rejects_missing_fields():
    with pytest.raises(ValueError):
        SignedEnvelope.from_dict({"payload": "x", "signatures": [{"sig": "y"}]})
    with pytest.raises(ValueError):
        SignedEnvelope.from_dict({"payloadType": "x", "payload": "y", "signatures": []})


def test_payload_hash_is_deterministic_and_changes_with_content():
    r1 = _make_receipt(saved=1)
    r2 = _make_receipt(saved=1)
    r3 = _make_receipt(saved=2)
    assert r1.payload_hash() != r1.receipt_id  # not trivially identical
    assert r3.payload_hash() != r1.payload_hash()
    # same content => same hash if receipt_id and issued_at stripped
    r1.receipt_id = r2.receipt_id
    r1.issued_at = r2.issued_at
    assert r1.payload_hash() == r2.payload_hash()


def test_eu_ai_act_claims_default_to_articles_15_and_50():
    r = _make_receipt()
    assert r.eu_ai_act_claims == {"article_15": True, "article_50": True}


def test_signer_rejects_empty_key_id():
    with pytest.raises(ValueError):
        from nacl.signing import SigningKey

        ReceiptSigner(SigningKey.generate(), key_id="")


def test_verifier_rejects_empty_key_set():
    with pytest.raises(ValueError):
        ReceiptVerifier({})


def test_canonical_payload_is_sorted_and_compact():
    r = _make_receipt()
    raw = r.to_payload_bytes()
    assert b": " not in raw  # compact separator
    assert b", " not in raw  # compact separator
    assert b"\n" not in raw
    parsed = json.loads(raw)
    keys = list(parsed.keys())
    assert keys == sorted(keys)
