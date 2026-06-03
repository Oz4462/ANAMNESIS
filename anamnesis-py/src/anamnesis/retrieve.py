# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Conformal-bounded retrieval of reasoning steps.

Given a new query, we ask the TraceStore for its k-nearest reasoning steps
(measured by d = 1 - cosine on a normalized embedding space) and then filter
the result against a conformal threshold tau supplied by a calibrator.

If at least one candidate's score is <= tau, that candidate is considered
within the calibrated reuse band and is safe to splice into the new prompt
under the bound's (alpha) miscoverage guarantee. Otherwise we abstain: the
query gets handled by the underlying reasoning model the normal way, and the
fresh trace becomes a new calibration point.

This module returns plain data; it never calls an LLM. The compose layer
takes its output and assembles a prompt; the receipt layer records the bound
and the retrieved step ids for audit.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from anamnesis.conformal import ConformalCalibrator, ReuseBound
from anamnesis.storage import ReasoningStep, TraceStore


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    step: ReasoningStep
    score: float

    @property
    def step_id(self) -> str:
        return self.step.step_id


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Outcome of a single conformal retrieval call.

    Attributes:
        query: The user prompt or sub-question the lookup was made for.
        bound: The conformal threshold that was applied. None when the
            calibrator was not yet warm enough.
        candidates: The k nearest steps, ordered by ascending score.
        accepted: Subset of candidates whose score is <= bound.tau.
        abstained: True when no candidate was accepted (or no bound existed).
    """

    query: str
    bound: ReuseBound | None
    candidates: tuple[RetrievalCandidate, ...]
    accepted: tuple[RetrievalCandidate, ...]

    @property
    def abstained(self) -> bool:
        return len(self.accepted) == 0

    @property
    def accepted_step_ids(self) -> tuple[str, ...]:
        return tuple(c.step_id for c in self.accepted)


@dataclass(slots=True)
class ConformalRetriever:
    """Pull k-nearest steps from a TraceStore and filter by a conformal bound."""

    store: TraceStore
    calibrator: ConformalCalibrator
    k: int = 5
    fallback_alpha: float = 0.1

    def retrieve(self, query: str, *, alpha: float | None = None) -> RetrievalResult:
        if self.k <= 0:
            raise ValueError(f"k must be positive, got {self.k}")

        raw = self.store.query_similar_steps(query, k=self.k)
        candidates = tuple(RetrievalCandidate(step=s, score=score) for s, score in raw)

        bound: ReuseBound | None = None
        accepted: tuple[RetrievalCandidate, ...] = ()
        if self.calibrator.ready:
            bound = self.calibrator.threshold(alpha=alpha)
            accepted = tuple(c for c in candidates if c.score <= bound.tau)

        return RetrievalResult(
            query=query,
            bound=bound,
            candidates=candidates,
            accepted=accepted,
        )

    def record_outcome(self, score: float) -> None:
        """Add an observed non-conformity score to the calibration window.

        Call this whenever a fresh-vs-retrieved comparison is performed so
        the threshold tracks current model behaviour.
        """
        self.calibrator.add(score)

    def record_batch(self, scores: Sequence[float]) -> None:
        self.calibrator.extend(scores)
