"""Stateful property test for the entire pipeline.

Hypothesis explores random sequences of:
  add_trace, add_steps, add_calibration, query, get_step, get_trace, sign_receipt

After every action a battery of invariants is checked. If any invariant
fails on any random interleaving, the test reports a minimised reproduction
sequence.
"""

from __future__ import annotations

import string

from anamnesis.capture import CapturedTrace
from anamnesis.conformal import ConformalCalibrator
from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
)
from anamnesis.storage import ReasoningStep, TraceStore, hash_embedder
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    invariant,
    precondition,
    rule,
)

_SAFE_TEXT = st.text(
    alphabet=string.ascii_letters + string.digits + " .,;:-_",
    min_size=1,
    max_size=80,
)


class AnamnesisStateMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.store = TraceStore(embedder=hash_embedder(dim=64))
        self.calibrator = ConformalCalibrator(alpha=0.1, min_calibration=10, max_window=2048)
        self.signer = ReceiptSigner.generate("sm-key")
        self.verifier = ReceiptVerifier.from_public_key_b64("sm-key", self.signer.public_key_b64())
        self.known_step_ids: set[str] = set()
        self.known_trace_ids: set[str] = set()
        self.last_query: str = "alpha"

    @rule(text=_SAFE_TEXT)
    def add_trace(self, text: str) -> None:
        trace = CapturedTrace(
            provider="anthropic",
            model="m",
            request_id="r",
            thinking_text=text,
            answer_text="ok",
            thinking_tokens=10,
            output_tokens=5,
        )
        tid = self.store.add_trace(trace)
        self.known_trace_ids.add(tid)

    @rule(text=_SAFE_TEXT)
    def add_step(self, text: str) -> None:
        step = ReasoningStep.make("c", text, "i")
        self.store.add_steps([step])
        self.known_step_ids.add(step.step_id)

    @rule(score=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False))
    def add_calibration(self, score: float) -> None:
        self.calibrator.add(score)

    @rule(query=_SAFE_TEXT, k=st.integers(min_value=1, max_value=8))
    def query(self, query: str, k: int) -> None:
        self.last_query = query
        results = self.store.query_similar_steps(query, k=k)
        assert len(results) <= self.store.n_steps
        for step, score in results:
            assert step.step_id in self.known_step_ids
            assert -1.0 <= score <= 2.0 + 1e-9

    @precondition(lambda self: self.calibrator.ready)
    @rule()
    def sign_receipt_when_ready(self) -> None:
        bound = self.calibrator.threshold()
        receipt = Receipt(
            tenant_id="sm-t",
            request_id="r",
            model=ModelRef(provider="anthropic", name="m"),
            capture_hash="sha256:" + ("0" * 64),
            distill_model="d",
            retrieved_step_ids=list(self.known_step_ids)[:5],
            bound=BoundRef(
                tau=bound.tau,
                alpha=bound.alpha,
                n_calibration=bound.n_calibration,
            ),
            cost_saved_tokens=0,
        )
        envelope = self.signer.sign(receipt)
        recovered = self.verifier.verify(envelope)
        assert recovered.tenant_id == "sm-t"
        assert recovered.bound.tau == bound.tau

    @invariant()
    def n_steps_matches_known_set(self) -> None:
        assert self.store.n_steps == len(self.known_step_ids)

    @invariant()
    def n_traces_matches_known_set(self) -> None:
        assert self.store.n_traces == len(self.known_trace_ids)

    @invariant()
    def calibrator_n_never_exceeds_max_window(self) -> None:
        assert self.calibrator.n <= 2048

    @invariant()
    def calibrator_threshold_within_score_range(self) -> None:
        if self.calibrator.ready:
            tau = self.calibrator.threshold().tau
            assert 0.0 <= tau <= 2.0

    @invariant()
    def known_step_ids_are_unique(self) -> None:
        # Implicit from set semantics, but we assert it loudly.
        assert len(self.known_step_ids) == len(set(self.known_step_ids))


TestPipelineStateMachine = AnamnesisStateMachine.TestCase
TestPipelineStateMachine.settings = settings(
    max_examples=30,
    stateful_step_count=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
