# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Multi-provider capture of reasoning-model thinking traces.

Today's reasoning APIs each expose their internal chain-of-thought differently:

    * Anthropic Claude Extended Thinking returns a list of content blocks; the
      thinking blocks carry the model's deliberation plus a cryptographic
      signature the user must echo back on tool-result turns.
    * OpenAI o1/o3 do not expose tokens themselves but report a
      reasoning_tokens count in usage; some endpoints accept a
      reasoning.summary="auto" parameter and return a textual summary.
    * DeepSeek R1 emits its thinking inline as a leading <think>...</think>
      block in the message content.

A capture adapter extracts a vendor-agnostic CapturedTrace from each shape so
the rest of the pipeline (distill, index, retrieve, receipt) stays uniform.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

THINK_TAG_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


@dataclass(frozen=True, slots=True)
class CapturedTrace:
    """A vendor-agnostic captured reasoning trace.

    Attributes:
        provider: Lowercase vendor id (e.g. "anthropic", "openai", "deepseek").
        model: Provider-reported model identifier.
        request_id: Caller-supplied or auto-generated stable id for joining.
        thinking_text: The internal deliberation text. May be empty if the
            provider does not expose it.
        answer_text: The user-visible answer text.
        thinking_tokens: Provider-reported count of thinking tokens billed.
        output_tokens: Provider-reported count of visible-output tokens.
        signature: Provider-issued signature over the thinking block, if any
            (Anthropic Extended Thinking uses this for tool-use round-trips).
        metadata: Provider-specific extras (e.g. stop_reason, finish_reason).
    """

    provider: str
    model: str
    request_id: str
    thinking_text: str
    answer_text: str
    thinking_tokens: int
    output_tokens: int
    signature: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        h = hashlib.sha256()
        h.update(self.provider.encode())
        h.update(b"\0")
        h.update(self.model.encode())
        h.update(b"\0")
        h.update(self.thinking_text.encode())
        h.update(b"\0")
        h.update(self.answer_text.encode())
        return "sha256:" + h.hexdigest()

    @property
    def has_thinking(self) -> bool:
        return bool(self.thinking_text)

    @property
    def total_billed_tokens(self) -> int:
        return self.thinking_tokens + self.output_tokens


class CaptureAdapter(Protocol):
    provider: str

    def extract(self, response: Any, request_id: str | None = None) -> CapturedTrace: ...


def _new_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:16]


def _get_field(obj: Any, *path: Any, default: Any = None) -> Any:
    """Walk a path of attributes, dict-keys, and list-indices.

    Each path segment can be a string (attribute or dict key) or an int
    (list index). Returns `default` as soon as a segment cannot be resolved,
    which keeps capture adapters tolerant of partial or shape-shifted SDK
    responses without raising AttributeError / KeyError / IndexError.
    """
    for segment in path:
        if obj is None:
            return default
        if isinstance(segment, int):
            try:
                obj = obj[segment]
            except (IndexError, KeyError, TypeError):
                return default
            continue
        if isinstance(segment, str):
            if isinstance(obj, dict):
                if segment in obj:
                    obj = obj[segment]
                else:
                    return default
            elif hasattr(obj, segment):
                obj = getattr(obj, segment)
            else:
                return default
            continue
        return default
    return obj if obj is not None else default


class AnthropicCapture:
    """Adapter for Anthropic Messages API with `thinking=...` enabled.

    Expects the standard SDK response shape::

        response.id = "msg_..."
        response.model = "claude-opus-4-7"
        response.content = [ThinkingBlock(type="thinking", thinking=..., signature=...),
                            TextBlock(type="text", text=...)]
        response.usage.input_tokens / .output_tokens / .cache_creation_input_tokens
    """

    provider = "anthropic"

    def extract(self, response: Any, request_id: str | None = None) -> CapturedTrace:
        model = _get_field(response, "model", default="unknown")
        msg_id = _get_field(response, "id")
        rid = request_id or msg_id or _new_request_id()

        thinking_parts: list[str] = []
        answer_parts: list[str] = []
        signature: str | None = None

        for block in _get_field(response, "content", default=[]) or []:
            block_type = _get_field(block, "type")
            if block_type == "thinking":
                text = _get_field(block, "thinking", default="") or ""
                thinking_parts.append(str(text))
                sig = _get_field(block, "signature")
                if sig:
                    signature = str(sig)
            elif block_type == "text":
                text = _get_field(block, "text", default="") or ""
                answer_parts.append(str(text))

        usage = _get_field(response, "usage", default={})
        output_tokens = int(_get_field(usage, "output_tokens", default=0) or 0)
        thinking_tokens = int(_get_field(usage, "thinking_tokens", default=0) or 0)

        if thinking_tokens == 0 and thinking_parts:
            thinking_tokens = _rough_token_count("\n".join(thinking_parts))

        return CapturedTrace(
            provider=self.provider,
            model=str(model),
            request_id=rid,
            thinking_text="\n".join(thinking_parts).strip(),
            answer_text="\n".join(answer_parts).strip(),
            thinking_tokens=thinking_tokens,
            output_tokens=output_tokens,
            signature=signature,
            metadata={"stop_reason": _get_field(response, "stop_reason")},
        )


