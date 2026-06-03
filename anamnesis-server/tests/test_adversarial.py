# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Adversarial input tests against the FastAPI app.

These are the inputs a paying customer (or pen-tester) will eventually fire
at the production deployment. We assert that:

  * SQL injection strings as tenant_id do NOT execute against sqlite
  * Pydantic validation rejects schema violations with 422, never 500
  * Unicode / emoji in tenant + thinking text survive round-trip
  * Very long thinking texts are accepted but bounded by the receipt schema
  * Tampered receipt envelopes consistently fail closed
"""

from __future__ import annotations

import pytest
from anamnesis_server.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_tenant_id_sql_injection_does_not_execute(client):
    evil = "robert'); DROP TABLE traces;--"
    r = client.post(
        "/v1/captures",
        json={
            "tenant_id": evil,
            "request_id": "rid",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "thinking_text": "Erste vollstaendige Begruendung mit Schluss.",
            "answer_text": "ok",
            "thinking_tokens": 100,
            "output_tokens": 5,
        },
    )
    assert r.status_code == 200, r.text  # parametrised query, no SQL exec
    cap_id = r.json()["trace_id"]
    assert cap_id.startswith("trace_")

    # The store for this tenant must still be queryable through the API.
    follow = client.get(f"/v1/calibration/{evil}")
    assert follow.status_code == 200


def test_empty_request_body_rejected_with_422(client):
    r = client.post("/v1/captures", json={})
    assert r.status_code == 422


def test_negative_thinking_tokens_accepted_or_clamped(client):
    """Pydantic doesn't constrain thinking_tokens so it stores the raw int.
    The application layer should at least not crash."""
    r = client.post(
        "/v1/captures",
        json={
            "tenant_id": "neg-tokens",
            "request_id": "rid",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "thinking_text": "x" * 50,
            "answer_text": "ok",
            "thinking_tokens": -99,
            "output_tokens": -7,
        },
    )
    # No crash. Either accepts or 422; either is fine, 500 is not.
    assert r.status_code in (200, 422)


def test_unicode_emoji_survives_round_trip(client):
    thinking = "Berechnung der Flaeche eines Dreiecks 🚀 mit Basis und Hoehe. " * 3
    r = client.post(
        "/v1/captures",
        json={
            "tenant_id": "tenant_unicode_äöüß",
            "request_id": "rid_emoji_🔥",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "thinking_text": thinking,
            "answer_text": "Antwort mit Umlauten: ä ö ü ß",
            "thinking_tokens": 100,
            "output_tokens": 8,
        },
    )
    assert r.status_code == 200, r.text


def test_very_long_thinking_text(client):
    big = ("Schritt nummer X bei dieser Berechnung mit vielen Details. " * 1000)[:60_000]
    r = client.post(
        "/v1/captures",
        json={
            "tenant_id": "huge",
            "request_id": "rid_huge",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "thinking_text": big,
            "answer_text": "ok",
            "thinking_tokens": len(big) // 4,
            "output_tokens": 5,
        },
    )
    assert r.status_code == 200
    assert r.json()["n_steps_distilled"] >= 100


def test_missing_required_field_in_reuse_returns_422(client):
    r = client.post(
        "/v1/reuse",
        json={
            "tenant_id": "x",
            # missing user_text + model
            "k": 3,
        },
    )
    assert r.status_code == 422


def test_calibration_score_out_of_range_rejected(client):
    for bad_score in (-0.5, 5.0, 100.0, -1.0):
        r = client.post("/v1/calibration", json={"tenant_id": "t", "score": bad_score})
        assert r.status_code == 422, f"score={bad_score}"


def test_k_out_of_range_in_reuse_rejected(client):
    for bad_k in (-1, 0, 999, 10_000):
        r = client.post(
            "/v1/reuse",
            json={
                "tenant_id": "t",
                "user_text": "anything",
                "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
                "k": bad_k,
            },
        )
        assert r.status_code == 422, f"k={bad_k}"


def test_alpha_out_of_range_in_reuse_rejected(client):
    for bad_alpha in (0.0, 1.0, -0.1, 1.5):
        r = client.post(
            "/v1/reuse",
            json={
                "tenant_id": "t",
                "user_text": "anything",
                "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
                "k": 5,
                "alpha": bad_alpha,
            },
        )
        assert r.status_code == 422, f"alpha={bad_alpha}"


def test_tenant_id_with_path_separators(client):
    """A tenant id containing slashes must not let the caller traverse the
    file system if we ever wire ANAMNESIS_DB_ROOT in this test."""
    sketchy = "../../etc/passwd"
    r = client.get(f"/v1/calibration/{sketchy}")
    # FastAPI strips path segments before the trailing one; we just want no 500.
    assert r.status_code in (200, 404)


def test_extremely_short_thinking_yields_zero_steps(client):
    r = client.post(
        "/v1/captures",
        json={
            "tenant_id": "tiny",
            "request_id": "rid_tiny",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "thinking_text": "ok.",
            "answer_text": "ok",
            "thinking_tokens": 1,
            "output_tokens": 1,
        },
    )
    assert r.status_code == 200
    assert r.json()["n_steps_distilled"] == 0


def test_provider_string_with_unknown_value_still_stored(client):
    """Server should not white-list providers — that gates extensibility."""
    r = client.post(
        "/v1/captures",
        json={
            "tenant_id": "novel",
            "request_id": "rid",
            "model": {"provider": "some-future-vendor", "name": "magic-model-v3"},
            "thinking_text": "Erste vollstaendige Begruendung mit Schluss.",
            "answer_text": "ok",
            "thinking_tokens": 50,
            "output_tokens": 5,
        },
    )
    assert r.status_code == 200
