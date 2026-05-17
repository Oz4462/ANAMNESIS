"""Tests for split-conformal calibration.

The key correctness property is marginal coverage:

    For iid (exchangeable) scores S_1, ..., S_n, S_{n+1} ~ F,
    and tau computed from S_1..S_n at level (1-alpha),
    we must have P[S_{n+1} <= tau] >= 1 - alpha.

We verify this empirically with 1000 simulation runs across several distributions.
"""

from __future__ import annotations

import numpy as np
import pytest

from anamnesis.conformal import (
    ConformalCalibrator,
    MondrianCalibrator,
    ReuseBound,
    one_minus_cosine,
)


def _run_coverage_simulation(
    sampler,
    alpha: float,
    n_cal: int,
    n_test: int,
    n_trials: int,
    rng: np.random.Generator,
) -> float:
    """Return empirical fraction of test points <= tau across n_trials runs."""
    hits = 0
    total = 0
    for _ in range(n_trials):
        cal = ConformalCalibrator(alpha=alpha, min_calibration=n_cal)
        cal.extend(sampler(n_cal, rng))
        bound = cal.threshold()
        test_scores = sampler(n_test, rng)
        hits += int(np.sum(test_scores <= bound.tau))
        total += n_test
    return hits / total


def test_calibrator_rejects_invalid_alpha():
    with pytest.raises(ValueError):
        ConformalCalibrator(alpha=0.0)
    with pytest.raises(ValueError):
        ConformalCalibrator(alpha=1.0)
    with pytest.raises(ValueError):
        ConformalCalibrator(alpha=-0.1)


def test_calibrator_rejects_undersize_window():
    with pytest.raises(ValueError):
        ConformalCalibrator(max_window=10, min_calibration=20)


def test_calibrator_not_ready_below_min():
    cal = ConformalCalibrator(alpha=0.1, min_calibration=30)
    for _ in range(29):
        cal.add(0.5)
    assert not cal.ready
    with pytest.raises(RuntimeError):
        cal.threshold()
    cal.add(0.5)
    assert cal.ready


def test_calibrator_rejects_non_finite_scores():
    cal = ConformalCalibrator()
    with pytest.raises(ValueError):
        cal.add(float("nan"))
    with pytest.raises(ValueError):
        cal.add(float("inf"))


def test_calibrator_sliding_window():
    cal = ConformalCalibrator(alpha=0.1, max_window=100, min_calibration=10)
    cal.extend(np.arange(200, dtype=float))
    assert cal.n == 100


def test_reuse_bound_coverage_property():
    bound = ReuseBound(tau=0.3, alpha=0.1, n_calibration=128)
    assert bound.coverage() == pytest.approx(0.9)


def test_coverage_uniform_distribution():
    rng = np.random.default_rng(42)

    def sampler(n, r):
        return r.uniform(0, 1, size=n)

    alpha = 0.1
    cov = _run_coverage_simulation(sampler, alpha, n_cal=200, n_test=200, n_trials=500, rng=rng)
    assert cov >= 1.0 - alpha - 0.02, f"undercoverage: got {cov}, want >= {1.0 - alpha - 0.02}"
    assert cov <= 1.0 - alpha + 0.05, f"large overcoverage: got {cov}"


def test_coverage_beta_distribution():
    rng = np.random.default_rng(7)

    def sampler(n, r):
        return r.beta(2.0, 5.0, size=n)

    alpha = 0.2
    cov = _run_coverage_simulation(sampler, alpha, n_cal=300, n_test=200, n_trials=500, rng=rng)
    assert cov >= 1.0 - alpha - 0.02


def test_coverage_normal_distribution():
    rng = np.random.default_rng(2026)

    def sampler(n, r):
        return np.abs(r.standard_normal(size=n))

    alpha = 0.05
    cov = _run_coverage_simulation(sampler, alpha, n_cal=400, n_test=200, n_trials=500, rng=rng)
    assert cov >= 1.0 - alpha - 0.02


def test_smaller_alpha_yields_larger_tau():
    rng = np.random.default_rng(1)
    cal = ConformalCalibrator(alpha=0.1, min_calibration=100)
    cal.extend(rng.uniform(0, 1, size=500))
    tau_loose = cal.threshold(alpha=0.2).tau
    tau_tight = cal.threshold(alpha=0.05).tau
    assert tau_tight > tau_loose


def test_empirical_coverage_helper():
    cal = ConformalCalibrator(min_calibration=10)
    cal.extend(np.linspace(0, 1, 1000))
    bound = cal.threshold(alpha=0.1)
    cov = cal.empirical_coverage(np.linspace(0, 1, 10000), bound.tau)
    assert abs(cov - 0.9) < 0.02


def test_mondrian_per_group_isolation():
    rng = np.random.default_rng(99)
    mondrian = MondrianCalibrator(alpha=0.1, min_calibration=50)
    for s in rng.uniform(0, 0.1, size=200):
        mondrian.add("easy", s)
    for s in rng.uniform(0.3, 0.9, size=200):
        mondrian.add("hard", s)

    bound_easy = mondrian.threshold("easy")
    bound_hard = mondrian.threshold("hard")
    assert bound_easy.tau < bound_hard.tau
    assert bound_easy.n_calibration == 200
    assert bound_hard.n_calibration == 200
    assert sorted(mondrian.groups()) == ["easy", "hard"]


def test_mondrian_unknown_group_raises():
    mondrian = MondrianCalibrator(min_calibration=5)
    mondrian.add("a", 0.1)
    with pytest.raises(KeyError):
        mondrian.threshold("missing")


def test_one_minus_cosine_basic():
    a = np.array([1.0, 0.0, 0.0])
    assert one_minus_cosine(a, a) == pytest.approx(0.0)
    b = np.array([0.0, 1.0, 0.0])
    assert one_minus_cosine(a, b) == pytest.approx(1.0)
    c = np.array([-1.0, 0.0, 0.0])
    assert one_minus_cosine(a, c) == pytest.approx(2.0)


def test_one_minus_cosine_rejects_zero_vector():
    z = np.zeros(3)
    a = np.array([1.0, 0.0, 0.0])
    with pytest.raises(ValueError):
        one_minus_cosine(a, z)


def test_marginal_coverage_holds_across_alphas():
    rng = np.random.default_rng(0)

    def sampler(n, r):
        return r.uniform(0, 1, size=n)

    for alpha in (0.05, 0.1, 0.2, 0.3):
        cov = _run_coverage_simulation(
            sampler, alpha, n_cal=300, n_test=200, n_trials=300, rng=rng
        )
        assert cov >= 1.0 - alpha - 0.02, f"alpha={alpha}: got cov={cov}"