class OpenAICapture:
    """Adapter for OpenAI Responses API or Chat-Completions with reasoning models.

    Two shapes are supported:

    * Chat Completions with reasoning models (o1/o3): usage.reasoning_tokens
      is reported; the message content contains only the final answer.
      Optionally a `reasoning_summary` field carries a vendor-provided summary.

    * Responses API: response.reasoning_summary may carry a textual summary.
    """

    provider = "openai"

    def extract(self, response: Any, request_id: str | None = None) -> CapturedTrace:
        model = _get_field(response, "model", default="unknown")
        msg_id = _get_field(response, "id")
        rid = request_id or msg_id or _new_request_id()

        answer_text = (
            _get_field(response, "choices", 0, "message", "content", default=None)
            or _get_field(response, "output_text", default=None)
            or ""
        )

        thinking_text = (
            _get_field(response, "reasoning_summary", default=None)
            or _get_field(response, "choices", 0, "message", "reasoning_summary", default=None)
            or ""
        )

        usage = _get_field(response, "usage", default={})
        output_tokens = int(
            _get_field(usage, "output_tokens", default=None)
            or _get_field(usage, "completion_tokens", default=0)
            or 0
        )
        reasoning_tokens = int(
            _get_field(usage, "reasoning_tokens", default=None)
            or _get_field(usage, "output_tokens_details", "reasoning_tokens", default=None)
            or _get_field(usage, "completion_tokens_details", "reasoning_tokens", default=0)
            or 0
        )

        return CapturedTrace(
            provider=self.provider,
            model=str(model),
            request_id=rid,
            thinking_text=str(thinking_text or "").strip(),
            answer_text=str(answer_text or "").strip(),
            thinking_tokens=reasoning_tokens,
            output_tokens=output_tokens,
            signature=None,
            metadata={"finish_reason": _get_field(response, "choices", 0, "finish_reason")},
        )


class DeepSeekCapture:
    """Adapter for DeepSeek-R1 and compatible <think>-tagged responses.

    DeepSeek-R1 emits the chain-of-thought inline in the assistant message,
    wrapped in a single <think>...</think> block at the start of `content`.
    """

    provider = "deepseek"

    def extract(self, response: Any, request_id: str | None = None) -> CapturedTrace:
        model = _get_field(response, "model", default="unknown")
        msg_id = _get_field(response, "id")
        rid = request_id or msg_id or _new_request_id()

        content = (
            _get_field(response, "choices", 0, "message", "content", default=None)
            or _get_field(response, "content", default=None)
            or ""
        )
        content = str(content)

        match = THINK_TAG_RE.search(content)
        thinking_text = match.group(1).strip() if match else ""
        answer_text = THINK_TAG_RE.sub("", content).strip()

        usage = _get_field(response, "usage", default={})
        output_tokens = int(_get_field(usage, "completion_tokens", default=0) or 0)
        thinking_tokens = int(
            _get_field(usage, "reasoning_tokens", default=None)
            or _get_field(usage, "completion_tokens_details", "reasoning_tokens", default=0)
            or (_rough_token_count(thinking_text) if thinking_text else 0)
        )

        return CapturedTrace(
            provider=self.provider,
            model=str(model),
            request_id=rid,
            thinking_text=thinking_text,
            answer_text=answer_text,
            thinking_tokens=thinking_tokens,
            output_tokens=output_tokens,
            signature=None,
            metadata={"finish_reason": _get_field(response, "choices", 0, "finish_reason")},
        )


