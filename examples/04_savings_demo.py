"""Generate a synthetic workload and compute the savings report.

Run with: uv run python examples/04_savings_demo.py

The demo workload mixes 30 unique queries with 5 repetitions each (mirrors
a typical legal/finance/code-AI day where users ask variants of the same
question). The output is what a prospect would see when they paste their
own JSONL transcript.
"""

from __future__ import annotations

import json

from anamnesis.savings import (
    PROVIDER_REGISTRY,
    WorkloadRow,
    run_savings_simulation,
)


def build_workload() -> list[WorkloadRow]:
    base = [
        "compute area of a triangle from base and height",
        "solve a linear equation a*x + b = 0 for x",
        "translate a German sentence to English with context",
        "find the volume of a sphere with radius r",
        "compute the eigenvalues of a 2x2 symmetric matrix",
        "explain the Pythagorean theorem with example",
        "review a non-disclosure agreement for jurisdiction clause",
        "draft a refund-policy clause for a SaaS contract",
        "summarise an earnings call transcript in three bullets",
        "rewrite a paragraph in plain German for a customer email",
    ]
    rows: list[WorkloadRow] = []
    for _ in range(10):  # 10 days of usage
        for q in base:
            rows.append(WorkloadRow(query=q, thinking_tokens=8000, output_tokens=400))
    # add 20 unique-ish queries that won't have a near-neighbour
    for i in range(20):
        rows.append(WorkloadRow(query=f"genuinely novel query number {i}", thinking_tokens=8000))
    return rows


def main() -> None:
    rows = build_workload()
    print(f"workload: {len(rows)} queries\n")

    for name, pricing in PROVIDER_REGISTRY.items():
        report = run_savings_simulation(rows, pricing=pricing, alpha=0.1, min_calibration=30)
        print(f"=== {name} (${pricing.thinking_usd_per_mtok}/MTok thinking) ===")
        print(json.dumps(report.to_dict(), indent=2))
        print(
            f"  SUMMARY: {report.reuse_rate_pct:.0f}% reusable, "
            f"${report.reused_thinking_cost_usd:.2f} saved out of "
            f"${report.total_thinking_cost_usd:.2f}"
        )
        print()


if __name__ == "__main__":
    main()
