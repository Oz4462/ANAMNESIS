# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Ozan Küsmez
"""Signed reasoning-trace receipts for EU AI Act Article 15 + 50 compliance.

We follow the Dead Simple Signing Envelope (DSSE) specification from in-toto:
    https://github.com/secure-systems-lab/dsse/blob/master/protocol.md

Pre-Authentication Encoding (PAE):
    PAE(type, payload) := "DSSEv1 " || SP || LEN(type) || SP || type
                                    || SP || LEN(payload) || SP || payload

The signer signs PAE(type, payload). Verifiers reject anything that does not
match the exact PAE bytes. This prevents canonicalization attacks against the
underlying JSON.

Each receipt records the full lineage of a reuse decision:
    * the captured reasoning-trace hash,
    * the distillation model used,
    * the retrieved step ids that were composed into the new prompt,
    * the conformal bound (tau, alpha, n_calibration) that justified the reuse,
    * the measured token savings,
    * EU AI Act Article 15 / 50 compliance claims.

These fields are the audit trail an EU AI Act high-risk system operator must
present to a notified body when challenged about logging completeness.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

RECEIPT_PAYLOAD_TYPE = "application/vnd.anamnesis.receipt+json"
RECEIPT_SCHEMA_VERSION = "anamnesis/v1"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _pae(payload_type: str, payload: bytes) -> bytes:
    """DSSE Pre-Authentication Encoding (binary-safe, length-prefixed)."""
    t = payload_type.encode("utf-8")
    return b"DSSEv1 " + str(len(t)).encode() + b" " + t + b" " + str(len(payload)).encode() + b" " + payload


@dataclass(frozen=True, slots=True)
class ModelRef:
    provider: str
    name: str
    version: str | None = None


@dataclass(frozen=True, slots=True)
class BoundRef:
    tau: float
    alpha: float
    n_calibration: int
    score_name: str = "one_minus_cosine"


@dataclass(slots=True)
class Receipt:
    """A signed audit record for one reuse decision.

    Construct via :class:`ReceiptSigner.sign`. Serialize via :meth:`to_envelope`.
    The envelope round-trips losslessly so receipts can be exported, stored,
    and re-verified by any party holding the issuer public key.
    """

    tenant_id: str
    request_id: str
    model: ModelRef
    capture_hash: str
    distill_model: str
    retrieved_step_ids: list[str]
    bound: BoundRef
    cost_saved_tokens: int
    issued_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    receipt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = RECEIPT_SCHEMA_VERSION
    eu_ai_act_claims: dict[str, bool] = field(
        default_factory=lambda: {"article_15": True, "article_50": True}
    )
    # F19 Key-Rotation: monotonic generation counter for the issuing key.
    # Optional for backward compatibility — legacy receipts without this field
    # continue to verify. See docs/specs/2026-05-22-key-rotation-interface.md
    # in TRUST-OS.
    key_generation: int | None = None

    def to_payload_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "issued_at": self.issued_at,
            "tenant_id": self.tenant_id,
            "request_id": self.request_id,
            "model": asdict(self.model),
            "capture_hash": self.capture_hash,
            "distill_model": self.distill_model,
            "retrieved_step_ids": list(self.retrieved_step_ids),
            "bound": asdict(self.bound),
            "cost_saved_tokens": self.cost_saved_tokens,
            "eu_ai_act_claims": dict(self.eu_ai_act_claims),
        }
        if self.key_generation is not None:
            payload["key_generation"] = int(self.key_generation)
        return payload

    def to_payload_bytes(self) -> bytes:
        return json.dumps(
            self.to_payload_dict(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def payload_hash(self) -> str:
        return hashlib.sha256(self.to_payload_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class SignedEnvelope:
    """DSSE-shaped envelope around a Receipt payload."""

    payloadType: str
    payload: str
    signatures: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "payloadType": self.payloadType,
            "payload": self.payload,
            "signatures": [dict(s) for s in self.signatures],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SignedEnvelope:
        if "payloadType" not in data or "payload" not in data or "signatures" not in data:
            raise ValueError("envelope missing required DSSE fields")
        sigs = data["signatures"]
        if not isinstance(sigs, list) or not sigs:
            raise ValueError("envelope must include at least one signature")
        return cls(
            payloadType=str(data["payloadType"]),
            payload=str(data["payload"]),
            signatures=[dict(s) for s in sigs],
        )

    @classmethod
    def from_json(cls, text: str) -> SignedEnvelope:
        return cls.from_dict(json.loads(text))


class ReceiptSigner:
    """Ed25519 signer for Receipt -> DSSE envelope."""

    def __init__(self, signing_key: SigningKey, key_id: str) -> None:
        if not key_id:
            raise ValueError("key_id must be non-empty")
        self._sk = signing_key
        self._key_id = key_id

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def verify_key(self) -> VerifyKey:
        return self._sk.verify_key

    def public_key_b64(self) -> str:
        return _b64(bytes(self._sk.verify_key))

    @classmethod
    def generate(cls, key_id: str) -> ReceiptSigner:
        return cls(SigningKey.generate(), key_id=key_id)

    @classmethod
    def from_seed_b64(cls, seed_b64: str, key_id: str) -> ReceiptSigner:
        sk = SigningKey(_b64decode(seed_b64))
        return cls(sk, key_id=key_id)

    def export_seed_b64(self) -> str:
        return _b64(bytes(self._sk))

    def sign(self, receipt: Receipt) -> SignedEnvelope:
        payload_bytes = receipt.to_payload_bytes()
        pae = _pae(RECEIPT_PAYLOAD_TYPE, payload_bytes)
        sig = self._sk.sign(pae).signature
        return SignedEnvelope(
            payloadType=RECEIPT_PAYLOAD_TYPE,
            payload=_b64(payload_bytes),
            signatures=[{"keyid": self._key_id, "sig": _b64(sig)}],
        )


class ReceiptVerifier:
    """Verifier for DSSE envelopes produced by :class:`ReceiptSigner`."""

    def __init__(self, public_keys: dict[str, VerifyKey]) -> None:
        if not public_keys:
            raise ValueError("at least one public key required")
        self._keys = dict(public_keys)

    @classmethod
    def from_public_key_b64(cls, key_id: str, pubkey_b64: str) -> ReceiptVerifier:
        return cls({key_id: VerifyKey(_b64decode(pubkey_b64))})

    def verify(self, envelope: SignedEnvelope) -> Receipt:
        if envelope.payloadType != RECEIPT_PAYLOAD_TYPE:
            raise ValueError(f"unexpected payloadType {envelope.payloadType!r}")
        payload_bytes = _b64decode(envelope.payload)
        pae = _pae(envelope.payloadType, payload_bytes)

        last_err: Exception | None = None
        verified = False
        for sig_entry in envelope.signatures:
            keyid = sig_entry.get("keyid")
            sig_b64 = sig_entry.get("sig")
            if not keyid or not sig_b64:
                continue
            verify_key = self._keys.get(keyid)
            if verify_key is None:
                continue
            try:
                verify_key.verify(pae, _b64decode(sig_b64))
                verified = True
                break
            except BadSignatureError as e:
                last_err = e
                continue

        if not verified:
            if last_err is not None:
                raise last_err
            raise BadSignatureError("no recognised keyid in envelope signatures")

        data = json.loads(payload_bytes.decode("utf-8"))
        return _receipt_from_payload(data)


def _receipt_from_payload(data: dict[str, Any]) -> Receipt:
    model = ModelRef(**data["model"])
    bound = BoundRef(**data["bound"])
    key_generation = data.get("key_generation")
    return Receipt(
        tenant_id=data["tenant_id"],
        request_id=data["request_id"],
        model=model,
        capture_hash=data["capture_hash"],
        distill_model=data["distill_model"],
        retrieved_step_ids=list(data["retrieved_step_ids"]),
        bound=bound,
        cost_saved_tokens=int(data["cost_saved_tokens"]),
        issued_at=data["issued_at"],
        receipt_id=data["receipt_id"],
        schema_version=data.get("schema_version", RECEIPT_SCHEMA_VERSION),
        eu_ai_act_claims=dict(data.get("eu_ai_act_claims", {"article_15": True, "article_50": True})),
        key_generation=int(key_generation) if key_generation is not None else None,
    )
