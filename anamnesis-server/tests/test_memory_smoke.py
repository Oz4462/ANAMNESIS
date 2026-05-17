"""Memory-leak smoke test.

Drive the FastAPI app through 2000 capture+calibrate+reuse cycles in the
same process and assert the RSS doesn't grow without bound. Some growth is
expected (the calibrator + trace store hold genuine state), but the curve
should be sub-linear in requests once the tenant is warm.

This catches:
  * orphan async tasks
  * unbounded caches in the FastAPI/uvicorn stack
  * step lists or vectors that aren't reused across requests
"""

from __future__ import annotations

import gc
import os

import psutil
import pytest
from anamnesis_server.main import create_app
from fastapi.testclient import TestClient


@pytest.mark.slow
def test_rss_grows_sub_linearly_under_steady_load():
    proc = psutil.Process(os.getpid())
    app = create_app()
    client = TestClient(app)
    tenant = "memory-smoke"

    # warm-up: one capture + 40 calibrations so retrieval is enabled
    client.post(
        "/v1/captures",
        json={
            "tenant_id": tenant,
            "request_id": "warmup",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "thinking_text": (
                "Erste vollstaendige Begruendung der Aufgabe im Detail. "
                "Zweite mathematische Ableitung der notwendigen Bedingungen mit Schluss."
            ),
            "answer_text": "ok",
            "thinking_tokens": 100,
            "output_tokens": 5,
        },
    )
    for i in range(40):
        client.post(
            "/v1/calibration",
            json={"tenant_id": tenant, "score": 0.4 + (i % 8) * 0.05},
        )

    gc.collect()
    rss_after_warmup = proc.memory_info().rss / (1024 * 1024)

    n_iter = 2000
    checkpoints = [500, 1000, 1500, 2000]
    rss_at: dict[int, float] = {}

    for i in range(n_iter):
        client.post(
            "/v1/reuse",
            json={
                "tenant_id": tenant,
                "user_text": f"Variant query number {i}",
                "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
                "k": 3,
            },
        )
        if i + 1 in checkpoints:
            gc.collect()
            rss_at[i + 1] = proc.memory_info().rss / (1024 * 1024)

    print(f"\n  RSS after warmup:        {rss_after_warmup:6.1f} MB")
    for n, rss in rss_at.items():
        print(f"  RSS after {n:>5} reuses: {rss:6.1f} MB  (+{rss - rss_after_warmup:+.1f})")

    # Allow ~60 MB headroom across 2000 requests; anything more is a leak.
    # That budget is generous because Python + numpy + sqlite already start
    # around 80-120 MB depending on the platform.
    growth = rss_at[2000] - rss_after_warmup
    assert growth < 60.0, f"suspected leak: RSS grew {growth:.1f} MB across 2000 reuses"


def test_calibrator_window_does_not_grow_past_max():
    """The sliding window of scores must never exceed max_window."""
    app = create_app()
    client = TestClient(app)
    tenant = "window-bound"

    for i in range(5000):
        r = client.post(
            "/v1/calibration",
            json={"tenant_id": tenant, "score": (i % 100) / 100.0},
        )
        assert r.status_code == 200
    status = client.get(f"/v1/calibration/{tenant}").json()
    # Server default is min_calibration=30, max_window=4096.
    assert status["n_calibration"] <= 4096