def _rough_token_count(text: str) -> int:
    """Cheap fallback token estimate when the provider does not report one.

    Uses a ~4-chars-per-token heuristic that matches GPT-style BPE within
    roughly 20 percent for English-prose reasoning traces. Real billing should
    always come from the provider's `usage` field; this is only a safety net
    so downstream metrics never silently report zero saved tokens.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


class GeminiCapture:
    """Adapter for Google Gemini 2.5 thinking models.

    Gemini exposes thinking summaries in two places depending on API version:

    - `response.candidates[0].content.parts[]` may include a part with
      `thought=True` whose `text` field is the thinking summary.
    - `response.usage_metadata.thoughts_token_count` (sometimes
      `reasoning_token_count`) reports billed thinking tokens.

    We tolerate both the new and the legacy shape.
    """

    provider = "gemini"

    def extract(self, response: Any, request_id: str | None = None) -> CapturedTrace:
        model = (
            _get_field(response, "model_version", default=None)
            or _get_field(response, "model", default="unknown")
        )
        msg_id = _get_field(response, "response_id", default=None) or _get_field(
            response, "id", default=None
        )
        rid = request_id or msg_id or _new_request_id()

        thinking_parts: list[str] = []
        answer_parts: list[str] = []
        parts = _get_field(response, "candidates", 0, "content", "parts", default=None)
        if parts is None:
            parts = _get_field(response, "parts", default=[]) or []
        for part in parts or []:
            text = _get_field(part, "text", default="")
            if not text:
                continue
            is_thought = bool(_get_field(part, "thought", default=False))
            if is_thought:
                thinking_parts.append(str(text))
            else:
                answer_parts.append(str(text))

        if not answer_parts:
            fallback = _get_field(response, "text", default="")
            if fallback:
                answer_parts.append(str(fallback))

        usage = _get_field(response, "usage_metadata", default={}) or _get_field(
            response, "usage", default={}
        )
        output_tokens = int(
            _get_field(usage, "candidates_token_count", default=None)
            or _get_field(usage, "output_tokens", default=0)
            or 0
        )
        thinking_tokens = int(
            _get_field(usage, "thoughts_token_count", default=None)
            or _get_field(usage, "reasoning_token_count", default=None)
            or _get_field(usage, "thinking_tokens", default=0)
            or (_rough_token_count("\n".join(thinking_parts)) if thinking_parts else 0)
        )

        return CapturedTrace(
            provider=self.provider,
            model=str(model),
            request_id=rid,
            thinking_text="\n".join(thinking_parts).strip(),
            answer_text="\n".join(answer_parts).strip(),
            thinking_tokens=thinking_tokens,
            output_tokens=output_tokens,
            signature=None,
            metadata={"finish_reason": _get_field(response, "candidates", 0, "finish_reason")},
        )


class MistralCapture:
    """Adapter for Mistral / Magistral reasoning responses.

    Magistral exposes thinking via two paths:
    - inline `<think>...</think>` blocks in the assistant message (like DeepSeek-R1)
    - `prefix` style where the first message turn is the thinking summary
    """

    provider = "mistral"

    def extract(self, response: Any, request_id: str | None = None) -> CapturedTrace:
        model = _get_field(response, "model", default="unknown")
        msg_id = _get_field(response, "id")
        rid = request_id or msg_id or _new_request_id()

        content = (
            _get_field(response, "choices", 0, "message", "content", default=None)
            or _get_field(response, "content", default=None)
            or ""
        )
        content = str(content)

        match = THINK_TAG_RE.search(content)
        thinking_text = match.group(1).strip() if match else ""
        answer_text = THINK_TAG_RE.sub("", content).strip()

        if not thinking_text:
            thinking_text = str(
                _get_field(response, "choices", 0, "message", "reasoning", default="")
                or _get_field(response, "reasoning", default="")
            ).strip()

        usage = _get_field(response, "usage", default={})
        output_tokens = int(_get_field(usage, "completion_tokens", default=0) or 0)
        thinking_tokens = int(
            _get_field(usage, "reasoning_tokens", default=None)
            or _get_field(usage, "thinking_tokens", default=None)
            or (_rough_token_count(thinking_text) if thinking_text else 0)
        )

        return CapturedTrace(
            provider=self.provider,
            model=str(model),
            request_id=rid,
            thinking_text=thinking_text,
            answer_text=answer_text,
            thinking_tokens=thinking_tokens,
            output_tokens=output_tokens,
            signature=None,
            metadata={"finish_reason": _get_field(response, "choices", 0, "finish_reason")},
        )


def adapter_for(provider: str) -> CaptureAdapter:
    p = provider.lower()
    if p == "anthropic":
        return AnthropicCapture()
    if p == "openai":
        return OpenAICapture()
    if p == "deepseek":
        return DeepSeekCapture()
    if p in {"gemini", "google", "vertex"}:
        return GeminiCapture()
    if p in {"mistral", "magistral"}:
        return MistralCapture()
    raise ValueError(f"unsupported provider {provider!r}")
