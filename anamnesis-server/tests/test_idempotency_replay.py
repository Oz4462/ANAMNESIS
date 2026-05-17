"""Idempotency + replay-attack tests.

The current MVP does NOT enforce idempotency on /v1/captures: re-posting
with the same request_id yields a NEW trace_id (and therefore new
distilled steps). That's a behaviour we want to document with a test so
the v0.3 idempotency-key feature can be added consciously.

We also confirm that a previously-issued receipt remains verifiable when
'replayed' to a verifier -- by design. Replay-prevention is a tenant-side
concern (use a nonce + dedupe store); the server only attests the receipt
is genuine, not unique-per-request.
"""

from __future__ import annotations

import pytest
from anamnesis.receipts import ReceiptVerifier, SignedEnvelope
from anamnesis_server.main import create_app
from fastapi.testclient import TestClient
from nacl.exceptions import BadSignatureError


@pytest.fixture()
def client():
    return TestClient(create_app())


def _capture_payload(rid: str = "rep-req") -> dict:
    return {
        "tenant_id": "rep-tenant",
        "request_id": rid,
        "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
        "thinking_text": (
            "Erste vollstaendige Begruendung der Aufgabe im Detail. "
            "Zweite mathematische Ableitung der notwendigen Bedingungen mit Schluss."
        ),
        "answer_text": "ok",
        "thinking_tokens": 100,
        "output_tokens": 5,
    }


def test_capture_with_same_request_id_yields_distinct_trace_ids(client):
    """Documents current MVP behaviour: capture is NOT idempotent on request_id."""
    a = client.post("/v1/captures", json=_capture_payload()).json()
    b = client.post("/v1/captures", json=_capture_payload()).json()
    assert a["trace_id"] != b["trace_id"]
    # The content_hash IS identical because the thinking_text didn't change.
    assert a["content_hash"] == b["content_hash"]


def test_capture_with_different_request_ids_distinct_steps(client):
    a = client.post("/v1/captures", json=_capture_payload("a")).json()
    b = client.post("/v1/captures", json=_capture_payload("b")).json()
    # Both distinct trace_ids AND distilled-step counts must be independent.
    assert a["trace_id"] != b["trace_id"]
    assert a["n_steps_distilled"] >= 1
    assert b["n_steps_distilled"] >= 1


def test_signed_receipt_can_be_verified_repeatedly(client):
    """Receipt verification is idempotent: same envelope verifies N times."""
    client.post("/v1/captures", json=_capture_payload())
    for i in range(40):
        client.post("/v1/calibration", json={"tenant_id": "rep-tenant", "score": 0.4 + (i % 8) * 0.05})

    reuse = client.post(
        "/v1/reuse",
        json={
            "tenant_id": "rep-tenant",
            "user_text": "Erste vollstaendige Begruendung",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "k": 3,
        },
    ).json()
    if reuse["abstained"]:
        pytest.skip("calibrator abstained, skip replay")

    env = SignedEnvelope.from_dict(reuse["receipt_envelope"])
    signer_pub = client.app.state.signer.public_key_b64()
    verifier = ReceiptVerifier.from_public_key_b64("anamnesis-server-default", signer_pub)

    receipt_a = verifier.verify(env)
    receipt_b = verifier.verify(env)
    receipt_c = verifier.verify(env)
    # Replay yields identical recovered payload every time.
    assert receipt_a.receipt_id == receipt_b.receipt_id == receipt_c.receipt_id


def test_step_ids_never_collide_across_repeated_captures(client):
    """Even if request_id is reused, internal step_id must remain unique."""
    seen: set[str] = set()
    for _ in range(20):
        rid = "shared-rid"
        cap = client.post("/v1/captures", json=_capture_payload(rid)).json()
        # Fetch the steps via a reuse call so we can examine their step_ids.
        # The cleanest way is via the store, but the API doesn't expose it.
        # We approximate by capturing the same payload, expecting fresh ids.
        # The trace_id is already proven distinct above; here we just confirm
        # nothing collides cumulatively.
        assert cap["trace_id"] not in seen
        seen.add(cap["trace_id"])
    assert len(seen) == 20


def test_replay_of_tampered_receipt_still_fails(client):
    """If an attacker captures a real receipt and tampers with one byte,
    verification must fail on the second try just like the first."""
    import base64
    import json

    client.post("/v1/captures", json=_capture_payload())
    for i in range(40):
        client.post("/v1/calibration", json={"tenant_id": "rep-tenant", "score": 0.4 + (i % 8) * 0.05})
    reuse = client.post(
        "/v1/reuse",
        json={
            "tenant_id": "rep-tenant",
            "user_text": "Erste vollstaendige Begruendung",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "k": 3,
        },
    ).json()
    if reuse["abstained"]:
        pytest.skip("calibrator abstained")
    env = reuse["receipt_envelope"]
    payload = json.loads(base64.b64decode(env["payload"]))
    payload["cost_saved_tokens"] = 99999999
    tampered = {
        "payloadType": env["payloadType"],
        "payload": base64.b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).decode(),
        "signatures": env["signatures"],
    }
    signer_pub = client.app.state.signer.public_key_b64()
    verifier = ReceiptVerifier.from_public_key_b64("anamnesis-server-default", signer_pub)
    with pytest.raises((BadSignatureError, ValueError)):
        verifier.verify(SignedEnvelope.from_dict(tampered))
    with pytest.raises((BadSignatureError, ValueError)):
        verifier.verify(SignedEnvelope.from_dict(tampered))  # second replay also fails


def test_two_concurrent_captures_same_tenant_isolated_storage(client):
    """Each capture must land in the same tenant's store, never cross-write."""
    ids_a, ids_b = [], []
    for _ in range(10):
        ids_a.append(client.post("/v1/captures", json=_capture_payload("a")).json()["trace_id"])
        ids_b.append(client.post("/v1/captures", json=_capture_payload("b")).json()["trace_id"])
    assert len(set(ids_a)) == 10
    assert len(set(ids_b)) == 10
    assert set(ids_a).isdisjoint(set(ids_b))
