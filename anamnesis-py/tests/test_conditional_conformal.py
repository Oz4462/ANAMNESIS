# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Tests for conditional (per-bucket) conformal calibration."""

from __future__ import annotations

import numpy as np
import pytest
from anamnesis.conformal import ConditionalConformalCalibrator


def _bucket_by_keyword(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("math", "triangle", "equation", "integral")):
        return "math"
    if any(w in t for w in ("law", "contract", "clause", "court")):
        return "legal"
    return "other"


def test_conditional_calibrator_separates_buckets():
    cal = ConditionalConformalCalibrator(alpha=0.1, min_calibration=30)
    cal.set_bucket_fn(_bucket_by_keyword)

    rng = np.random.default_rng(0)
    for s in rng.uniform(0.0, 0.2, size=80):
        cal.add("math triangle area", float(s))
    for s in rng.uniform(0.5, 0.95, size=80):
        cal.add("contract clause review", float(s))

    assert sorted(cal.buckets()) == ["legal", "math"]
    tau_math = cal.threshold("math integral").tau
    tau_legal = cal.threshold("contract clause").tau
    assert tau_math < tau_legal


def test_conditional_calibrator_default_bucket_without_fn():
    cal = ConditionalConformalCalibrator(alpha=0.1, min_calibration=20)
    for s in np.linspace(0.1, 0.5, 30):
        cal.add("anything goes here", float(s))
    bound = cal.threshold("anything goes here")
    assert bound.alpha == pytest.approx(0.1)
    assert cal.buckets() == ["default"]


def test_conditional_calibrator_not_ready_raises():
    cal = ConditionalConformalCalibrator(alpha=0.1, min_calibration=30)
    cal.set_bucket_fn(_bucket_by_keyword)
    cal.add("math", 0.1)
    assert not cal.ready("math")
    with pytest.raises(RuntimeError):
        cal.threshold("math")


def test_conditional_calibrator_unknown_bucket_raises():
    cal = ConditionalConformalCalibrator(alpha=0.1, min_calibration=5)
    cal.set_bucket_fn(_bucket_by_keyword)
    cal.add("math area", 0.1)
    with pytest.raises(RuntimeError):
        cal.threshold("unrelated query")


def test_conditional_calibrator_rejects_invalid_alpha():
    with pytest.raises(ValueError):
        ConditionalConformalCalibrator(alpha=0.0)
    with pytest.raises(ValueError):
        ConditionalConformalCalibrator(alpha=1.5)


def test_conditional_calibrator_per_bucket_coverage_holds():
    rng = np.random.default_rng(7)
    cal = ConditionalConformalCalibrator(alpha=0.1, min_calibration=50)
    cal.set_bucket_fn(_bucket_by_keyword)

    math_scores = rng.uniform(0, 0.3, size=300)
    legal_scores = rng.uniform(0.4, 0.9, size=300)

    for s in math_scores[:200]:
        cal.add("math", float(s))
    for s in legal_scores[:200]:
        cal.add("law", float(s))

    tau_math = cal.threshold("math").tau
    tau_legal = cal.threshold("law").tau

    math_hits = float(np.mean(math_scores[200:] <= tau_math))
    legal_hits = float(np.mean(legal_scores[200:] <= tau_legal))
    assert math_hits >= 0.85, f"math conditional undercoverage: {math_hits}"
    assert legal_hits >= 0.85, f"legal conditional undercoverage: {legal_hits}"
