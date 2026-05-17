"""Split-conformal prediction for reasoning-trace reuse.

References:
    Vovk, V., Gammerman, A., Shafer, G. (2005). Algorithmic Learning in a Random World.
    Angelopoulos, A. N., Bates, S. (2021). A Gentle Introduction to Conformal Prediction
        and Distribution-Free Uncertainty Quantification. arXiv:2107.07511.

The non-conformity score we use is d = 1 - cos(embed(fresh), embed(retrieved)),
where 'fresh' is what a reasoning model would produce de novo for a query,
and 'retrieved' is what our reuse layer composed from prior reasoning steps.

Given a calibration set C = {d_i}_{i=1..n} of iid scores under exchangeability,
the conformal quantile is

    tau = ceil((n + 1) * (1 - alpha)) / n -- quantile of {d_i}.

For a new score d_new from the same distribution,

    P[d_new <= tau] >= 1 - alpha

distribution-free. We expose tau via ReuseBound so receipts can record the
exact threshold and confidence used for each reuse decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Iterable

import numpy as np


@dataclass(frozen=True, slots=True)
class ReuseBound:
    """Frozen record of a split-conformal threshold used at a reuse decision.

    Attributes:
        tau: Non-conformity threshold. A new candidate with score <= tau is
            considered within the calibrated reuse band.
        alpha: Miscoverage level. P[d_new > tau] is bounded above by alpha.
        n_calibration: Number of calibration samples used to compute tau.
        score_name: Identifier of the non-conformity score function.
    """

    tau: float
    alpha: float
    n_calibration: int
    score_name: str = "one_minus_cosine"

    def coverage(self) -> float:
        """Lower bound on P[d_new <= tau] for a fresh exchangeable score."""
        return 1.0 - self.alpha


class ConformalCalibrator:
    """Online split-conformal calibrator for reasoning-trace reuse decisions.

    Maintains a sliding window of calibration scores and computes the
    distribution-free quantile threshold on demand.
    """

    def __init__(
        self,
        alpha: float = 0.1,
        max_window: int = 4096,
        min_calibration: int = 30,
    ) -> None:
        if not 0.0 < alpha < 1.0:
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")
        if max_window < min_calibration:
            raise ValueError(
                f"max_window ({max_window}) must be >= min_calibration ({min_calibration})"
            )
        self._alpha = alpha
        self._max_window = max_window
        self._min_calibration = min_calibration
        self._scores: list[float] = []

    @property
    def alpha(self) -> float:
        return self._alpha

    @property
    def n(self) -> int:
        return len(self._scores)

    @property
    def ready(self) -> bool:
        return self.n >= self._min_calibration

    def add(self, score: float) -> None:
        """Append a single non-conformity score to the calibration window."""
        if not np.isfinite(score):
            raise ValueError(f"score must be finite, got {score}")
        self._scores.append(float(score))
        if len(self._scores) > self._max_window:
            self._scores = self._scores[-self._max_window :]

    def extend(self, scores: Iterable[float]) -> None:
        for s in scores:
            self.add(s)

    def threshold(self, alpha: float | None = None) -> ReuseBound:
        """Compute the split-conformal threshold for the requested miscoverage.

        The corrected quantile uses index ceil((n+1)(1-alpha))/n to preserve
        marginal coverage under exchangeability (Angelopoulos & Bates 2021, eq 1).
        """
        if not self.ready:
            raise RuntimeError(
                f"Calibrator not ready: have {self.n} scores, need {self._min_calibration}"
            )
        a = self._alpha if alpha is None else alpha
        if not 0.0 < a < 1.0:
            raise ValueError(f"alpha must be in (0, 1), got {a}")

        n = self.n
        q_level = min(ceil((n + 1) * (1.0 - a)) / n, 1.0)
        tau = float(np.quantile(self._scores, q_level, method="higher"))
        return ReuseBound(tau=tau, alpha=a, n_calibration=n)

    def empirical_coverage(self, scores: Iterable[float], tau: float) -> float:
        arr = np.fromiter((float(s) for s in scores), dtype=float)
        if arr.size == 0:
            return float("nan")
        return float(np.mean(arr <= tau))


@dataclass(slots=True)
class MondrianCalibrator:
    """Mondrian (per-group) split-conformal calibration.

    Useful when the reuse distribution differs across reasoning models, tasks,
    or customers. Coverage is preserved per group when group membership is
    measurable and the within-group exchangeability assumption holds
    (Vovk et al. 2005, §4.5).
    """

    alpha: float = 0.1
    max_window: int = 4096
    min_calibration: int = 30
    _groups: dict[str, ConformalCalibrator] = field(default_factory=dict)

    def add(self, group: str, score: float) -> None:
        cal = self._groups.get(group)
        if cal is None:
            cal = ConformalCalibrator(
                alpha=self.alpha,
                max_window=self.max_window,
                min_calibration=self.min_calibration,
            )
            self._groups[group] = cal
        cal.add(score)

    def threshold(self, group: str, alpha: float | None = None) -> ReuseBound:
        if group not in self._groups:
            raise KeyError(f"unknown group {group!r}")
        return self._groups[group].threshold(alpha=alpha)

    def ready(self, group: str) -> bool:
        cal = self._groups.get(group)
        return cal is not None and cal.ready

    def groups(self) -> list[str]:
        return sorted(self._groups)


def one_minus_cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Default non-conformity score: 1 - cosine similarity of two embeddings."""
    a64 = np.asarray(a, dtype=np.float64)
    b64 = np.asarray(b, dtype=np.float64)
    na = np.linalg.norm(a64)
    nb = np.linalg.norm(b64)
    if na == 0.0 or nb == 0.0:
        raise ValueError("one_minus_cosine requires non-zero embeddings")
    cos = float(np.dot(a64, b64) / (na * nb))
    cos = max(-1.0, min(1.0, cos))
    return 1.0 - cos
