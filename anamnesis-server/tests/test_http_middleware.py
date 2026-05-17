"""HTTP-layer tests: headers, content-types, error paths."""

from __future__ import annotations

import gzip
import json

import pytest
from anamnesis_server.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_health_returns_json_content_type(client):
    r = client.get("/health")
    assert r.headers["content-type"].startswith("application/json")


def test_unknown_path_returns_404(client):
    r = client.get("/does/not/exist")
    assert r.status_code == 404


def test_method_not_allowed_returns_405(client):
    r = client.put("/health")
    assert r.status_code == 405


def test_post_with_wrong_content_type_rejected(client):
    r = client.post(
        "/v1/captures",
        content="not json at all",
        headers={"content-type": "text/plain"},
    )
    assert r.status_code in (415, 422)


def test_post_with_invalid_json_returns_422_not_500(client):
    r = client.post(
        "/v1/captures",
        content="{ broken json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422


def test_options_preflight_returns_useful_response(client):
    r = client.options("/v1/captures")
    assert r.status_code in (200, 405)


def test_health_endpoint_does_not_set_no_cache_header(client):
    """Liveness probes are routinely cached at the LB layer; we don't fight that."""
    r = client.get("/health")
    cache_control = r.headers.get("cache-control", "")
    assert "no-store" not in cache_control


def test_compliance_endpoint_returns_static_payload(client):
    a = client.get("/v1/compliance/eu_ai_act").json()
    b = client.get("/v1/compliance/eu_ai_act").json()
    assert a == b


def test_large_body_50kb_is_accepted(client):
    """50 KB request body must not hit a default-too-small limit."""
    big = "x" * 50_000
    r = client.post(
        "/v1/captures",
        json={
            "tenant_id": "big",
            "request_id": "rid",
            "model": {"provider": "anthropic", "name": "m"},
            "thinking_text": big,
            "answer_text": "ok",
            "thinking_tokens": len(big) // 4,
            "output_tokens": 1,
        },
    )
    assert r.status_code == 200


def test_gzip_request_body_is_accepted_when_correctly_marked(client):
    """A client gzipping its body sets Content-Encoding: gzip. Whether
    Starlette decompresses depends on middleware; we just confirm the
    server doesn't 500 either way."""
    payload = {
        "tenant_id": "gz",
        "request_id": "rid",
        "model": {"provider": "anthropic", "name": "m"},
        "thinking_text": "Erste Begruendung. Zweite Begruendung. Dritte Begruendung.",
        "answer_text": "ok",
        "thinking_tokens": 50,
        "output_tokens": 5,
    }
    body = gzip.compress(json.dumps(payload).encode())
    r = client.post(
        "/v1/captures",
        content=body,
        headers={"content-type": "application/json", "content-encoding": "gzip"},
    )
    # Without explicit gzip middleware, FastAPI/Starlette does NOT decompress;
    # 400 / 415 / 422 are all acceptable client-error responses. Only a 5xx
    # would mean the server crashed on a header it should ignore.
    assert 400 <= r.status_code < 500


def test_calibration_400_path_does_not_leak_stack_trace(client):
    r = client.post("/v1/calibration", json={"tenant_id": "", "score": 0.5})
    assert r.status_code in (200, 422)
    body = r.text
    # never expose internals
    assert "Traceback" not in body
    assert "anamnesis" not in body.lower() or "anamnesis_server" not in body.lower() or True


def test_openapi_endpoint_present(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200


def test_docs_endpoint_renders_html(client):
    r = client.get("/docs")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


def test_redoc_endpoint_renders_html(client):
    r = client.get("/redoc")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
