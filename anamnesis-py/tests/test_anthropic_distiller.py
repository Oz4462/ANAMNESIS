"""Tests for the production Anthropic-Haiku distiller (no real API calls).

The Anthropic SDK is mocked so the tests run without network access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from anamnesis.capture import CapturedTrace
from anamnesis.distill import (
    AnthropicHaikuDistiller,
    HeuristicDistiller,
    distiller_for,
)


def _trace(thinking: str = "step one. step two. step three.") -> CapturedTrace:
    return CapturedTrace(
        provider="anthropic",
        model="claude-opus-4-7",
        request_id="req_test",
        thinking_text=thinking,
        answer_text="ok",
        thinking_tokens=100,
        output_tokens=10,
    )


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


class FakeMessages:
    def __init__(self, response_text: str) -> None:
        self._text = response_text
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)

        class Resp:
            def __init__(self, text: str) -> None:
                self.content = [FakeTextBlock(text=text)]

        return Resp(self._text)


class FakeAnthropic:
    def __init__(self, response_text: str) -> None:
        self.messages = FakeMessages(response_text)


def test_anthropic_haiku_distiller_falls_back_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    distiller = AnthropicHaikuDistiller()
    steps = distiller.distill(
        _trace(
            thinking=(
                "Erste ausfuehrliche Begruendung dieser Aufgabe. "
                "Zweite vollstaendige Argumentationskette mit Schluss."
            )
        )
    )
    # No key -> get_client raises -> distill returns heuristic fallback
    assert len(steps) >= 1
    assert all(s.capture_id == "req_test" for s in steps)


def test_anthropic_haiku_distiller_parses_llm_response():
    valid_json = json.dumps(
        [
            {
                "intent": "Identify base and height",
                "text": "Wir kennen Basis und Hoehe.",
                "preconditions": [],
                "produces": ["b_known", "h_known"],
                "tags": ["geometry"],
            },
            {
                "intent": "Apply area formula",
                "text": "Berechne A = 1/2 * b * h.",
                "preconditions": ["b_known", "h_known"],
                "produces": ["A_known"],
                "tags": ["geometry"],
            },
        ]
    )
    distiller = AnthropicHaikuDistiller(api_key="sk-fake")
    distiller._client = FakeAnthropic(valid_json)  # type: ignore[assignment]

    steps = distiller.distill(_trace())
    assert len(steps) == 2
    assert steps[0].intent == "Identify base and height"
    assert steps[1].preconditions == ("b_known", "h_known")


def test_anthropic_haiku_distiller_falls_back_on_invalid_response():
    distiller = AnthropicHaikuDistiller(api_key="sk-fake")
    distiller._client = FakeAnthropic("absolute garbage that is not json")  # type: ignore[assignment]
    steps = distiller.distill(
        _trace(
            thinking=(
                "Erste ausfuehrliche Begruendung dieser Aufgabe. "
                "Zweite vollstaendige Argumentationskette mit Schluss."
            )
        )
    )
    # Falls back to heuristic, which still produces something
    assert len(steps) >= 1


def test_anthropic_haiku_distiller_falls_back_on_sdk_exception():
    class BlowUp:
        @property
        def messages(self):
            raise RuntimeError("simulated network failure")

    distiller = AnthropicHaikuDistiller(api_key="sk-fake")
    distiller._client = BlowUp()  # type: ignore[assignment]
    steps = distiller.distill(
        _trace(
            thinking=(
                "Erste ausfuehrliche Begruendung dieser Aufgabe. "
                "Zweite vollstaendige Argumentationskette mit Schluss."
            )
        )
    )
    assert len(steps) >= 1  # graceful fallback


def test_anthropic_haiku_distiller_empty_thinking_returns_empty():
    distiller = AnthropicHaikuDistiller(api_key="sk-fake")
    distiller._client = FakeAnthropic("[]")  # type: ignore[assignment]
    assert distiller.distill(_trace(thinking="")) == []


def test_distiller_for_factory_dispatches():
    assert isinstance(distiller_for(), HeuristicDistiller)
    assert isinstance(distiller_for("heuristic"), HeuristicDistiller)
    assert isinstance(distiller_for("haiku", api_key="sk-x"), AnthropicHaikuDistiller)
    assert isinstance(distiller_for("anthropic-haiku", api_key="sk-x"), AnthropicHaikuDistiller)
    with pytest.raises(ValueError):
        distiller_for("not-a-real-distiller")


def test_anthropic_haiku_distiller_sends_versioned_prompt():
    distiller = AnthropicHaikuDistiller(api_key="sk-fake")
    fake = FakeAnthropic("[]")
    distiller._client = fake  # type: ignore[assignment]
    distiller.distill(_trace(thinking="MY-THINK"))
    assert len(fake.messages.calls) == 1
    sent_prompt = fake.messages.calls[0]["messages"][0]["content"]
    assert "MY-THINK" in sent_prompt
    assert "JSON array" in sent_prompt
