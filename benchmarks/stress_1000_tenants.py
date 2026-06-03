# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""1000 concurrent tenants stress against a running server (port 8768).

Each tenant does capture + 10 calibration scores + reuse. We cap concurrency
with a semaphore (default 100) so we don't open 1000 sockets at once.

Reports:
  * total wall-clock
  * P50/P95/P99 per-tenant latency
  * any HTTP failures
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time

import httpx

BASE = "http://127.0.0.1:8768"


async def one_tenant(client: httpx.AsyncClient, tenant: str, sem: asyncio.Semaphore) -> tuple[bool, float]:
    async with sem:
        t0 = time.perf_counter()
        try:
            cap = await client.post(
                "/v1/captures",
                json={
                    "tenant_id": tenant,
                    "request_id": f"req-{tenant}",
                    "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
                    "thinking_text": (
                        "Erste vollstaendige Begruendung der Aufgabe im Detail. "
                        "Zweite mathematische Ableitung Schritt fuer Schritt."
                    ),
                    "answer_text": "ok",
                    "thinking_tokens": 50,
                    "output_tokens": 5,
                },
            )
            cap.raise_for_status()

            for i in range(10):
                r = await client.post(
                    "/v1/calibration",
                    json={"tenant_id": tenant, "score": 0.4 + (i % 8) * 0.05},
                )
                r.raise_for_status()

            reuse = await client.post(
                "/v1/reuse",
                json={
                    "tenant_id": tenant,
                    "user_text": "Erste vollstaendige Begruendung",
                    "model": {"provider": "anthropic", "name": "claude-opus-4-7"},
                    "k": 3,
                },
            )
            reuse.raise_for_status()
            return True, (time.perf_counter() - t0) * 1000
        except Exception:
            return False, (time.perf_counter() - t0) * 1000


async def main(n_tenants: int = 1000, concurrency: int = 100) -> int:
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_keepalive_connections=concurrency, max_connections=concurrency * 2)
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(base_url=BASE, timeout=timeout, limits=limits) as client:
        t0 = time.perf_counter()
        results = await asyncio.gather(
            *[one_tenant(client, f"stress-{i:04d}", sem) for i in range(n_tenants)]
        )
        wall = time.perf_counter() - t0

    oks = [lat for ok, lat in results if ok]
    bads = [lat for ok, lat in results if not ok]
    if not oks:
        print("ALL FAILED")
        return 1
    oks.sort()
    p50 = statistics.median(oks)
    p95 = oks[int(0.95 * len(oks))]
    p99 = oks[int(0.99 * len(oks))]

    print(f"=== {n_tenants} tenants, max concurrency {concurrency} ===")
    print(f"  wall-clock:    {wall:.2f}s")
    print(f"  throughput:    {n_tenants / wall:.1f} tenants/sec")
    print(f"  ok:            {len(oks)}  ({len(oks) / n_tenants * 100:.1f}%)")
    print(f"  failed:        {len(bads)}")
    print(f"  per-tenant latency p50/p95/p99: {p50:.0f}/{p95:.0f}/{p99:.0f} ms")
    return 0 if not bads else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
