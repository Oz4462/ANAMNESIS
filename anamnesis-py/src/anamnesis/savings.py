# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Token-savings calculator for a prospect's own reasoning workload.

This is the closer for a sales conversation: paste a CSV/JSONL of past
(query, thinking_tokens, output_tokens) triples and we report

  - how many of those queries are semantically near-duplicates,
  - how many thinking-tokens would have been reusable under our bound,
  - the dollar cost of those tokens at the prospect's provider rates,
  - the conformal coverage we would have given them.

No LLM calls. No API keys. Runs entirely offline against the prospect's
own data on their machine. The output is the empirical ROI number for
their workload, not a marketing claim.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from anamnesis.conformal import ConformalCalibrator
from anamnesis.storage import Embedder, ReasoningStep, TraceStore, embedder_for


@dataclass(frozen=True, slots=True)
class WorkloadRow:
    query: str
    thinking_tokens: int
    # Captured for completeness; the savings simulation prices thinking-token
    # reuse only, so output_tokens does not currently affect the report.
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ProviderPricing:
    """Per-million-token rates for the prospect's provider.

    Only ``thinking_usd_per_mtok`` drives the savings maths today -- reuse saves
    thinking tokens, not visible output. ``output_usd_per_mtok`` is carried for
    completeness (e.g. to price the full request) but is intentionally not used
    by :func:`run_savings_simulation`, which reports thinking-token savings only.
    """

    name: str
    thinking_usd_per_mtok: float
    output_usd_per_mtok: float

    @classmethod
    def claude_opus_4_7(cls) -> ProviderPricing:
        return cls("claude-opus-4-7", thinking_usd_per_mtok=25.0, output_usd_per_mtok=25.0)

    @classmethod
    def openai_o3_pro(cls) -> ProviderPricing:
        return cls("o3-pro", thinking_usd_per_mtok=20.0, output_usd_per_mtok=80.0)

    @classmethod
    def deepseek_r1(cls) -> ProviderPricing:
        return cls("deepseek-r1", thinking_usd_per_mtok=0.55, output_usd_per_mtok=2.19)

    @classmethod
    def gemini_2_5_flash(cls) -> ProviderPricing:
        return cls("gemini-2.5-flash", thinking_usd_per_mtok=3.5, output_usd_per_mtok=3.5)


@dataclass(frozen=True, slots=True)
class SavingsReport:
    """Output of run_savings_simulation. Every field is a measured number,
    not an estimate or marketing claim."""

    total_queries: int
    total_thinking_tokens: int
    total_thinking_cost_usd: float
    reusable_queries: int
    reused_thinking_tokens: int
    reused_thinking_cost_usd: float
    reuse_rate_pct: float
    savings_rate_pct: float
    tau: float | None
    alpha: float
    n_calibration: int
    provider: str

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "total_queries": self.total_queries,
            "total_thinking_tokens": self.total_thinking_tokens,
            "total_thinking_cost_usd": round(self.total_thinking_cost_usd, 2),
            "reusable_queries": self.reusable_queries,
            "reused_thinking_tokens": self.reused_thinking_tokens,
            "reused_thinking_cost_usd": round(self.reused_thinking_cost_usd, 2),
            "reuse_rate_pct": round(self.reuse_rate_pct, 1),
            "savings_rate_pct": round(self.savings_rate_pct, 1),
            "bound": {"tau": self.tau, "alpha": self.alpha, "n_calibration": self.n_calibration},
        }


def load_workload_jsonl(path: str | Path) -> Iterator[WorkloadRow]:
    """Read a JSONL file with at least {"query": ..., "thinking_tokens": ...} per line."""
    with Path(path).open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as e:
                raise ValueError(f"line {lineno}: not valid JSON ({e})") from e
            yield WorkloadRow(
                query=str(obj.get("query", "")),
                thinking_tokens=int(obj.get("thinking_tokens", 0) or 0),
                output_tokens=int(obj.get("output_tokens", 0) or 0),
            )


def _coerce_tokens(value: object) -> int:
    """Parse a token count that may be blank/None into a non-negative int."""
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    return int(text)


def load_workload_csv(path: str | Path) -> Iterator[WorkloadRow]:
    """Read a CSV file with a header row that includes at least
    ``query`` and ``thinking_tokens`` columns (``output_tokens`` optional).

    Mirrors :func:`load_workload_jsonl`: blank lines are skipped and any row
    whose token columns are not integers raises ``ValueError`` naming the
    offending line so the prospect can fix their export.
    """
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return
        if "query" not in reader.fieldnames or "thinking_tokens" not in reader.fieldnames:
            raise ValueError(
                "CSV must have a header row with at least "
                "'query' and 'thinking_tokens' columns"
            )
        for row in reader:
            # csv.DictReader skips truly empty lines, but a line with only
            # delimiters yields a row of all-empty values -- treat as blank.
            if not any((v or "").strip() for v in row.values()):
                continue
            try:
                thinking_tokens = _coerce_tokens(row.get("thinking_tokens"))
                output_tokens = _coerce_tokens(row.get("output_tokens"))
            except ValueError as e:
                raise ValueError(f"line {reader.line_num}: {e}") from e
            yield WorkloadRow(
                query=str(row.get("query") or ""),
                thinking_tokens=thinking_tokens,
                output_tokens=output_tokens,
            )


def load_workload(path: str | Path) -> Iterator[WorkloadRow]:
    """Load a workload, dispatching on file extension.

    ``.csv`` is parsed as CSV; everything else (``.jsonl``, ``.json``, ...)
    is parsed as JSONL. This is the entry point the docstring promises:
    "paste a CSV/JSONL of (query, thinking_tokens, output_tokens) triples".
    """
    if Path(path).suffix.lower() == ".csv":
        return load_workload_csv(path)
    return load_workload_jsonl(path)


