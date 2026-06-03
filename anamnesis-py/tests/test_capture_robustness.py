# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Capture-adapter robustness: malformed provider responses.

Real provider SDKs occasionally return shapes we didn't see in tests.
Each adapter must produce a sensible CapturedTrace (or empty fields) for:
  - completely empty dict
  - missing 'usage' / 'choices' / 'content'
  - wrong types in nested fields
  - None-valued fields
  - truncated lists
"""

from __future__ import annotations

import pytest
from anamnesis.capture import (
    AnthropicCapture,
    DeepSeekCapture,
    GeminiCapture,
    MistralCapture,
    OpenAICapture,
)


@pytest.fixture(params=[
    AnthropicCapture(),
    OpenAICapture(),
    DeepSeekCapture(),
    GeminiCapture(),
    MistralCapture(),
])
def adapter(request):
    return request.param


def test_adapter_handles_empty_dict(adapter):
    trace = adapter.extract({})
    assert trace.provider == adapter.provider
    assert trace.model == "unknown"
    assert trace.request_id.startswith("req_") or trace.request_id  # auto-generated
    assert trace.thinking_text == ""
    assert trace.answer_text == ""
    assert trace.thinking_tokens == 0
    assert trace.output_tokens == 0


def test_adapter_handles_none_content(adapter):
    response = {"id": "r1", "model": "m", "content": None, "choices": None, "usage": None}
    trace = adapter.extract(response)
    assert trace.thinking_text == ""


def test_adapter_handles_missing_usage(adapter):
    response = {"id": "r2", "model": "m"}
    trace = adapter.extract(response)
    assert trace.output_tokens == 0


def test_anthropic_adapter_handles_wrong_type_in_content():
    response = {"id": "r", "model": "claude-opus-4-7", "content": "this-should-be-a-list", "usage": {"output_tokens": 0}}
    trace = AnthropicCapture().extract(response)
    assert trace.thinking_text == ""
    assert trace.answer_text == ""


def test_anthropic_adapter_handles_unknown_block_type():
    response = {
        "id": "r",
        "model": "m",
        "content": [
            {"type": "image", "text": "ignored"},
            {"type": "thinking", "thinking": "step", "signature": "s"},
            {"type": "tool_use", "name": "calc"},
        ],
        "usage": {"output_tokens": 0, "thinking_tokens": 12},
    }
    trace = AnthropicCapture().extract(response)
    assert trace.thinking_text == "step"


def test_openai_adapter_handles_empty_choices_list():
    trace = OpenAICapture().extract({"id": "r", "model": "o3", "choices": [], "usage": {"completion_tokens": 0}})
    assert trace.answer_text == ""


def test_openai_adapter_handles_missing_message_in_choice():
    trace = OpenAICapture().extract({
        "id": "r",
        "model": "o3",
        "choices": [{"finish_reason": "stop"}],
        "usage": {"completion_tokens": 0},
    })
    assert trace.answer_text == ""


def test_deepseek_adapter_handles_only_closing_think_tag():
    content = "Just an answer without a properly opened tag</think>so this is weird."
    trace = DeepSeekCapture().extract({"id": "r", "model": "deepseek-r1",
                                         "choices": [{"message": {"content": content}}],
                                         "usage": {"completion_tokens": 5}})
    # No proper <think>...</think> pair => empty thinking, full content as answer.
    assert trace.thinking_text == ""
    assert "weird" in trace.answer_text


def test_deepseek_adapter_handles_multiple_think_blocks():
    content = "<think>first thought</think>between<think>second thought</think>final"
    trace = DeepSeekCapture().extract({"id": "r", "model": "deepseek-r1",
                                         "choices": [{"message": {"content": content}}],
                                         "usage": {"completion_tokens": 5}})
    # Our adapter takes the FIRST <think> block.
    assert trace.thinking_text == "first thought"


def test_gemini_adapter_handles_missing_parts_list():
    trace = GeminiCapture().extract({
        "model_version": "gemini-2.5-pro",
        "candidates": [{"content": {}}],
        "usage_metadata": {"candidates_token_count": 0},
    })
    assert trace.thinking_text == ""
    assert trace.answer_text == ""


def test_gemini_adapter_handles_part_without_text():
    trace = GeminiCapture().extract({
        "model_version": "gemini-2.5-pro",
        "candidates": [{"content": {"parts": [{"thought": True}, {"text": "answer"}]}}],
        "usage_metadata": {"candidates_token_count": 5},
    })
    assert trace.thinking_text == ""
    assert trace.answer_text == "answer"


def test_mistral_adapter_handles_dict_content_instead_of_string():
    """Mistral occasionally returns content as a list of blocks instead of a string."""
    response = {
        "id": "m",
        "model": "magistral-medium",
        "choices": [{"message": {"content": ["unexpected", "list"]}}],
        "usage": {"completion_tokens": 0},
    }
    trace = MistralCapture().extract(response)
    # str([...]) is non-crashy; just confirm no exception and producer fields are filled.
    assert trace.provider == "mistral"


def test_all_adapters_handle_pydantic_like_attribute_objects():
    """If the response is a pydantic-like object instead of a dict, attribute access still works."""

    class Resp:
        id = "r"
        model = "m"
        content = []
        choices = []
        usage = type("U", (), {"output_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0})()
        candidates = []
        usage_metadata = type("M", (), {"candidates_token_count": 0, "thoughts_token_count": 0})()
        text = ""
        response_id = "r"

    for adapter in [AnthropicCapture(), OpenAICapture(), DeepSeekCapture(),
                    GeminiCapture(), MistralCapture()]:
        trace = adapter.extract(Resp())
        assert trace.provider == adapter.provider


def test_adapter_request_id_override_takes_precedence(adapter):
    response = {"id": "vendor-id", "model": "m"}
    trace = adapter.extract(response, request_id="explicit-rid")
    assert trace.request_id == "explicit-rid"
