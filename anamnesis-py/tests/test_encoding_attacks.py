"""Encoding attacks against the serialisation + transport layer.

These are the byte-level games attackers play to bypass naive parsers:
non-canonical base64, BOM-prefixed JSON, embedded NULs, UTF-16 surrogates,
mixed encodings. Our PAE-anchored signature should reject every one.
"""

from __future__ import annotations

import base64

import pytest
from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
    SignedEnvelope,
)
from anamnesis_server.main import create_app
from fastapi.testclient import TestClient
from nacl.exceptions import BadSignatureError


def _receipt() -> Receipt:
    return Receipt(
        tenant_id="enc-t",
        request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=0,
    )


def test_bom_prefixed_payload_breaks_signature():
    """A BOM at the start of the JSON changes the bytes, so PAE differs."""
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    raw = base64.b64decode(env.payload)
    with_bom = b"\xef\xbb\xbf" + raw
    bad = SignedEnvelope(
        payloadType=env.payloadType,
        payload=base64.b64encode(with_bom).decode(),
        signatures=env.signatures,
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    with pytest.raises(BadSignatureError):
        verifier.verify(bad)


def test_payload_with_trailing_whitespace_breaks_signature():
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    raw = base64.b64decode(env.payload)
    with_trailing = raw + b" \n"
    bad = SignedEnvelope(
        payloadType=env.payloadType,
        payload=base64.b64encode(with_trailing).decode(),
        signatures=env.signatures,
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    with pytest.raises(BadSignatureError):
        verifier.verify(bad)


def test_base64_with_url_safe_alphabet_rejected():
    """Standard b64 alphabet uses +/=. URL-safe uses -_=. Mixing them on
    the sig field should fail to decode or fail to verify."""
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    sig = env.signatures[0]["sig"]
    if "+" in sig or "/" in sig:
        url_safe = sig.translate(str.maketrans("+/", "-_"))
        bad = SignedEnvelope(
            payloadType=env.payloadType,
            payload=env.payload,
            signatures=[{"keyid": "k", "sig": url_safe}],
        )
        verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
        with pytest.raises((BadSignatureError, ValueError)):
            verifier.verify(bad)


def test_embedded_utf16_byte_order_mark_in_thinking_text_handled():
    """UTF-16 BOM bytes (\\xff\\xfe) inside a Python str are just two code
    points; we store them, the sqlite layer round-trips them, no crash."""
    from anamnesis.capture import CapturedTrace
    from anamnesis.storage import TraceStore, hash_embedder

    weird = "before﻿after"  # invisible Zero-Width-No-Break-Space
    store = TraceStore(embedder=hash_embedder(dim=16))
    trace = CapturedTrace(
        provider="anthropic",
        model="m",
        request_id="r",
        thinking_text=weird,
        answer_text="ok",
        thinking_tokens=10,
        output_tokens=5,
    )
    tid = store.add_trace(trace)
    recovered = store.get_trace(tid)
    assert recovered.thinking_text == weird


def test_lone_surrogate_in_thinking_text_raises_on_content_hash():
    """A Python string with a lone surrogate (U+DCFF) is technically invalid
    UTF-16. Computing the content_hash uses utf-8 encoding which refuses
    to encode lone surrogates -- the correct fail-fast behaviour."""
    from anamnesis.capture import CapturedTrace

    trace = CapturedTrace(
        provider="anthropic",
        model="m",
        request_id="r",
        thinking_text="\udcff",
        answer_text="ok",
        thinking_tokens=10,
        output_tokens=5,
    )
    with pytest.raises(UnicodeEncodeError):
        _ = trace.content_hash


def test_api_rejects_payload_with_invalid_utf8_bytes():
    """FastAPI / Pydantic should refuse a body with raw bytes that aren't
    valid UTF-8 at parse time."""
    app = create_app()
    client = TestClient(app)
    invalid_utf8 = b'{"tenant_id":"\xff", "request_id":"r"}'
    r = client.post(
        "/v1/captures",
        content=invalid_utf8,
        headers={"content-type": "application/json"},
    )
    assert r.status_code in (400, 422)


def test_pae_encoding_handles_payload_type_with_spaces_safely():
    """Our payload_type is constant but the PAE format uses spaces as
    delimiters. A malicious type with a space in it could try to confuse
    the parse on a buggy verifier. Ours is strict equality on payloadType
    before unpacking."""
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    sneaky = SignedEnvelope(
        payloadType="application/vnd.anamnesis.receipt+json fake",
        payload=env.payload,
        signatures=env.signatures,
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    with pytest.raises(ValueError):
        verifier.verify(sneaky)


def test_payload_base64_with_internal_whitespace_tolerated_as_wire_variation():
    """Python's b64decode treats whitespace as separators (MIME-style).
    Whitespace in the wire b64 does NOT change the decoded payload bytes,
    so verification still succeeds. This is acceptable: DSSE signs the
    decoded bytes, not the wire encoding. Documented here to avoid
    surprise during code review."""
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    with_newlines = env.payload[:10] + "\n" + env.payload[10:]
    spaced = SignedEnvelope(
        payloadType=env.payloadType,
        payload=with_newlines,
        signatures=env.signatures,
    )
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    # Whitespace tolerance is by design; decoded bytes identical -> ok.
    recovered = verifier.verify(spaced)
    assert recovered.tenant_id == "enc-t"


def test_envelope_json_with_extra_unrecognised_fields_still_parses():
    """A forward-compatible envelope may carry future fields. Our parser
    should tolerate that without rejecting the whole envelope."""
    signer = ReceiptSigner.generate("k")
    env = signer.sign(_receipt())
    fat = {
        "payloadType": env.payloadType,
        "payload": env.payload,
        "signatures": env.signatures,
        "future_field_X": "tomorrow",
        "future_count": 7,
    }
    parsed = SignedEnvelope.from_dict(fat)
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    verifier.verify(parsed)  # ok


def test_payload_json_with_unicode_escape_sequences_round_trips():
    """JSON allows \\uXXXX. The decoded canonical form should round-trip
    losslessly through sign+verify."""
    signer = ReceiptSigner.generate("k")
    r = Receipt(
        tenant_id="äöüß",
        request_id="你好",  # ni hao
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=0,
    )
    env = signer.sign(r)
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    recovered = verifier.verify(env)
    assert recovered.tenant_id == "äöüß"
    assert recovered.request_id == "你好"


def test_payload_json_emoji_round_trips():
    signer = ReceiptSigner.generate("k")
    r = Receipt(
        tenant_id="emoji-\U0001f680",
        request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=0,
    )
    env = signer.sign(r)
    verifier = ReceiptVerifier.from_public_key_b64("k", signer.public_key_b64())
    recovered = verifier.verify(env)
    assert "\U0001f680" in recovered.tenant_id