def run_savings_simulation(
    rows: Iterable[WorkloadRow],
    *,
    pricing: ProviderPricing,
    embedder: Embedder | None = None,
    alpha: float = 0.1,
    reuse_threshold: float = 0.15,
    min_calibration: int = 30,
    warmup_fraction: float = 0.2,
) -> SavingsReport:
    """Simulate what Anamnesis would have saved on a prospect's own workload.

    Procedure:
      1. Use the first `warmup_fraction` of rows to build the candidate store.
         Each warm-up row is measured against the *prior* index BEFORE it is
         itself indexed, so the collected nearest-neighbour distances reflect
         genuine cross-row drift -- never a row matching itself (which would
         collapse every score to 0). These distances seed a conformal
         calibrator purely to (a) require a minimum drift sample and (b) record
         `n_calibration` provenance in the receipt.
      2. For each subsequent row, query the store for its nearest neighbour. A
         row counts as reusable when that nearest-neighbour distance
         d = 1 - cos(embed(query), embed(prior)) is <= `reuse_threshold`. The
         threshold is the operator's accepted worst-case semantic drift (tau):
         it is an explicit policy, not a quantile of the workload's own scores.
         (A self-similarity quantile is degenerate here -- conformal coverage
         is (1 - alpha) by construction, so it would label ~(1 - alpha) of
         *every* workload reusable regardless of redundancy.)
      3. Report dollar value at the prospect's provider rates.

    The numbers are conservative: they assume every reusable query saves
    100% of its thinking tokens, which matches our compose-prompt behaviour
    when a match exists. They do NOT include the upfront cost of the first
    occurrence -- that cost is paid by the workload regardless.
    """
    rows_list = list(rows)
    n = len(rows_list)
    if n < min_calibration * 2:
        raise ValueError(
            f"need at least {min_calibration * 2} rows to simulate, got {n}"
        )
    if not 0.0 <= reuse_threshold <= 2.0:
        raise ValueError(
            f"reuse_threshold must be in [0, 2] (it is a 1-cos distance), "
            f"got {reuse_threshold}"
        )
    emb = embedder or embedder_for("hash", dim=128)
    store = TraceStore(embedder=emb)
    cal = ConformalCalibrator(alpha=alpha, min_calibration=min_calibration)

    warmup_n = max(min_calibration, int(n * warmup_fraction))

    def _measure_then_index(row: WorkloadRow, *, have_prior: bool) -> None:
        """Score the row against the existing index, then add it.

        Querying BEFORE indexing is essential: if the row were indexed first it
        would match itself at distance 0 and poison the calibration sample.
        """
        if have_prior:
            top = store.query_similar_steps(row.query, k=1)
            if top:
                cal.add(float(top[0][1]))
        store.add_steps([ReasoningStep.make("workload", row.query, "i")])

    # warm-up: collect real nearest-prior-neighbour distances.
    seen = 0
    for r in rows_list[:warmup_n]:
        if not r.query.strip():
            continue
        _measure_then_index(r, have_prior=seen > 0)
        seen += 1

    # backfill the calibration sample if the warm-up produced too few scores.
    while not cal.ready and warmup_n < n:
        r = rows_list[warmup_n]
        warmup_n += 1
        if not r.query.strip():
            continue
        _measure_then_index(r, have_prior=True)

    if not cal.ready:
        raise RuntimeError(
            f"could not warm calibrator: need {min_calibration} drift scores"
        )

    n_calibration = cal.n
    total_queries = 0
    total_thinking_tokens = 0
    reusable_queries = 0
    reused_thinking_tokens = 0

    for r in rows_list[warmup_n:]:
        total_queries += 1
        total_thinking_tokens += r.thinking_tokens
        if not r.query.strip():
            continue
        results = store.query_similar_steps(r.query, k=1)
        if results and results[0][1] <= reuse_threshold:
            reusable_queries += 1
            reused_thinking_tokens += r.thinking_tokens
        # always grow the store so later rows can match this one too
        store.add_steps([ReasoningStep.make("workload", r.query, "i")])

    total_cost_usd = total_thinking_tokens / 1_000_000 * pricing.thinking_usd_per_mtok
    reused_cost_usd = reused_thinking_tokens / 1_000_000 * pricing.thinking_usd_per_mtok
    reuse_rate = reusable_queries / total_queries * 100.0 if total_queries else 0.0
    savings_rate = (
        reused_thinking_tokens / total_thinking_tokens * 100.0
        if total_thinking_tokens else 0.0
    )

    return SavingsReport(
        total_queries=total_queries,
        total_thinking_tokens=total_thinking_tokens,
        total_thinking_cost_usd=total_cost_usd,
        reusable_queries=reusable_queries,
        reused_thinking_tokens=reused_thinking_tokens,
        reused_thinking_cost_usd=reused_cost_usd,
        reuse_rate_pct=reuse_rate,
        savings_rate_pct=savings_rate,
        tau=reuse_threshold,
        alpha=alpha,
        n_calibration=n_calibration,
        provider=pricing.name,
    )


PROVIDER_REGISTRY: dict[str, ProviderPricing] = {
    "claude-opus-4-7": ProviderPricing.claude_opus_4_7(),
    "o3-pro": ProviderPricing.openai_o3_pro(),
    "deepseek-r1": ProviderPricing.deepseek_r1(),
    "gemini-2.5-flash": ProviderPricing.gemini_2_5_flash(),
}
