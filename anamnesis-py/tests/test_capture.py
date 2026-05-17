"""Tests for multi-provider capture adapters using mock SDK response shapes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from anamnesis.capture import (
    AnthropicCapture,
    CapturedTrace,
    DeepSeekCapture,
    OpenAICapture,
    adapter_for,
)


@dataclass
class FakeBlock:
    type: str
    thinking: str | None = None
    signature: str | None = None
    text: str | None = None


@dataclass
class FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class FakeAnthropicResponse:
    id: str
    model: str
    content: list[FakeBlock]
    usage: FakeUsage
    stop_reason: str = "end_turn"


def test_anthropic_capture_extracts_thinking_and_answer():
    response = FakeAnthropicResponse(
        id="msg_abc",
        model="claude-opus-4-7",
        content=[
            FakeBlock(type="thinking", thinking="step 1\nstep 2", signature="sigsigsig"),
            FakeBlock(type="text", text="42"),
        ],
        usage=FakeUsage(output_tokens=10, thinking_tokens=120),
    )
    trace = AnthropicCapture().extract(response)
    assert trace.provider == "anthropic"
    assert trace.model == "claude-opus-4-7"
    assert trace.request_id == "msg_abc"
    assert trace.thinking_text == "step 1\nstep 2"
    assert trace.answer_text == "42"
    assert trace.signature == "sigsigsig"
    assert trace.thinking_tokens == 120
    assert trace.output_tokens == 10
    assert trace.has_thinking
    assert trace.total_billed_tokens == 130


def test_anthropic_capture_handles_dict_payloads():
    response: dict[str, Any] = {
        "id": "msg_xyz",
        "model": "claude-haiku-4-5",
        "content": [
            {"type": "thinking", "thinking": "hmm", "signature": "abc"},
            {"type": "text", "text": "ok"},
        ],
        "usage": {"output_tokens": 5, "thinking_tokens": 40},
        "stop_reason": "end_turn",
    }
    trace = AnthropicCapture().extract(response)
    assert trace.thinking_text == "hmm"
    assert trace.answer_text == "ok"
    assert trace.thinking_tokens == 40


def test_anthropic_capture_falls_back_to_estimated_token_count():
    response = FakeAnthropicResponse(
        id="msg_no_usage",
        model="claude-opus-4-7",
        content=[FakeBlock(type="thinking", thinking="x" * 400), FakeBlock(type="text", text="z")],
        usage=FakeUsage(output_tokens=1, thinking_tokens=0),
    )
    trace = AnthropicCapture().extract(response)
    assert trace.thinking_tokens > 50


def test_anthropic_capture_handles_missing_thinking_block():
    response = FakeAnthropicResponse(
        id="msg_no_think",
        model="claude-opus-4-7",
        content=[FakeBlock(type="text", text="just the answer")],
        usage=FakeUsage(output_tokens=3),
    )
    trace = AnthropicCapture().extract(response)
    assert trace.thinking_text == ""
    assert trace.answer_text == "just the answer"
    assert not trace.has_thinking


@dataclass
class FakeMessage:
    content: str
    reasoning_summary: str | None = None


@dataclass
class FakeChoice:
    message: FakeMessage
    finish_reason: str = "stop"


@dataclass
class FakeOpenAIUsage:
    completion_tokens: int = 0
    prompt_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass
class FakeOpenAIResponse:
    id: str
    model: str
    choices: list[FakeChoice]
    usage: FakeOpenAIUsage


def test_openai_capture_extracts_reasoning_summary_and_tokens():
    response = FakeOpenAIResponse(
        id="resp_001",
        model="o3-mini",
        choices=[
            FakeChoice(
                message=FakeMessage(
                    content="The answer is 42.",
                    reasoning_summary="Considered options A, B, C and selected B.",
                )
            )
        ],
        usage=FakeOpenAIUsage(completion_tokens=20, reasoning_tokens=4500),
    )
    trace = OpenAICapture().extract(response)
    assert trace.provider == "openai"
    assert trace.model == "o3-mini"
    assert trace.request_id == "resp_001"
    assert trace.thinking_text == "Considered options A, B, C and selected B."
    assert trace.answer_text == "The answer is 42."
    assert trace.thinking_tokens == 4500
    assert trace.output_tokens == 20


def test_openai_capture_handles_missing_reasoning_summary():
    response: dict[str, Any] = {
        "id": "resp_no_sum",
        "model": "o1-preview",
        "choices": [{"message": {"content": "final"}, "finish_reason": "stop"}],
        "usage": {"completion_tokens": 8, "reasoning_tokens": 1234},
    }
    trace = OpenAICapture().extract(response)
    assert trace.thinking_text == ""
    assert trace.answer_text == "final"
    assert trace.thinking_tokens == 1234


def test_openai_capture_reads_nested_completion_tokens_details():
    response: dict[str, Any] = {
        "id": "resp_nested",
        "model": "o3",
        "choices": [{"message": {"content": "x"}}],
        "usage": {
            "completion_tokens": 3,
            "completion_tokens_details": {"reasoning_tokens": 9000},
        },
    }
    trace = OpenAICapture().extract(response)
    assert trace.thinking_tokens == 9000


def test_deepseek_capture_extracts_inline_think_tag():
    content = "<think>\nstep one\nstep two\n</think>\nFinal answer: 42"
    response: dict[str, Any] = {
        "id": "ds_1",
        "model": "deepseek-r1",
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"completion_tokens": 16, "reasoning_tokens": 800},
    }
    trace = DeepSeekCapture().extract(response)
    assert trace.thinking_text == "step one\nstep two"
    assert trace.answer_text == "Final answer: 42"
    assert trace.thinking_tokens == 800
    assert trace.output_tokens == 16


def test_deepseek_capture_estimates_tokens_when_provider_silent():
    content = "<think>" + "a" * 600 + "</think>answer"
    response: dict[str, Any] = {
        "id": "ds_2",
        "model": "deepseek-r1-distill",
        "choices": [{"message": {"content": content}}],
        "usage": {"completion_tokens": 4},
    }
    trace = DeepSeekCapture().extract(response)
    assert trace.thinking_tokens >= 100


def test_deepseek_capture_handles_no_think_tag():
    response: dict[str, Any] = {
        "id": "ds_3",
        "model": "deepseek-chat",
        "choices": [{"message": {"content": "no thinking here"}}],
        "usage": {"completion_tokens": 5},
    }
    trace = DeepSeekCapture().extract(response)
    assert trace.thinking_text == ""
    assert trace.answer_text == "no thinking here"
    assert trace.thinking_tokens == 0


def test_content_hash_is_stable_and_changes_with_content():
    from dataclasses import replace

    a = CapturedTrace(
        provider="anthropic",
        model="claude-opus-4-7",
        request_id="r1",
        thinking_text="t",
        answer_text="a",
        thinking_tokens=1,
        output_tokens=1,
    )
    b = replace(a, answer_text="a")
    c = replace(a, answer_text="different")
    assert a.content_hash == b.content_hash
    assert a.content_hash != c.content_hash
    assert a.content_hash.startswith("sha256:")


def test_adapter_for_dispatches_by_name():
    assert isinstance(adapter_for("anthropic"), AnthropicCapture)
    assert isinstance(adapter_for("OpenAI"), OpenAICapture)
    assert isinstance(adapter_for("DEEPSEEK"), DeepSeekCapture)
    with pytest.raises(ValueError):
        adapter_for("bedrock")


def test_request_id_auto_generated_when_missing():
    response: dict[str, Any] = {
        "model": "claude-opus-4-7",
        "content": [{"type": "text", "text": "ok"}],
        "usage": {"output_tokens": 1},
    }
    trace = AnthropicCapture().extract(response)
    assert trace.request_id.startswith("req_")
