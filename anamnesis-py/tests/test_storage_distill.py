"""Tests for storage and distillation working together."""

from __future__ import annotations

import json

import numpy as np
import pytest

from anamnesis.capture import CapturedTrace
from anamnesis.distill import (
    DISTILL_PROMPT_TEMPLATE,
    HeuristicDistiller,
    LLMDistiller,
    _parse_distilled_json,
    distill_traces,
    render_distill_prompt,
)
from anamnesis.storage import (
    ReasoningStep,
    TraceStore,
    hash_embedder,
)


def _trace(
    thinking: str = "First step. Then this. Finally that.",
    answer: str = "Answer.",
    rid: str = "req_test",
    provider: str = "anthropic",
    model: str = "claude-opus-4-7",
    thinking_tokens: int = 500,
) -> CapturedTrace:
    return CapturedTrace(
        provider=provider,
        model=model,
        request_id=rid,
        thinking_text=thinking,
        answer_text=answer,
        thinking_tokens=thinking_tokens,
        output_tokens=10,
    )


def test_heuristic_distiller_produces_one_step_per_sentence():
    trace = _trace(
        thinking=(
            "Erste Beobachtung der Aufgabe. "
            "Zweite Ableitung der Bedingungen. "
            "Dritte Begruendung warum Schritt vier folgt."
        )
    )
    steps = HeuristicDistiller(min_step_chars=10).distill(trace)
    assert len(steps) == 3
    assert all(s.capture_id == trace.request_id for s in steps)
    assert all(s.tags[0] == "anthropic" for s in steps)


def test_heuristic_distiller_drops_short_fragments():
    trace = _trace(thinking="Ja. Nein. Vielleicht eine wirklich aussagekraeftige Begruendung.")
    steps = HeuristicDistiller(min_step_chars=20).distill(trace)
    assert len(steps) == 1


def test_heuristic_distiller_handles_empty_thinking():
    trace = _trace(thinking="")
    assert HeuristicDistiller().distill(trace) == []


def test_heuristic_distiller_handles_bullet_lists():
    trace = _trace(
        thinking="- erste Beobachtung der Aufgabe\n- zweite Ableitung der Bedingungen\n- dritte Begruendung"
    )
    steps = HeuristicDistiller(min_step_chars=10).distill(trace)
    assert len(steps) >= 2


def test_llm_distiller_parses_clean_json_array():
    def fake_llm(_prompt: str) -> str:
        return json.dumps(
            [
                {
                    "intent": "Identifiziere bekannte Werte",
                    "text": "Wir wissen dass x = 5.",
                    "preconditions": [],
                    "produces": ["x_known"],
                    "tags": ["algebra", "init"],
                },
                {
                    "intent": "Setze in Gleichung ein",
                    "text": "Daraus folgt y = 10.",
                    "preconditions": ["x_known"],
                    "produces": ["y_known"],
                    "tags": ["algebra"],
                },
            ]
        )

    distiller = LLMDistiller(llm=fake_llm)
    steps = distiller.distill(_trace(thinking="Wir loesen die Gleichung."))
    assert len(steps) == 2
    assert steps[0].intent == "Identifiziere bekannte Werte"
    assert steps[1].preconditions == ("x_known",)
    assert steps[1].produces == ("y_known",)


def test_llm_distiller_tolerates_markdown_fences():
    def fake_llm(_prompt: str) -> str:
        return '```json\n[{"intent": "ok", "text": "ok text", "preconditions": [], "produces": [], "tags": []}]\n```'

    distiller = LLMDistiller(llm=fake_llm)
    steps = distiller.distill(_trace())
    assert len(steps) == 1


def test_llm_distiller_returns_empty_on_invalid_json():
    distiller = LLMDistiller(llm=lambda _: "not json at all")
    assert distiller.distill(_trace()) == []


def test_llm_distiller_skips_empty_text_entries():
    def fake_llm(_prompt: str) -> str:
        return json.dumps(
            [
                {"intent": "x", "text": "", "preconditions": [], "produces": [], "tags": []},
                {"intent": "y", "text": "something", "preconditions": [], "produces": [], "tags": []},
            ]
        )

    distiller = LLMDistiller(llm=fake_llm)
    assert len(distiller.distill(_trace())) == 1


