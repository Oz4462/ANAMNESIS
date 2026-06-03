# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Conformal + cosine math edge cases.

These tests cover the values most likely to break in production:
  - exactly at min_calibration boundary
  - alpha at the upper edge (close to 1.0)
  - all-identical calibration scores
  - very tiny windows
  - orthogonal, identical, and antipodal embeddings
"""

from __future__ import annotations

import numpy as np
import pytest
from anamnesis.conformal import (
    ConditionalConformalCalibrator,
    ConformalCalibrator,
    MondrianCalibrator,
    one_minus_cosine,
)


def test_threshold_at_exact_min_calibration():
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10)
    for s in np.linspace(0, 1, 10):
        cal.add(float(s))
    assert cal.ready
    bound = cal.threshold()
    assert bound.n_calibration == 10
    assert 0.0 <= bound.tau <= 1.0


def test_threshold_one_below_min_calibration_raises():
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10)
    for s in np.linspace(0, 1, 9):
        cal.add(float(s))
    assert not cal.ready
    with pytest.raises(RuntimeError):
        cal.threshold()


def test_threshold_with_all_identical_scores():
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10)
    cal.extend([0.42] * 100)
    bound = cal.threshold()
    assert bound.tau == 0.42


def test_threshold_alpha_near_one_yields_smallest_score():
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10)
    cal.extend(np.linspace(0, 1, 100))
    bound_loose = cal.threshold(alpha=0.99)
    bound_strict = cal.threshold(alpha=0.01)
    assert bound_strict.tau > bound_loose.tau
    assert bound_loose.tau >= 0.0


def test_threshold_alpha_near_zero_caps_at_quantile_one():
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10)
    cal.extend(np.linspace(0, 1, 100))
    bound = cal.threshold(alpha=1e-6)
    # q_level = min(ceil((n+1)*(1-eps))/n, 1.0) clamps at 1.0
    # so tau is the 100th-percentile score = 1.0 here.
    assert bound.tau == pytest.approx(1.0)


def test_window_max_equals_min_is_allowed():
    cal = ConformalCalibrator(alpha=0.1, max_window=5, min_calibration=5)
    cal.extend([0.1, 0.2, 0.3, 0.4, 0.5])
    assert cal.ready
    cal.add(0.99)
    assert cal.n == 5  # oldest dropped
    bound = cal.threshold()
    assert 0.2 <= bound.tau <= 0.99


def test_orthogonal_embeddings_yield_score_one():
    a = np.array([1.0, 0.0, 0.0])
    b = np.array([0.0, 1.0, 0.0])
    assert one_minus_cosine(a, b) == pytest.approx(1.0)


def test_identical_embeddings_yield_score_zero():
    a = np.array([0.3, 0.5, 0.2])
    assert one_minus_cosine(a, a) == pytest.approx(0.0)


def test_antipodal_embeddings_yield_score_two():
    a = np.array([1.0, 0.0, 0.0])
    b = -a
    assert one_minus_cosine(a, b) == pytest.approx(2.0)


def test_one_minus_cosine_handles_floating_point_precision_at_boundary():
    """Tiny numerical drift can push cos > 1.0 — must clamp, not produce negative score."""
    a = np.array([1.0 + 1e-15, 0.0, 0.0])
    score = one_minus_cosine(a, a)
    assert score >= 0.0
    assert score < 1e-9


def test_mondrian_calibrator_independent_window_per_group():
    m = MondrianCalibrator(alpha=0.1, max_window=10, min_calibration=5)
    for _ in range(20):
        m.add("g1", 0.1)
    for _ in range(20):
        m.add("g2", 0.9)
    # Each group has its own 10-element window
    assert m.threshold("g1").tau == pytest.approx(0.1)
    assert m.threshold("g2").tau == pytest.approx(0.9)
    assert len(m.groups()) == 2


def test_conditional_calibrator_handles_lambda_bucketer():
    cal = ConditionalConformalCalibrator(alpha=0.1, min_calibration=10)
    cal.set_bucket_fn(lambda q: "short" if len(q) < 10 else "long")
    for _ in range(15):
        cal.add("hi", 0.1)
    for _ in range(15):
        cal.add("this is a longer query", 0.5)
    short = cal.threshold("hi")
    long_b = cal.threshold("this is a longer query")
    assert short.tau == pytest.approx(0.1)
    assert long_b.tau == pytest.approx(0.5)


def test_conformal_threshold_uses_higher_quantile_for_coverage():
    """The conformal correction uses ceil((n+1)*(1-alpha))/n quantile.
    For n=10, alpha=0.1: ceil(11*0.9)/10 = 10/10 = 1.0 => take max."""
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10)
    cal.extend([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    bound = cal.threshold()
    assert bound.tau == 1.0
