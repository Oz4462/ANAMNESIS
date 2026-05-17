"""Verify FastAPI generates a valid OpenAPI 3.x spec.

A spec that doesn't validate is a spec that won't work with auditor tooling
(redocly, swagger-codegen, mintlify, etc.). For an EU-AI-Act audit product
the OpenAPI surface itself is part of what's reviewed.
"""

from __future__ import annotations

import pytest
from anamnesis_server.main import create_app
from fastapi.testclient import TestClient
from openapi_spec_validator import validate


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_openapi_spec_is_valid_openapi_30_or_31(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    # openapi-spec-validator raises if the spec is not well-formed.
    validate(spec)


def test_openapi_exposes_all_documented_endpoints(client):
    r = client.get("/openapi.json")
    spec = r.json()
    paths = set(spec["paths"].keys())
    expected = {
        "/health",
        "/v1/compliance/eu_ai_act",
        "/v1/calibration/{tenant_id}",
        "/v1/calibration",
        "/v1/captures",
        "/v1/reuse",
    }
    assert expected.issubset(paths), f"missing paths: {expected - paths}"


def test_openapi_schemas_have_required_request_models(client):
    spec = client.get("/openapi.json").json()
    schemas = spec.get("components", {}).get("schemas", {})
    for required in ("CaptureIn", "ReuseQueryIn", "CalibrationIn"):
        assert required in schemas, f"missing schema: {required}"


def test_openapi_reuse_endpoint_documents_alpha_range(client):
    spec = client.get("/openapi.json").json()
    reuse_in = spec["components"]["schemas"]["ReuseQueryIn"]
    alpha = reuse_in["properties"]["alpha"]
    # Pydantic constraint translates to JSON schema exclusiveMinimum + exclusiveMaximum.
    serialised = str(alpha)
    assert "exclusiveMinimum" in serialised or "minimum" in serialised
    assert "exclusiveMaximum" in serialised or "maximum" in serialised
