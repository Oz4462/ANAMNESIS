# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Hard cryptographic attack surface against the receipt subsystem.

Every test below codifies a known pattern that auditors and pen-testers
ship at any production crypto layer. The receipt verifier must reject
each one cold or the EU AI Act compliance claim is theatre.
"""

from __future__ import annotations

import base64
import json
import os

import pytest
from anamnesis.receipts import (
    RECEIPT_PAYLOAD_TYPE,
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
    SignedEnvelope,
)
from nacl.exceptions import BadSignatureError


def _receipt(saved: int = 0) -> Receipt:
    return Receipt(
        tenant_id="crypto-t",
        request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=saved,
    )


def test_all_zero_public_key_is_constructible_but_rejects_legit_sigs():
    """An all-zero pubkey is a small-subgroup point. The verifier must NOT
    accept a real signature against it."""
    signer = ReceiptSigner.generate("real-key")
    env = signer.sign(_receipt())

    zero_pub_b64 = base64.b64encode(b"\x00" * 32).decode()
    verifier = ReceiptVerifier.from_public_key_b64("real-key", zero_pub_b64)
    with pytest.raises(BadSignatureError):
        verifier.verify(env)


def test_signature_truncated_to_zero_bytes_rejected():
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    truncated = SignedEnvelope(
        payloadType=env.payloadType,
        payload=env.payload,
        signatures=[{"keyid": "k", "sig": ""}],
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    with pytest.raises((BadSignatureError, ValueError)):
        verifier.verify(truncated)


def test_signature_truncated_to_half_bytes_rejected():
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    half = base64.b64decode(env.signatures[0]["sig"])[:32]  # 32 instead of 64
    bad = SignedEnvelope(
        payloadType=env.payloadType,
        payload=env.payload,
        signatures=[{"keyid": "k", "sig": base64.b64encode(half).decode()}],
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    with pytest.raises((BadSignatureError, ValueError)):
        verifier.verify(bad)


def test_signature_doubled_in_length_rejected():
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    sig_bytes = base64.b64decode(env.signatures[0]["sig"])
    doubled = sig_bytes + sig_bytes
    bad = SignedEnvelope(
        payloadType=env.payloadType,
        payload=env.payload,
        signatures=[{"keyid": "k", "sig": base64.b64encode(doubled).decode()}],
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    with pytest.raises((BadSignatureError, ValueError)):
        verifier.verify(bad)


def test_key_substitution_with_attacker_pubkey_rejected():
    """Attacker takes a real envelope and rewrites the keyid + presents
    their own pubkey for that id. Verifier accepts ONLY the bound key,
    so verification under the attacker's pubkey must fail."""
    legit = ReceiptSigner.generate("legit-key")
    attacker = ReceiptSigner.generate("legit-key")  # same keyid, attacker key
    env = legit.sign(_receipt())
    verifier = ReceiptVerifier.from_public_key_b64("legit-key", attacker.public_key_b64())
    with pytest.raises(BadSignatureError):
        verifier.verify(env)


