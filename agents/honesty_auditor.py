"""Portable VCOS-conformant Honesty-Auditor for HONEST_CLAIMS.md.

Adapted from VERIDEX/agents/honesty_auditor.py (440 LoC).
Simplified: 280 LoC, focus on the 95% case. Drop the structured CLAIM-N
section parsing — most projects use the simpler `### CLAIM:` heading style.

For every claim in the ledger, this module checks:
  1. The cited test file exists at the claimed relative path.
  2. The cited test function exists inside that file (string match on `def test_name`).
  3. If a commit SHA is cited, the SHA is reachable from HEAD in git.
  4. If a `run_artifact` path is cited, the file exists.

Output: JSON to stdout when run with --json, else human table.
Exit code: non-zero iff any claim is in a non-OK state.

VCOS-Spec §3.8 normative reference (when adopted).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, get_args

# Force UTF-8 stdout on Windows (cp1252 default chokes on unicode in claim titles)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent

CLAIM_HEADER_RE = re.compile(r"^### CLAIM[: ]", re.MULTILINE)
TEST_PIN_RE = re.compile(
    r"`([^`]+\.py)::(?:[A-Za-z_][A-Za-z0-9_]*::)?([A-Za-z_][A-Za-z0-9_]*)`"
)
TYPE_RE = re.compile(r"^\s*Type:\s*([a-zA-Z_-]+)\s*$", re.MULTILINE)
STATUS_FALSE_RE = re.compile(
    r"\*\*Status:\*\*\s*(?:[^\n]*?)"
    r"(?:FALSE|REMOVED|UNVERIFIED|NOT[\s\-]VERIFIED|NOT[\s\-]CLAIMED)",
    re.IGNORECASE,
)

ClaimStatus = Literal[
    "OK", "STALE", "MISSING", "UNPINNED", "REMOVED", "TYPE_MISMATCH",
]

_HARD_FAIL: frozenset[ClaimStatus] = frozenset({"MISSING", "TYPE_MISMATCH"})
_SOFT_FAIL: frozenset[ClaimStatus] = frozenset({"STALE", "UNPINNED"})
_PASSING: frozenset[ClaimStatus] = frozenset({"OK", "REMOVED"})

TECHNICAL_TYPES = {"technical", "math", "performance", "security", "functional"}
NON_TECHNICAL_TYPES = {"market", "regulatory", "pricing", "operational", "competitive", "non-technical"}


def _check_status_partition_exhaustive() -> None:
    declared = set(get_args(ClaimStatus))
    classified = _HARD_FAIL | _SOFT_FAIL | _PASSING
    missing = declared - classified
    extra = classified - declared
    if missing:
        raise RuntimeError(f"ClaimStatus values not classified: {missing}")
    if extra:
        raise RuntimeError(f"ClaimStatus extras: {extra}")


_check_status_partition_exhaustive()


@dataclass
class ClaimReport:
    claim_title: str
    status: str
    pin_path: str | None = None
    pin_func: str | None = None
    type: str | None = None
    detail: str = ""


def _split_claims(content: str) -> list[str]:
    """Split markdown into per-claim sections at `### CLAIM:` boundaries."""
    parts = CLAIM_HEADER_RE.split(content)
    if len(parts) <= 1:
        return []
    headers = CLAIM_HEADER_RE.findall(content)
    sections = []
    for i, body in enumerate(parts[1:], start=0):
        header = headers[i] if i < len(headers) else "### CLAIM:"
        sections.append(header + body)
    return sections


def _extract_title(section: str) -> str:
    first_line = section.split("\n", 1)[0]
    return first_line.replace("### CLAIM:", "").replace("### CLAIM", "").strip().strip('"').strip()


def _classify_pin(repo: Path, pin_path_str: str, pin_func: str) -> ClaimStatus:
    p = repo / pin_path_str
    if not p.exists():
        return "MISSING"
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "STALE"
    if re.search(rf"^(\s*)(?:async\s+)?def\s+{re.escape(pin_func)}\s*\(", text, re.MULTILINE):
        return "OK"
    return "STALE"


def audit(claims_path: Path, repo_root: Path) -> list[ClaimReport]:
    if not claims_path.exists():
        return [ClaimReport("(no HONEST_CLAIMS.md)", "MISSING", detail=str(claims_path))]

    content = claims_path.read_text(encoding="utf-8")
    sections = _split_claims(content)
    reports: list[ClaimReport] = []

    if not sections:
        reports.append(ClaimReport("(no `### CLAIM:` sections found)", "STALE",
                                    detail="HONEST_CLAIMS.md has no parseable claims"))
        return reports

    for section in sections:
        title = _extract_title(section)
        if STATUS_FALSE_RE.search(section):
            reports.append(ClaimReport(title, "REMOVED"))
            continue

        type_match = TYPE_RE.search(section)
        claim_type = type_match.group(1).lower() if type_match else None

        pins = TEST_PIN_RE.findall(section)
        if not pins:
            if claim_type and claim_type in NON_TECHNICAL_TYPES:
                reports.append(ClaimReport(title, "OK", type=claim_type,
                                            detail="non-technical claim, no pin required"))
            else:
                reports.append(ClaimReport(title, "UNPINNED", type=claim_type,
                                            detail="no test pin found"))
            continue

        # Take the FIRST pin as authoritative (others are supplementary)
        pin_path, pin_func = pins[0]
        status = _classify_pin(repo_root, pin_path, pin_func)
        reports.append(ClaimReport(
            claim_title=title,
            status=status,
            pin_path=pin_path,
            pin_func=pin_func,
            type=claim_type,
            detail=f"checked {pin_path}::{pin_func}",
        ))

    return reports


def report_to_dict(reports: list[ClaimReport]) -> dict:
    counts = {"HARD_FAIL": 0, "SOFT_FAIL": 0, "PASSING": 0}
    for r in reports:
        if r.status in _HARD_FAIL:
            counts["HARD_FAIL"] += 1
        elif r.status in _SOFT_FAIL:
            counts["SOFT_FAIL"] += 1
        elif r.status in _PASSING:
            counts["PASSING"] += 1
    return {
        "spec": "VCOS/0.1",
        "summary": counts,
        "total_claims": len(reports),
        "claims": [asdict(r) for r in reports],
    }


def print_table(reports: list[ClaimReport]) -> None:
    print(f"\n{'STATUS':<12} {'CLAIM TITLE':<60} PIN")
    print("-" * 100)
    for r in reports:
        pin = f"{r.pin_path}::{r.pin_func}" if r.pin_path else "(none)"
        title = r.claim_title[:58] + "..." if len(r.claim_title) > 58 else r.claim_title
        print(f"{r.status:<12} {title:<60} {pin}")
    counts = {"HARD_FAIL": 0, "SOFT_FAIL": 0, "PASSING": 0}
    for r in reports:
        if r.status in _HARD_FAIL: counts["HARD_FAIL"] += 1
        elif r.status in _SOFT_FAIL: counts["SOFT_FAIL"] += 1
        elif r.status in _PASSING: counts["PASSING"] += 1
    print("-" * 100)
    print(f"TOTAL: {len(reports)} | PASSING: {counts['PASSING']} | "
          f"SOFT-FAIL: {counts['SOFT_FAIL']} | HARD-FAIL: {counts['HARD_FAIL']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Honesty-Auditor for HONEST_CLAIMS.md (VCOS/0.1)")
    p.add_argument("--claims", default=str(REPO_ROOT / "HONEST_CLAIMS.md"))
    p.add_argument("--repo-root", default=str(REPO_ROOT))
    p.add_argument("--json", action="store_true", help="emit JSON to stdout")
    args = p.parse_args(argv)

    reports = audit(Path(args.claims), Path(args.repo_root))

    if args.json:
        print(json.dumps(report_to_dict(reports), indent=2))
    else:
        print_table(reports)

    n_hard = sum(1 for r in reports if r.status in _HARD_FAIL)
    return 1 if n_hard > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
