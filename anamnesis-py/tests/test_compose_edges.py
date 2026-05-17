"""Edge cases for retrieve + compose: k bounds, empty store, abstain logic, big queries."""

from __future__ import annotations

import pytest
from anamnesis.compose import compose
from anamnesis.conformal import ConformalCalibrator
from anamnesis.retrieve import ConformalRetriever
from anamnesis.storage import ReasoningStep, TraceStore, hash_embedder


def _populated_store(n: int = 5) -> TraceStore:
    store = TraceStore(embedder=hash_embedder(dim=64))
    store.add_steps([
        ReasoningStep.make("cap", f"step number {i} with unique words alpha beta gamma {i}", f"i_{i}")
        for i in range(n)
    ])
    return store


def _ready_calibrator() -> ConformalCalibrator:
    cal = ConformalCalibrator(alpha=0.1, min_calibration=30)
    cal.extend([0.5] * 60)
    return cal


def test_retrieve_with_k_one():
    retriever = ConformalRetriever(store=_populated_store(), calibrator=_ready_calibrator(), k=1)
    result = retriever.retrieve("alpha beta gamma 2")
    assert len(result.candidates) == 1


def test_retrieve_with_k_larger_than_store():
    retriever = ConformalRetriever(store=_populated_store(n=3), calibrator=_ready_calibrator(), k=10)
    result = retriever.retrieve("alpha beta gamma 0")
    assert len(result.candidates) == 3  # bounded by what's in store


def test_retrieve_empty_store_returns_empty():
    empty = TraceStore(embedder=hash_embedder(dim=32))
    retriever = ConformalRetriever(store=empty, calibrator=_ready_calibrator(), k=5)
    result = retriever.retrieve("anything")
    assert result.candidates == ()
    assert result.abstained


def test_compose_with_unicode_query():
    retriever = ConformalRetriever(store=_populated_store(), calibrator=_ready_calibrator(), k=3)
    result = retriever.retrieve("Was ist die Flaeche eines Dreiecks?")
    composed = compose(result, user_text="Frage mit Umlauten: ä ö ü ß 🚀")
    assert composed.user_text == "Frage mit Umlauten: ä ö ü ß 🚀"


def test_compose_with_very_long_user_text():
    retriever = ConformalRetriever(store=_populated_store(), calibrator=_ready_calibrator(), k=3)
    result = retriever.retrieve("alpha beta gamma 1")
    huge = "x " * 5000
    composed = compose(result, user_text=huge)
    assert composed.user_text == huge


def test_compose_abstain_when_calibrator_not_ready():
    cal_cold = ConformalCalibrator(alpha=0.1, min_calibration=30)
    retriever = ConformalRetriever(store=_populated_store(), calibrator=cal_cold, k=3)
    result = retriever.retrieve("alpha")
    assert result.bound is None
    composed = compose(result, user_text="query")
    assert composed.abstained
    assert composed.system_fragment == ""


def test_retriever_explicit_alpha_overrides_calibrator_default():
    retriever = ConformalRetriever(store=_populated_store(), calibrator=_ready_calibrator(), k=3)
    result_loose = retriever.retrieve("alpha beta gamma 0", alpha=0.5)
    result_strict = retriever.retrieve("alpha beta gamma 0", alpha=0.05)
    assert result_loose.bound is not None and result_strict.bound is not None
    assert result_loose.bound.alpha == 0.5
    assert result_strict.bound.alpha == 0.05


def test_retriever_record_outcome_accumulates_for_threshold():
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10)
    retriever = ConformalRetriever(store=_populated_store(), calibrator=cal, k=2)
    for s in [0.1, 0.2, 0.3, 0.4, 0.5] * 3:
        retriever.record_outcome(s)
    assert cal.ready
    result = retriever.retrieve("alpha beta gamma 1")
    assert result.bound is not None


def test_compose_empty_acceptance_still_records_bound():
    """Bound exists but no candidate passed tau => abstained but bound is in result."""
    cal = ConformalCalibrator(alpha=0.1, min_calibration=10)
    cal.extend([0.001] * 30)  # tau will be ~0.001, no candidate passes
    retriever = ConformalRetriever(store=_populated_store(), calibrator=cal, k=3)
    result = retriever.retrieve("completely unrelated query about pasta cooking")
    composed = compose(result, user_text="q")
    assert result.bound is not None
    assert composed.abstained
    # When abstained, ComposedPrompt still records the bound metadata for the receipt.
    assert composed.tau == result.bound.tau
    assert composed.alpha == result.bound.alpha


def test_compose_step_block_contains_all_accepted_ids():
    retriever = ConformalRetriever(store=_populated_store(n=10), calibrator=_ready_calibrator(), k=5)
    result = retriever.retrieve("alpha beta gamma 3")
    composed = compose(result, user_text="q")
    for sid in composed.reused_step_ids:
        assert sid in composed.system_fragment


def test_retriever_k_negative_raises():
    retriever = ConformalRetriever(store=_populated_store(), calibrator=_ready_calibrator(), k=-5)
    with pytest.raises(ValueError):
        retriever.retrieve("x")
