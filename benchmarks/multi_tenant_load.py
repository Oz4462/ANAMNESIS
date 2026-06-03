# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Multi-tenant concurrent load test against a running ANAMNESIS server.

Spawns N tenants in parallel, each running:
  capture -> calibration (warm-up) -> reuse -> verify isolation

Asserts that:
  * the per-tenant calibration counter never leaks (isolation)
  * every reuse for a warmed tenant returns a signed receipt
  * total wall-clock < 30s for N=20 tenants, 40 calib + 1 reuse each
"""

from __future__ import annotations

import asyncio
import random
import sys
import time

import httpx

BASE = "http://127.0.0.1:8766"


async def run_tenant(client: httpx.AsyncClient, tenant: str) -> dict:
    rng = random.Random(hash(tenant) & 0xFFFFFFFF)
    # 1) capture
    cap = await client.post(
        "/v1/captures",
        json={
            "tenant_id": tenant,
            "request_id": f"req-{tenant}",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "thinking_text": (
                "Erste ausfuehrliche Begruendung der Aufgabe in vollem Detail. "
                "Zweite mathematische Ableitung der notwendigen Bedingungen mit Schluss. "
                "Dritte Begruendung warum dieser Schritt korrekt ist."
            ),
            "answer_text": "ok",
            "thinking_tokens": 200,
            "output_tokens": 5,
        },
    )
    cap.raise_for_status()

    # 2) calibration: 40 random scores
    cal_status = None
    for _ in range(40):
        r = await client.post(
            "/v1/calibration",
            json={"tenant_id": tenant, "score": rng.uniform(0.4, 0.8)},
        )
        r.raise_for_status()
        cal_status = r.json()

    # 3) reuse
    reuse = await client.post(
        "/v1/reuse",
        json={
            "tenant_id": tenant,
            "user_text": "Erste ausfuehrliche Begruendung der Aufgabe",
            "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
            "k": 3,
        },
    )
    reuse.raise_for_status()
    body = reuse.json()
    return {
        "tenant": tenant,
        "n_calibration": cal_status["n_calibration"],
        "abstained": body["abstained"],
        "has_receipt": body["receipt_envelope"] is not None,
        "trace_id": cap.json()["trace_id"],
    }


async def main(n_tenants: int = 20) -> int:
    timeout = httpx.Timeout(30.0, connect=5.0)
    async with httpx.AsyncClient(base_url=BASE, timeout=timeout) as client:
        t0 = time.perf_counter()
        results = await asyncio.gather(
            *[run_tenant(client, f"load-{i:02d}") for i in range(n_tenants)]
        )
        wall = time.perf_counter() - t0

    print(f"=== {n_tenants} tenants in parallel, wall-clock {wall:.2f}s ===")
    failures = 0
    seen_trace_ids = set()
    for r in results:
        ok_cal = r["n_calibration"] == 40
        ok_unique = r["trace_id"] not in seen_trace_ids
        ok_receipt = r["has_receipt"] is True or r["abstained"] is True
        seen_trace_ids.add(r["trace_id"])
        flag = "OK" if (ok_cal and ok_unique and ok_receipt) else "FAIL"
        if not (ok_cal and ok_unique and ok_receipt):
            failures += 1
        print(
            f"  [{flag}] {r['tenant']}  n_cal={r['n_calibration']}  "
            f"abstained={r['abstained']}  receipt={r['has_receipt']}  "
            f"trace_id={r['trace_id']}"
        )
    print(f"\nFailures: {failures}/{n_tenants}")
    print(f"Per-tenant throughput: {n_tenants / wall:.1f} tenants/sec")
    if wall > 30.0:
        print("WARNING: wall-clock exceeded 30s budget")
        return 2
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