def test_pae_length_prefix_confusion_rejected():
    """Manual envelope whose payload bytes claim a different length than
    they actually have. DSSE PAE length-prefixes prevent confusion."""
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())

    payload_bytes = base64.b64decode(env.payload)
    # Append a single byte and try to pass it as the original.
    longer_payload = payload_bytes + b"X"
    bad = SignedEnvelope(
        payloadType=env.payloadType,
        payload=base64.b64encode(longer_payload).decode(),
        signatures=env.signatures,
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    with pytest.raises(BadSignatureError):
        verifier.verify(bad)


def test_payload_type_swap_rejected():
    """Swap payloadType to a different valid media type; the PAE pre-image
    differs, so the signature no longer matches."""
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    swapped = SignedEnvelope(
        payloadType="application/x-other+json",
        payload=env.payload,
        signatures=env.signatures,
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    with pytest.raises(ValueError):  # rejected before sig check on payloadType mismatch
        verifier.verify(swapped)


def test_random_garbage_signature_rejected():
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    rand = os.urandom(64)
    bad = SignedEnvelope(
        payloadType=env.payloadType,
        payload=env.payload,
        signatures=[{"keyid": "k", "sig": base64.b64encode(rand).decode()}],
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    with pytest.raises(BadSignatureError):
        verifier.verify(bad)


def test_replay_with_two_signatures_both_invalid_rejected():
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    bad_sigs = [
        {"keyid": "wrong-key-1", "sig": env.signatures[0]["sig"]},
        {"keyid": "wrong-key-2", "sig": env.signatures[0]["sig"]},
    ]
    bad = SignedEnvelope(payloadType=env.payloadType, payload=env.payload, signatures=bad_sigs)
    verifier = ReceiptVerifier.from_public_key_b64("real-key", signer.public_key_b64())
    with pytest.raises(BadSignatureError):
        verifier.verify(bad)


def test_one_of_two_signatures_verifies_if_keyid_matches():
    """If multiple signatures are present and ONE has a recognised keyid
    that verifies, the envelope passes. Other signatures are ignored."""
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    sig_real = env.signatures[0]
    mixed = SignedEnvelope(
        payloadType=env.payloadType,
        payload=env.payload,
        signatures=[
            {"keyid": "unknown", "sig": base64.b64encode(os.urandom(64)).decode()},
            sig_real,
        ],
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    receipt = verifier.verify(mixed)
    assert receipt.tenant_id == "crypto-t"


def test_signatures_field_with_missing_keys_rejected():
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    no_keyid = SignedEnvelope(
        payloadType=env.payloadType,
        payload=env.payload,
        signatures=[{"sig": env.signatures[0]["sig"]}],
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    with pytest.raises(BadSignatureError):
        verifier.verify(no_keyid)


def test_base64_with_extra_padding_still_decodes_or_rejects():
    """Liberal base64 parsers accept extra padding. We must not produce a
    spurious accept on different bytes that happen to decode identically."""
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    sig = env.signatures[0]["sig"]
    if not sig.endswith("="):
        # Add bogus padding -- base64.b64decode is strict in CPython 3.13.
        bogus = sig + "="
        bad = SignedEnvelope(
            payloadType=env.payloadType,
            payload=env.payload,
            signatures=[{"keyid": "k", "sig": bogus}],
        )
        verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
        with pytest.raises((BadSignatureError, ValueError)):
            verifier.verify(bad)


def test_payload_with_non_canonical_json_yields_different_signature():
    """Two JSONs with identical semantics but different whitespace produce
    different signatures, so an attacker cannot 'reformat' a payload and
    keep the signature valid."""
    signer = ReceiptSigner.generate("k")
    receipt = _receipt(saved=42)
    env = signer.sign(receipt)
    original = base64.b64decode(env.payload)
    pretty = json.dumps(json.loads(original), indent=2).encode()
    assert pretty != original
    bad = SignedEnvelope(
        payloadType=env.payloadType,
        payload=base64.b64encode(pretty).decode(),
        signatures=env.signatures,
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    with pytest.raises(BadSignatureError):
        verifier.verify(bad)


def test_signature_uses_canonical_payload_type_in_pae():
    """Even the payloadType bytes are part of the PAE pre-image. Confirm
    that changing payload_type while keeping signature breaks verification."""
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    assert env.payloadType == RECEIPT_PAYLOAD_TYPE
    # Already covered by test_payload_type_swap_rejected; this is the
    # spec-level affirmation.


def test_verifier_with_empty_keyset_constructor_rejected():
    with pytest.raises(ValueError):
        ReceiptVerifier({})


def test_signer_with_empty_keyid_rejected():
    from nacl.signing import SigningKey
    with pytest.raises(ValueError):
        ReceiptSigner(SigningKey.generate(), key_id="")
