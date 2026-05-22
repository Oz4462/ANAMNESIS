# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ozan Küsmez
"""KeyStore implementation for ANAMNESIS.

Implements the canonical TRUST-OS KeyStore interface
(`docs/specs/2026-05-22-key-rotation-interface.md`) for the ANAMNESIS receipt
signer. Uses PyNaCl Ed25519 (already a runtime dependency via `receipts.py`).

The store keeps three states per key — active / archived / revoked — so a
single key compromise or scheduled rotation does not collapse the EU AI Act
Article 12 audit trail. Receipts produced after this implementation carry a
`key_generation` field; receipts produced before continue to verify under the
unchanged DSSE PAE path (see `Receipt.to_payload_dict`).
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from nacl.signing import SigningKey, VerifyKey

_REPO_TAG = "anamnesis"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def derive_key_id(public_key_bytes: bytes, scope: str = "receipt") -> str:
    """did:anamnesis:<scope>:<32-hex-chars> derived from raw public-key bytes.

    The 32-hex suffix is SHA-256(public_key_bytes)[:32]. Verifiers can
    independently rebuild this from the embedded public key in any receipt.
    """
    if len(public_key_bytes) != 32:
        raise ValueError("Ed25519 raw public key must be exactly 32 bytes")
    suffix = hashlib.sha256(public_key_bytes).hexdigest()[:32]
    return f"did:{_REPO_TAG}:{scope}:{suffix}"


@dataclass(frozen=True, slots=True)
class KeyMaterial:
    key_id: str
    public_key_b64: str
    generation: int
    state: str  # "active" | "archived" | "revoked"
    created_at: str
    archived_at: str | None
    revoked_at: str | None
    revocation_reason: str | None


@dataclass(frozen=True, slots=True)
class RotationProof:
    old_key_id: str
    new_key_id: str
    old_generation: int
    new_generation: int
    rotated_at: str


@dataclass(frozen=True, slots=True)
class RevocationProof:
    key_id: str
    generation: int
    reason: str
    revoked_at: str


class KeyStore:
    """In-memory canonical KeyStore for ANAMNESIS receipts.

    Pure-Python, single-process. Production deployments may persist the store
    contents to disk between process restarts, but the threading model and
    durability guarantees of that persistence layer are out of scope for this
    reference implementation.
    """

    def __init__(self) -> None:
        self._signing_keys: dict[str, SigningKey] = {}
        self._material: dict[str, KeyMaterial] = {}

    def generate(self, scope: str = "receipt") -> KeyMaterial:
        """Create a fresh Ed25519 keypair. Returns the public-side KeyMaterial."""
        sk = SigningKey.generate()
        pub_bytes = bytes(sk.verify_key)
        key_id = derive_key_id(pub_bytes, scope=scope)
        if key_id in self._material:
            # Astronomically unlikely with 256 bits of entropy, but the spec is explicit.
            raise KeyError(f"key_id collision (regenerate): {key_id}")
        mat = KeyMaterial(
            key_id=key_id,
            public_key_b64=_b64(pub_bytes),
            generation=1,
            state="active",
            created_at=_now(),
            archived_at=None,
            revoked_at=None,
            revocation_reason=None,
        )
        self._signing_keys[key_id] = sk
        self._material[key_id] = mat
        return mat

    def rotate(self, old_key_id: str, scope: str = "receipt") -> tuple[KeyMaterial, RotationProof]:
        """Archive `old_key_id`, create new active key with generation += 1.

        Returns (new_key_material, proof). Archived key remains in the store
        and continues to be usable for verification of past receipts.
        """
        if old_key_id not in self._material:
            raise KeyError(old_key_id)
        old = self._material[old_key_id]
        if old.state != "active":
            raise ValueError(f"cannot rotate non-active key {old_key_id} (state={old.state})")

        sk = SigningKey.generate()
        pub_bytes = bytes(sk.verify_key)
        new_key_id = derive_key_id(pub_bytes, scope=scope)
        if new_key_id in self._material:
            raise KeyError(f"new key_id collision: {new_key_id}")

        now = _now()
        new_mat = KeyMaterial(
            key_id=new_key_id,
            public_key_b64=_b64(pub_bytes),
            generation=old.generation + 1,
            state="active",
            created_at=now,
            archived_at=None,
            revoked_at=None,
            revocation_reason=None,
        )
        archived = KeyMaterial(
            key_id=old.key_id,
            public_key_b64=old.public_key_b64,
            generation=old.generation,
            state="archived",
            created_at=old.created_at,
            archived_at=now,
            revoked_at=None,
            revocation_reason=None,
        )

        self._material[old_key_id] = archived
        self._material[new_key_id] = new_mat
        self._signing_keys[new_key_id] = sk
        # Keep archived signing key — operators may need to re-issue past artifacts.
        # (For an HSM-backed store, this is where the archive policy gets enforced.)

        proof = RotationProof(
            old_key_id=old_key_id,
            new_key_id=new_key_id,
            old_generation=old.generation,
            new_generation=new_mat.generation,
            rotated_at=now,
        )
        return new_mat, proof

    def revoke(self, key_id: str, reason: str) -> RevocationProof:
        if not reason:
            raise ValueError("revocation reason must be non-empty")
        if key_id not in self._material:
            raise KeyError(key_id)
        prev = self._material[key_id]
        if prev.state == "revoked":
            raise ValueError(f"key {key_id} already revoked at {prev.revoked_at}")
        now = _now()
        self._material[key_id] = KeyMaterial(
            key_id=prev.key_id,
            public_key_b64=prev.public_key_b64,
            generation=prev.generation,
            state="revoked",
            created_at=prev.created_at,
            archived_at=prev.archived_at,
            revoked_at=now,
            revocation_reason=reason,
        )
        return RevocationProof(
            key_id=key_id,
            generation=prev.generation,
            reason=reason,
            revoked_at=now,
        )

    def list_active(self) -> list[KeyMaterial]:
        return [m for m in self._material.values() if m.state == "active"]

    def get_generation(self, key_id: str) -> int:
        if key_id not in self._material:
            raise KeyError(key_id)
        return self._material[key_id].generation

    def get(self, key_id: str) -> KeyMaterial:
        if key_id not in self._material:
            raise KeyError(key_id)
        return self._material[key_id]

    def sign(self, key_id: str, message: bytes) -> bytes:
        mat = self.get(key_id)
        if mat.state != "active":
            raise ValueError(f"refusing to sign with non-active key {key_id} (state={mat.state})")
        sk = self._signing_keys[key_id]
        return sk.sign(message).signature

    def verify_key_of(self, key_id: str) -> VerifyKey:
        """Returns the VerifyKey of any key (active, archived, or revoked).

        Verifiers call this to validate signatures on historical receipts even
        after the signing key has been rotated out.
        """
        if key_id not in self._signing_keys:
            raise KeyError(key_id)
        return self._signing_keys[key_id].verify_key
