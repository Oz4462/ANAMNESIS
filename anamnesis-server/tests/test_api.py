"""End-to-end tests for the ANAMNESIS FastAPI app."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from anamnesis.receipts import ReceiptSigner, ReceiptVerifier, SignedEnvelope

from anamnesis_server.main import create_app


@pytest.fixture()
def signer() -> ReceiptSigner:
    return ReceiptSigner.generate("test-issuer")


@pytest.fixture()
def client(signer):
    app = create_app(signer=signer)
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["eu_ai_act_article_15"] is True
    assert body["eu_ai_act_article_50"] is True


def test_compliance_matrix(client):
    r = client.get("/v1/compliance/eu_ai_act")
    assert r.status_code == 200
    body = r.json()
    assert "article_15" in body
    assert "article_50" in body
    assert any("accuracy" in c["summary"].lower() for c in body["article_15"])


def test_calibration_starts_cold(client):
    r = client.get("/v1/calibration/tenant_x")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    assert body["n_calibration"] == 0
    assert 0.0 < body["alpha"] < 1.0


def test_calibration_add_warms_it_up(client):
    for s in (0.05, 0.1, 0.15, 0.2):
        r = client.post("/v1/calibration", json={"tenant_id": "tenant_y", "score": s})
        assert r.status_code == 200, r.text
    final = client.get("/v1/calibration/tenant_y").json()
    assert final["n_calibration"] == 4


def test_capture_persists_and_distils(client):
    payload = {
        "tenant_id": "t1",
        "request_id": "req1",
        "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
        "thinking_text": (
            "Erste Beobachtung der Aufgabe. "
            "Zweite Ableitung der notwendigen Bedingungen. "
            "Dritte Begruendung warum Schritt vier folgt."
        ),
        "answer_text": "42",
        "thinking_tokens": 500,
        "output_tokens": 8,
        "metadata": {"stop_reason": "end_turn"},
    }
    r = client.post("/v1/captures", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["trace_id"].startswith("trace_")
    assert body["content_hash"].startswith("sha256:")
    assert body["n_steps_distilled"] >= 3


def test_reuse_cold_returns_candidates_but_abstains(client):
    cap = {
        "tenant_id": "t2",
        "request_id": "rA",
        "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
        "thinking_text": "Compute the area of a triangle from base and height.",
        "answer_text": "result",
        "thinking_tokens": 200,
        "output_tokens": 5,
    }
    client.post("/v1/captures", json=cap)
    r = client.post(
        "/v1/reuse",
        json={
            "tenant_id": "t2",
            "user_text": "How do I compute area of a triangle?",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "k": 3,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["abstained"] is True
    assert body["bound"] is None
    assert body["receipt_envelope"] is None
    assert len(body["candidates"]) >= 1


def test_reuse_warm_returns_signed_receipt(client, signer):
    tenant = "t3"
    cap = {
        "tenant_id": tenant,
        "request_id": "rB",
        "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
        "thinking_text": (
            "Compute the area of a triangle from base and height. "
            "The formula is one half times base times height. "
            "Substitute the known values and arrive at the area in square units."
        ),
        "answer_text": "ok",
        "thinking_tokens": 300,
        "output_tokens": 5,
    }
    r1 = client.post("/v1/captures", json=cap)
    assert r1.status_code == 200

    for s in [0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7] * 6:
        r2 = client.post("/v1/calibration", json={"tenant_id": tenant, "score": s})
        assert r2.status_code == 200

    r3 = client.post(
        "/v1/reuse",
        json={
            "tenant_id": tenant,
            "user_text": "How do I compute area of a triangle?",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "k": 5,
        },
    )
    assert r3.status_code == 200, r3.text
    body = r3.json()
    assert body["bound"] is not None
    if not body["abstained"]:
        env_dict = body["receipt_envelope"]
        assert env_dict is not None
        envelope = SignedEnvelope.from_dict(env_dict)
        verifier = ReceiptVerifier.from_public_key_b64("test-issuer", signer.public_key_b64())
        receipt = verifier.verify(envelope)
        assert receipt.tenant_id == tenant
        assert receipt.bound.alpha == pytest.approx(0.1, abs=0.01)
        assert len(receipt.retrieved_step_ids) >= 1
        assert receipt.eu_ai_act_claims["article_15"] is True


def test_calibration_rejects_invalid_score(client):
    r = client.post("/v1/calibration", json={"tenant_id": "t", "score": 5.0})
    assert r.status_code == 422


def test_calibration_status_unknown_tenant_lazy_created(client):
    r = client.get("/v1/calibration/never_used_before")
    assert r.status_code == 200
    assert r.json()["n_calibration"] == 0
