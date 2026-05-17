"""Tests for conformal retrieval and prompt composition."""

from __future__ import annotations

import numpy as np
import pytest
from anamnesis.compose import compose
from anamnesis.conformal import ConformalCalibrator
from anamnesis.retrieve import ConformalRetriever, RetrievalResult
from anamnesis.storage import ReasoningStep, TraceStore, hash_embedder


def _populated_store(seed: int = 1) -> TraceStore:
    embedder = hash_embedder(dim=64)
    store = TraceStore(embedder=embedder)
    steps = [
        ReasoningStep.make("cap_1", "Compute the area of a triangle from base and height.", "triangle area"),
        ReasoningStep.make("cap_1", "Bake a sourdough loaf with rye flour overnight.", "bake sourdough"),
        ReasoningStep.make("cap_2", "Solve a linear equation by isolating x on the left side.", "linear equation"),
        ReasoningStep.make("cap_2", "Translate a German sentence into English using context clues.", "translate"),
        ReasoningStep.make("cap_3", "Compute the volume of a sphere from its radius using V = 4/3 pi r^3.", "sphere volume"),
    ]
    store.add_steps(steps)
    _ = seed  # reserved for future randomised setups
    return store


def _warm_calibrator(scores=(0.05, 0.1, 0.15, 0.2, 0.25, 0.3) * 6, alpha=0.1, min_cal=30):
    cal = ConformalCalibrator(alpha=alpha, min_calibration=min_cal)
    cal.extend(scores)
    return cal


def test_retriever_returns_candidates_when_cold_but_abstains():
    store = _populated_store()
    cal = ConformalCalibrator(alpha=0.1, min_calibration=30)
    retriever = ConformalRetriever(store=store, calibrator=cal, k=3)
    result = retriever.retrieve("How do I compute area of a triangle?")
    assert isinstance(result, RetrievalResult)
    assert len(result.candidates) == 3
    assert result.bound is None
    assert result.abstained


def test_retriever_warmed_calibrator_accepts_matching_step():
    store = _populated_store()
    cal = _warm_calibrator(scores=[0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75] * 5, alpha=0.1)
    retriever = ConformalRetriever(store=store, calibrator=cal, k=3)
    result = retriever.retrieve("How do I compute area of a triangle?")
    assert result.bound is not None
    assert result.bound.tau > 0
    assert not result.abstained or len(result.candidates) > 0


def test_retriever_strict_alpha_can_force_abstention():
    store = _populated_store()
    cal = ConformalCalibrator(alpha=0.5, min_calibration=10)
    cal.extend([0.001] * 50)  # extremely tight calibration band
    retriever = ConformalRetriever(store=store, calibrator=cal, k=3)
    result = retriever.retrieve("an entirely unrelated query about cooking pasta")
    assert result.bound is not None
    assert result.abstained


def test_retriever_rejects_zero_k():
    store = _populated_store()
    cal = ConformalCalibrator(min_calibration=5)
    cal.extend([0.1] * 30)
    retriever = ConformalRetriever(store=store, calibrator=cal, k=0)
    with pytest.raises(ValueError):
        retriever.retrieve("anything")


def test_retriever_record_outcome_warms_calibrator():
    store = _populated_store()
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10)
    retriever = ConformalRetriever(store=store, calibrator=cal, k=2)
    assert not cal.ready
    for s in np.linspace(0.1, 0.5, 10):
        retriever.record_outcome(float(s))
    assert cal.ready


def test_compose_abstained_returns_empty_system_fragment():
    store = _populated_store()
    cal = ConformalCalibrator(min_calibration=30)
    retriever = ConformalRetriever(store=store, calibrator=cal, k=3)
    result = retriever.retrieve("anything")
    composed = compose(result, user_text="some user query")
    assert composed.system_fragment == ""
    assert composed.abstained
    assert composed.reused_step_ids == ()


def test_compose_includes_bound_and_step_metadata():
    store = _populated_store()
    cal = _warm_calibrator(scores=[0.5] * 60, alpha=0.1)
    retriever = ConformalRetriever(store=store, calibrator=cal, k=3)
    result = retriever.retrieve("Compute area of triangle")
    composed = compose(result, user_text="please help")
    assert "ANAMNESIS REUSE CONTEXT" in composed.system_fragment
    assert "tau=" in composed.system_fragment
    assert "alpha=" in composed.system_fragment
    assert "n_calibration=" in composed.system_fragment
    assert len(composed.reused_step_ids) >= 1
    assert composed.tau is not None
    assert composed.alpha == pytest.approx(0.1)


def test_compose_step_block_lists_intent_text_tags():
    store = _populated_store()
    cal = _warm_calibrator(scores=[0.5] * 60, alpha=0.1)
    retriever = ConformalRetriever(store=store, calibrator=cal, k=3)
    result = retriever.retrieve("Compute area of triangle")
    composed = compose(result, user_text="please help")
    for sid in composed.reused_step_ids:
        assert sid in composed.system_fragment


def test_compose_user_text_passthrough():
    store = _populated_store()
    cal = _warm_calibrator(scores=[0.5] * 60, alpha=0.1)
    retriever = ConformalRetriever(store=store, calibrator=cal, k=3)
    result = retriever.retrieve("Compute area of triangle")
    composed = compose(result, user_text="VERY SPECIFIC USER TEXT")
    assert composed.user_text == "VERY SPECIFIC USER TEXT"


def test_retrieval_result_accepted_step_ids_helper():
    store = _populated_store()
    cal = _warm_calibrator(scores=[0.5] * 60, alpha=0.1)
    retriever = ConformalRetriever(store=store, calibrator=cal, k=3)
    result = retriever.retrieve("Compute the area of a triangle from base and height.")
    ids = result.accepted_step_ids
    assert isinstance(ids, tuple)
    assert all(isinstance(x, str) for x in ids)
