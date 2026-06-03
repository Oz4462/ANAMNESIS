# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Tests for the Gemini + Mistral capture adapters."""

from __future__ import annotations

from typing import Any

import pytest
from anamnesis.capture import (
    GeminiCapture,
    MistralCapture,
    adapter_for,
)


def test_gemini_capture_extracts_thought_part_and_token_count():
    response: dict[str, Any] = {
        "response_id": "gem_001",
        "model_version": "gemini-2.5-pro",
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"thought": True, "text": "Step 1 reasoning here."},
                        {"text": "Final answer is 42."},
                    ]
                },
                "finish_reason": "STOP",
            }
        ],
        "usage_metadata": {
            "candidates_token_count": 12,
            "thoughts_token_count": 800,
        },
    }
    trace = GeminiCapture().extract(response)
    assert trace.provider == "gemini"
    assert trace.model == "gemini-2.5-pro"
    assert trace.request_id == "gem_001"
    assert trace.thinking_text == "Step 1 reasoning here."
    assert trace.answer_text == "Final answer is 42."
    assert trace.thinking_tokens == 800
    assert trace.output_tokens == 12


def test_gemini_capture_estimates_thinking_when_silent():
    response: dict[str, Any] = {
        "model_version": "gemini-2.5-flash",
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"thought": True, "text": "x" * 400},
                        {"text": "answer"},
                    ]
                }
            }
        ],
        "usage_metadata": {"candidates_token_count": 5},
    }
    trace = GeminiCapture().extract(response)
    assert trace.thinking_tokens >= 50


def test_gemini_capture_falls_back_to_top_level_text():
    response: dict[str, Any] = {
        "model_version": "gemini-2.5-pro",
        "candidates": [{"content": {"parts": []}}],
        "text": "fallback answer",
        "usage_metadata": {"candidates_token_count": 2},
    }
    trace = GeminiCapture().extract(response)
    assert trace.answer_text == "fallback answer"
    assert trace.thinking_text == ""


def test_mistral_capture_extracts_inline_think_tag():
    response: dict[str, Any] = {
        "id": "mist_1",
        "model": "magistral-medium-2509",
        "choices": [
            {"message": {"content": "<think>think hard</think>The answer is X."}, "finish_reason": "stop"}
        ],
        "usage": {"completion_tokens": 7, "reasoning_tokens": 350},
    }
    trace = MistralCapture().extract(response)
    assert trace.provider == "mistral"
    assert trace.thinking_text == "think hard"
    assert trace.answer_text == "The answer is X."
    assert trace.thinking_tokens == 350
    assert trace.output_tokens == 7


def test_mistral_capture_reads_reasoning_field_when_no_think_tag():
    response: dict[str, Any] = {
        "id": "mist_2",
        "model": "magistral-small",
        "choices": [
            {
                "message": {
                    "content": "Just the answer.",
                    "reasoning": "private chain of thought here",
                }
            }
        ],
        "usage": {"completion_tokens": 4},
    }
    trace = MistralCapture().extract(response)
    assert trace.thinking_text == "private chain of thought here"
    assert trace.answer_text == "Just the answer."


def test_adapter_for_dispatches_gemini_and_mistral():
    assert isinstance(adapter_for("gemini"), GeminiCapture)
    assert isinstance(adapter_for("Google"), GeminiCapture)
    assert isinstance(adapter_for("vertex"), GeminiCapture)
    assert isinstance(adapter_for("mistral"), MistralCapture)
    assert isinstance(adapter_for("Magistral"), MistralCapture)
    with pytest.raises(ValueError):
        adapter_for("bedrock")
