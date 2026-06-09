# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Tests for the honesty-auditor claim classification."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import honesty_auditor as ha  # noqa: E402


def _claims(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "HONEST_CLAIMS.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_unknown_type_is_type_mismatch(tmp_path):
    """A declared Type outside the taxonomy (typo) must hard-fail, not slip
    through as UNPINNED. Regression: TYPE_MISMATCH used to be unreachable."""
    md = "### CLAIM: typo'd type\nType: secrity\nSome prose, no pin.\n"
    reports = ha.audit(_claims(tmp_path, md), tmp_path)
    assert len(reports) == 1
    assert reports[0].status == "TYPE_MISMATCH"
    assert reports[0].status in ha._HARD_FAIL  # tooling exits non-zero


def test_known_nontechnical_type_without_pin_is_ok(tmp_path):
    md = "### CLAIM: market sizing\nType: market\nNo pin needed.\n"
    reports = ha.audit(_claims(tmp_path, md), tmp_path)
    assert reports[0].status == "OK"


def test_known_technical_type_without_pin_is_unpinned(tmp_path):
    md = "### CLAIM: perf claim\nType: performance\nNo pin provided.\n"
    reports = ha.audit(_claims(tmp_path, md), tmp_path)
    assert reports[0].status == "UNPINNED"


def test_known_technical_type_with_valid_pin_is_ok(tmp_path):
    test_file = tmp_path / "test_thing.py"
    test_file.write_text("def test_alpha():\n    assert True\n", encoding="utf-8")
    md = (
        "### CLAIM: pinned perf claim\n"
        "Type: performance\n"
        "Evidence: `test_thing.py::test_alpha`\n"
    )
    reports = ha.audit(_claims(tmp_path, md), tmp_path)
    assert reports[0].status == "OK"
    assert reports[0].pin_func == "test_alpha"
