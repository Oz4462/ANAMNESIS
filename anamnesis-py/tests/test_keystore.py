# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ozan Küsmez
"""Tests for the F19 KeyStore + key_generation receipt field.

Spec: TRUST-OS docs/specs/2026-05-22-key-rotation-interface.md
"""
from __future__ import annotations

import base64

import pytest
from nacl.signing import VerifyKey

from anamnesis.keystore import KeyStore
from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
    SignedEnvelope,
)


def _make_receipt(*, key_generation: int | None = None) -> Receipt:
    return Receipt(
        tenant_id="tenant-1",
        request_id="req-1",
        model=ModelRef(provider="anthropic", name="claude-sonnet", version="4.7"),
        capture_hash="0" * 64,
        distill_model="distill-mini",
        retrieved_step_ids=["s1", "s2"],
        bound=BoundRef(tau=0.05, alpha=0.1, n_calibration=100),
        cost_saved_tokens=4096,
        key_generation=key_generation,
    )


def test_keystore_generate_returns_unique_keypair():
    store = KeyStore()
    a = store.generate()
    b = store.generate()
    assert a.key_id != b.key_id
    assert a.generation == 1
    assert b.generation == 1
    assert a.state == "active"
    assert b.state == "active"
    assert a.public_key_b64 != b.public_key_b64
    # key_id derived from public-key SHA-256 prefix — verifier can rebuild it.
    pub_bytes = base64.b64decode(a.public_key_b64.encode("ascii"))
    assert len(pub_bytes) == 32


def test_keystore_rotate_keeps_old_key_verifiable():
    store = KeyStore()
    old = store.generate()
    sig_before = store.sign(old.key_id, b"old-message")

    new, proof = store.rotate(old.key_id)
    assert proof.old_key_id == old.key_id
    assert proof.new_key_id == new.key_id
    assert proof.new_generation == old.generation + 1

    assert store.get(old.key_id).state == "archived"
    assert store.get(new.key_id).state == "active"
    assert store.get_generation(new.key_id) == 2

    # Archived key MUST still verify past signatures.
    vk = store.verify_key_of(old.key_id)
    vk.verify(b"old-message", sig_before)

    # But MUST NOT be usable to sign new artifacts.
    with pytest.raises(ValueError):
        store.sign(old.key_id, b"new-message")


def test_keystore_revoke_adds_to_revocation_list():
    store = KeyStore()
    k = store.generate()
    proof = store.revoke(k.key_id, "lost-laptop")
    assert proof.reason == "lost-laptop"
    assert store.get(k.key_id).state == "revoked"
    assert store.get(k.key_id).revocation_reason == "lost-laptop"

    with pytest.raises(ValueError):
        store.sign(k.key_id, b"x")

    with pytest.raises(ValueError):
        store.revoke(k.key_id, "double-revoke")


def test_keystore_revoke_requires_reason():
    store = KeyStore()
    k = store.generate()
    with pytest.raises(ValueError):
        store.revoke(k.key_id, "")


def test_keystore_list_active_excludes_revoked():
    store = KeyStore()
    a = store.generate()
    b = store.generate()
    c = store.generate()
    store.revoke(b.key_id, "compromised")

    active_ids = {m.key_id for m in store.list_active()}
    assert a.key_id in active_ids
    assert c.key_id in active_ids
    assert b.key_id not in active_ids


def test_keystore_list_active_excludes_archived():
    store = KeyStore()
    old = store.generate()
    new, _ = store.rotate(old.key_id)
    active_ids = {m.key_id for m in store.list_active()}
    assert new.key_id in active_ids
    assert old.key_id not in active_ids


def test_keystore_rotate_only_active_key():
    store = KeyStore()
    k = store.generate()
    store.revoke(k.key_id, "test")
    with pytest.raises(ValueError):
        store.rotate(k.key_id)


def test_keystore_get_generation_missing():
    store = KeyStore()
    with pytest.raises(KeyError):
        store.get_generation("did:anamnesis:receipt:" + "0" * 32)


def test_receipt_contains_key_generation_field():
    store = KeyStore()
    mat = store.generate()
    receipt = _make_receipt(key_generation=store.get_generation(mat.key_id))
    payload = receipt.to_payload_dict()
    assert payload["key_generation"] == 1


def test_receipt_without_key_generation_omits_field():
    """Backward compatibility: legacy receipts without the field stay shaped the same way."""
    receipt = _make_receipt(key_generation=None)
    payload = receipt.to_payload_dict()
    assert "key_generation" not in payload


def test_legacy_receipt_payload_round_trips():
    """A receipt serialized before this spec must deserialize to key_generation = None."""
    signer = ReceiptSigner.generate(key_id="legacy-key")
    legacy = _make_receipt(key_generation=None)
    envelope = signer.sign(legacy)
    verifier = ReceiptVerifier.from_public_key_b64(
        key_id="legacy-key",
        pubkey_b64=signer.public_key_b64(),
    )
    restored = verifier.verify(envelope)
    assert restored.key_generation is None
    # Spot-check that we still see all other fields.
    assert restored.tenant_id == "tenant-1"
    assert restored.bound.tau == pytest.approx(0.05)


def test_modern_receipt_with_generation_round_trips():
    """A receipt with key_generation must survive sign -> envelope -> verify."""
    store = KeyStore()
    mat = store.generate()
    signer = ReceiptSigner.generate(key_id=mat.key_id)
    modern = _make_receipt(key_generation=store.get_generation(mat.key_id))
    envelope = signer.sign(modern)
    verifier = ReceiptVerifier.from_public_key_b64(
        key_id=mat.key_id,
        pubkey_b64=signer.public_key_b64(),
    )
    restored = verifier.verify(envelope)
    assert restored.key_generation == 1


def test_key_id_format():
    store = KeyStore()
    mat = store.generate(scope="gateway")
    assert mat.key_id.startswith("did:anamnesis:gateway:")
    suffix = mat.key_id.split(":")[-1]
    assert len(suffix) == 32
    assert all(c in "0123456789abcdef" for c in suffix)


def test_verify_key_of_archived_key_still_works():
    store = KeyStore()
    old = store.generate()
    payload = b"audit-trail-payload"
    sig = store.sign(old.key_id, payload)
    store.rotate(old.key_id)
    vk = store.verify_key_of(old.key_id)
    assert isinstance(vk, VerifyKey)
    vk.verify(payload, sig)  # must not raise
