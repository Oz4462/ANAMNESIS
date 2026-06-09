# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Tests for the savings calculator.

The numbers it reports become the basis of any POC conversation, so the
math must be transparent and the edge cases predictable.
"""

from __future__ import annotations

import json

import pytest
from anamnesis.savings import (
    PROVIDER_REGISTRY,
    ProviderPricing,
    SavingsReport,
    WorkloadRow,
    load_workload,
    load_workload_csv,
    load_workload_jsonl,
    run_savings_simulation,
)


def _synthetic_redundant_workload(n_unique: int = 5, repeats: int = 20) -> list[WorkloadRow]:
    """Generate a workload where each unique query is repeated `repeats` times.

    Under this construction, after the first occurrence of each query the
    other (repeats - 1) occurrences should be reuse candidates -- the
    calculator must detect that and report a high savings rate.
    """
    queries = [
        "compute area of triangle from base and height",
        "solve quadratic by completing the square method",
        "translate German sentence to English using dictionary",
        "bake sourdough loaf with rye flour overnight oven",
        "find volume of sphere with radius r using formula",
    ][:n_unique]
    rows: list[WorkloadRow] = []
    for _ in range(repeats):
        for q in queries:
            rows.append(WorkloadRow(query=q, thinking_tokens=1000, output_tokens=100))
    return rows


def test_savings_on_highly_redundant_workload():
    rows = _synthetic_redundant_workload(n_unique=5, repeats=20)
    report = run_savings_simulation(
        rows,
        pricing=ProviderPricing.claude_opus_4_7(),
        alpha=0.1,
        min_calibration=30,
    )
    assert isinstance(report, SavingsReport)
    # Redundant workload => reuse rate should be high.
    assert report.reuse_rate_pct > 50.0, f"got reuse_rate={report.reuse_rate_pct}"
    assert report.savings_rate_pct > 50.0
    # Total tokens calculated correctly.
    assert report.total_thinking_tokens == report.total_queries * 1000


def test_savings_on_diverse_workload_is_modest():
    """All queries unique => low reuse rate."""
    rows = [
        WorkloadRow(query=f"completely unique question number {i} about topic {i}", thinking_tokens=1000)
        for i in range(200)
    ]
    report = run_savings_simulation(
        rows,
        pricing=ProviderPricing.claude_opus_4_7(),
        alpha=0.1,
        min_calibration=30,
    )
    assert report.reuse_rate_pct < 30.0, f"diverse workload reuse should be low, got {report.reuse_rate_pct}"


def test_savings_dollar_math_is_exact():
    rows = [WorkloadRow(query=f"q{i}", thinking_tokens=1_000_000) for i in range(100)]
    pricing = ProviderPricing(name="test", thinking_usd_per_mtok=10.0, output_usd_per_mtok=0.0)
    report = run_savings_simulation(
        rows,
        pricing=pricing,
        alpha=0.1,
        min_calibration=30,
    )
    # Each query = 1M thinking tokens at $10/Mtok = $10
    # total cost = total_queries * $10
    expected_total = report.total_queries * 10.0
    assert report.total_thinking_cost_usd == pytest.approx(expected_total)


def test_reuse_threshold_is_a_real_knob():
    """Regression guard for the warm-up calibration bug.

    With the old self-similarity calibration tau collapsed to 0, so the reuse
    rate was identical (and near-zero) for every threshold. A meaningful
    simulation must let a larger accepted drift admit strictly more reuse.
    """
    rows = [
        WorkloadRow(query=f"completely unique question number {i} about topic {i}",
                    thinking_tokens=1000)
        for i in range(200)
    ]
    tight = run_savings_simulation(
        rows, pricing=ProviderPricing.claude_opus_4_7(), reuse_threshold=0.10
    )
    loose = run_savings_simulation(
        rows, pricing=ProviderPricing.claude_opus_4_7(), reuse_threshold=0.30
    )
    assert loose.reuse_rate_pct > tight.reuse_rate_pct + 20.0, (
        f"threshold had no effect: tight={tight.reuse_rate_pct} "
        f"loose={loose.reuse_rate_pct} (calibration may be degenerate)"
    )
    # tau is recorded verbatim as the operator's accepted drift policy.
    assert tight.tau == 0.10
    assert loose.tau == 0.30


def test_invalid_reuse_threshold_raises():
    rows = [WorkloadRow(query=f"q{i}", thinking_tokens=10) for i in range(100)]
    with pytest.raises(ValueError, match="reuse_threshold"):
        run_savings_simulation(
            rows, pricing=ProviderPricing.claude_opus_4_7(), reuse_threshold=2.5
        )


def test_too_few_rows_raises():
    rows = [WorkloadRow(query="q", thinking_tokens=10)] * 10
    with pytest.raises(ValueError):
        run_savings_simulation(rows, pricing=ProviderPricing.claude_opus_4_7())


def test_load_jsonl_round_trip(tmp_path):
    f = tmp_path / "workload.jsonl"
    f.write_text(
        "\n".join(
            json.dumps({"query": f"q{i}", "thinking_tokens": 100, "output_tokens": 10})
            for i in range(5)
        )
    )
    rows = list(load_workload_jsonl(f))
    assert len(rows) == 5
    assert rows[0].query == "q0"
    assert rows[0].thinking_tokens == 100


def test_load_jsonl_skips_empty_lines(tmp_path):
    f = tmp_path / "ws.jsonl"
    f.write_text('{"query":"a","thinking_tokens":1}\n\n{"query":"b","thinking_tokens":2}\n')
    rows = list(load_workload_jsonl(f))
    assert len(rows) == 2


def test_load_jsonl_invalid_line_raises(tmp_path):
    f = tmp_path / "bad.jsonl"
    f.write_text('{"query":"a","thinking_tokens":1}\nnot-json\n')
    with pytest.raises(ValueError, match="line 2"):
        list(load_workload_jsonl(f))


def test_load_csv_round_trip(tmp_path):
    f = tmp_path / "workload.csv"
    f.write_text(
        "query,thinking_tokens,output_tokens\n"
        + "\n".join(f"q{i},100,10" for i in range(5))
        + "\n"
    )
    rows = list(load_workload_csv(f))
    assert len(rows) == 5
    assert rows[0].query == "q0"
    assert rows[0].thinking_tokens == 100
    assert rows[0].output_tokens == 10


def test_load_csv_output_tokens_optional(tmp_path):
    f = tmp_path / "workload.csv"
    f.write_text("query,thinking_tokens\na,5\nb,7\n")
    rows = list(load_workload_csv(f))
    assert [r.thinking_tokens for r in rows] == [5, 7]
    assert all(r.output_tokens == 0 for r in rows)


def test_load_csv_skips_blank_lines(tmp_path):
    f = tmp_path / "workload.csv"
    f.write_text("query,thinking_tokens\na,1\n\nb,2\n,\n")
    rows = list(load_workload_csv(f))
    assert [r.query for r in rows] == ["a", "b"]


def test_load_csv_missing_required_header_raises(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("query,output_tokens\na,1\n")
    with pytest.raises(ValueError, match="thinking_tokens"):
        list(load_workload_csv(f))


def test_load_csv_non_integer_tokens_raises(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("query,thinking_tokens\na,1\nb,not-a-number\n")
    with pytest.raises(ValueError, match="line 3"):
        list(load_workload_csv(f))


def test_load_workload_dispatches_on_extension(tmp_path):
    csv_f = tmp_path / "w.csv"
    csv_f.write_text("query,thinking_tokens\na,1\n")
    jsonl_f = tmp_path / "w.jsonl"
    jsonl_f.write_text('{"query":"b","thinking_tokens":2}\n')
    assert list(load_workload(csv_f))[0].query == "a"
    assert list(load_workload(jsonl_f))[0].query == "b"


def test_provider_registry_has_known_models():
    assert "claude-opus-4-7" in PROVIDER_REGISTRY
    assert "o3-pro" in PROVIDER_REGISTRY
    assert "deepseek-r1" in PROVIDER_REGISTRY
    assert PROVIDER_REGISTRY["o3-pro"].thinking_usd_per_mtok == 20.0


def test_savings_report_to_dict_is_audit_ready():
    rows = _synthetic_redundant_workload(n_unique=5, repeats=30)
    report = run_savings_simulation(rows, pricing=ProviderPricing.deepseek_r1())
    d = report.to_dict()
    assert d["provider"] == "deepseek-r1"
    assert "bound" in d
    assert "tau" in d["bound"]
    assert "alpha" in d["bound"]
    assert "n_calibration" in d["bound"]


def test_savings_with_zero_token_rows():
    """Rows with 0 thinking tokens still get counted but contribute $0."""
    rows = [WorkloadRow(query=f"q{i}", thinking_tokens=0) for i in range(100)]
    report = run_savings_simulation(rows, pricing=ProviderPricing.claude_opus_4_7())
    assert report.total_thinking_tokens == 0
    assert report.total_thinking_cost_usd == 0.0
    assert report.savings_rate_pct == 0.0