def test_distill_traces_helper_aggregates():
    distiller = HeuristicDistiller(min_step_chars=5)
    traces = [
        _trace(thinking="alpha sentence here. beta sentence here.", rid="r1"),
        _trace(thinking="gamma sentence here. delta sentence here.", rid="r2"),
    ]
    steps = distill_traces(distiller, traces)
    assert len({s.capture_id for s in steps}) == 2


def test_parse_distilled_json_handles_prose_wrap():
    assert _parse_distilled_json('Sure, here it is: [{"a":1}] hope that helps') == [{"a": 1}]


def test_distill_prompt_template_is_versionable():
    assert "<<<THINKING_TRACE>>>" in DISTILL_PROMPT_TEMPLATE
    assert "JSON array" in DISTILL_PROMPT_TEMPLATE


def test_render_distill_prompt_substitutes_thinking():
    out = render_distill_prompt("MY_THINK")
    assert "<<<THINKING_TRACE>>>" not in out
    assert "MY_THINK" in out


def test_trace_store_add_and_retrieve_trace():
    store = TraceStore(embedder=hash_embedder(dim=64))
    trace = _trace(thinking="x. y.")
    tid = store.add_trace(trace)
    assert tid.startswith("trace_")
    assert store.n_traces == 1
    recovered = store.get_trace(tid)
    assert recovered.thinking_text == trace.thinking_text
    assert recovered.provider == trace.provider


def test_trace_store_add_steps_and_query_similar():
    store = TraceStore(embedder=hash_embedder(dim=64))
    cap_id = "req_demo"
    steps = [
        ReasoningStep.make(cap_id, "Calculate eigenvalues of a 2x2 matrix.", "eigen", tags=("math",)),
        ReasoningStep.make(cap_id, "Bake a chocolate cake with sugar and eggs.", "bake", tags=("food",)),
        ReasoningStep.make(cap_id, "Solve the quadratic equation by completing the square.", "quad", tags=("math",)),
    ]
    store.add_steps(steps)
    assert store.n_steps == 3

    results = store.query_similar_steps("How do I bake chocolate cookies?", k=2)
    assert len(results) == 2
    top_step, top_score = results[0]
    assert "Bake" in top_step.text or "cake" in top_step.text
    assert 0.0 <= top_score <= 2.0


def test_trace_store_returns_empty_when_no_steps():
    store = TraceStore(embedder=hash_embedder(dim=32))
    assert store.query_similar_steps("anything", k=3) == []


def test_trace_store_get_unknown_raises():
    store = TraceStore(embedder=hash_embedder(dim=16))
    with pytest.raises(KeyError):
        store.get_step("nope")
    with pytest.raises(KeyError):
        store.get_trace("nope")


def test_trace_store_list_steps_for_trace():
    store = TraceStore(embedder=hash_embedder(dim=32))
    s1 = ReasoningStep.make("cap_a", "alpha step", "i", tags=())
    s2 = ReasoningStep.make("cap_a", "beta step", "i", tags=())
    s3 = ReasoningStep.make("cap_b", "gamma step", "i", tags=())
    store.add_steps([s1, s2, s3])
    assert {s.step_id for s in store.list_steps_for_trace("cap_a")} == {s1.step_id, s2.step_id}


def test_hash_embedder_is_deterministic_and_unit_norm():
    e = hash_embedder(dim=64)
    v1 = e("Hallo Welt")
    v2 = e("Hallo Welt")
    assert np.allclose(v1, v2)
    assert v1.shape == (64,)
    assert np.isclose(np.linalg.norm(v1), 1.0)
    v3 = e("voellig anderer Text")
    assert not np.allclose(v1, v3)


def test_hash_embedder_handles_empty_text():
    e = hash_embedder(dim=8)
    v = e("")
    assert v.shape == (8,)
    assert np.isclose(np.linalg.norm(v), 1.0)


def test_persistent_store_round_trip(tmp_path):
    db_file = tmp_path / "anamnesis.db"
    embedder = hash_embedder(dim=32)
    store = TraceStore(embedder=embedder, db_path=db_file)
    trace = _trace()
    tid = store.add_trace(trace)
    steps = [ReasoningStep.make("req_test", "alpha", "i")]
    store.add_steps(steps)
    store.close()

    store2 = TraceStore(embedder=embedder, db_path=db_file)
    assert store2.n_traces == 1
    recovered = store2.get_trace(tid)
    assert recovered.thinking_text == trace.thinking_text
    fetched = store2.get_step(steps[0].step_id)
    assert fetched.text == "alpha"
    store2.close()
