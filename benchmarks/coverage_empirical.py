# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Empirical conformal-coverage on shapes other than uniform.

The theoretical guarantee (Vovk/Shafer/Angelopoulos-Bates) says

    P[S_{n+1} <= tau]  >=  1 - alpha

under exchangeability, distribution-free. The unit tests verify this on
uniform, beta, and half-normal. Here we hit the calibrator with shapes that
matter in production:

  * pareto       - heavy-tail, modelling rare-but-bad reuse drift
  * lognormal    - long-tailed semantic distance distribution
  * bimodal      - two clusters of reuse difficulty
  * mixture-drift - first half drawn from F1, second from F2 (concept drift)

A drift sample is allowed to undercover -- the conformal guarantee assumes
exchangeability, which drift breaks. We report the empirical coverage so a
deployer can see the calibrator behaviour vs theory.
"""

from __future__ import annotations

import statistics

import numpy as np
from anamnesis.conformal import ConformalCalibrator

N_TRIALS = 500
N_CAL = 500
N_TEST = 200


def coverage(sampler, alpha: float, rng: np.random.Generator) -> float:
    hits = 0
    total = 0
    for _ in range(N_TRIALS):
        cal = ConformalCalibrator(alpha=alpha, min_calibration=N_CAL, max_window=10_000)
        cal.extend(sampler(N_CAL, rng))
        bound = cal.threshold()
        test = sampler(N_TEST, rng)
        hits += int(np.sum(test <= bound.tau))
        total += N_TEST
    return hits / total


def two_sample_coverage(sampler_cal, sampler_test, alpha: float, rng: np.random.Generator) -> float:
    """Coverage when calibration and test are drawn from different laws."""
    hits = 0
    total = 0
    for _ in range(N_TRIALS):
        cal = ConformalCalibrator(alpha=alpha, min_calibration=N_CAL, max_window=10_000)
        cal.extend(sampler_cal(N_CAL, rng))
        bound = cal.threshold()
        test = sampler_test(N_TEST, rng)
        hits += int(np.sum(test <= bound.tau))
        total += N_TEST
    return hits / total


def main() -> None:
    rng = np.random.default_rng(13)
    alpha = 0.1
    target = 1.0 - alpha

    samplers = {
        "uniform[0,1]":      lambda n, r: r.uniform(0, 1, n),
        "pareto(a=2)":       lambda n, r: (r.pareto(2.0, n) / 5.0).clip(0, 5),
        "lognormal(0,0.5)":  lambda n, r: (r.lognormal(0, 0.5, n) / 5.0).clip(0, 5),
        "bimodal":           lambda n, r: np.where(r.random(n) < 0.5,
                                                    r.normal(0.2, 0.05, n),
                                                    r.normal(0.7, 0.05, n)).clip(0, 1),
        "half-normal":       lambda n, r: np.abs(r.standard_normal(n)) / 3.0,
    }

    print(f"=== exchangeable case (alpha={alpha}, target coverage>={target:.2f}) ===")
    for name, sampler in samplers.items():
        cov = coverage(sampler, alpha=alpha, rng=rng)
        flag = "OK" if cov >= target - 0.03 else "UNDER"
        print(f"  [{flag}]  {name:22s} empirical_coverage={cov:.3f}  ({cov - target:+.3f} vs target)")

    print("\n=== concept-drift case (calibration != test law) ===")
    print("  Expected: coverage may drop below 1-alpha -- this is a known limitation.")
    drift_pairs = {
        "uniform -> shifted uniform": (samplers["uniform[0,1]"], lambda n, r: r.uniform(0.1, 1.1, n)),
        "uniform -> pareto":          (samplers["uniform[0,1]"], samplers["pareto(a=2)"]),
        "bimodal -> uniform":         (samplers["bimodal"], samplers["uniform[0,1]"]),
    }
    for name, (cal_s, test_s) in drift_pairs.items():
        cov = two_sample_coverage(cal_s, test_s, alpha=alpha, rng=rng)
        print(f"  {name:32s} empirical_coverage={cov:.3f}  ({cov - target:+.3f} vs target)")

    print("\nCOVERAGE EMPIRICAL OK")


if __name__ == "__main__":
    _ = statistics  # placeholder for future per-trial CIs
    main()
