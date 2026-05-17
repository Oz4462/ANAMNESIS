"""Distill captured reasoning traces into atomic, retrievable steps.

Distillation is the bridge from a raw stream of thinking-tokens to a set of
indexed units the retrieve+compose layer can splice into new prompts.

We define an Distiller protocol so callers can plug in:

    * HeuristicDistiller -- deterministic sentence-paragraph segmentation, no
      LLM, used in tests and as a free baseline,
    * LLMDistiller -- calls a cheap reasoning-distilled model (e.g.
      claude-haiku-4-5) to produce structured JSON steps with intent and
      preconditions, used in production.

Both yield ReasoningStep instances. The LLM prompt is exposed as a constant so
the same template can be A/B-tested and version-pinned in receipts.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

from anamnesis.capture import CapturedTrace
from anamnesis.storage import ReasoningStep

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\?!])\s+(?=\S)|\n+")
_BULLET_RE = re.compile(r"^\s*(?:\d+[\.\)]|[-*•])\s+", re.MULTILINE)
_THINKING_PLACEHOLDER = "<<<THINKING_TRACE>>>"


DISTILL_PROMPT_VERSION = "anamnesis-distill-v1"

DISTILL_PROMPT_TEMPLATE = (
    "You are a reasoning-trace distiller for an audit-grade memory system.\n"
    "Read the THINKING TRACE below and split it into atomic reasoning steps.\n\n"
    "Each step MUST have:\n"
    "    - intent: one sentence describing what the step accomplishes\n"
    "    - text: verbatim quoted span of the trace that contains the step\n"
    "    - preconditions: list of facts/state required before this step (may be empty)\n"
    "    - produces: list of facts/conclusions this step generates (may be empty)\n"
    "    - tags: 1 to 3 short topical tags\n\n"
    "Return ONE JSON array, no prose, no markdown fences. Each element is an object\n"
    "with keys: intent (string), text (string), preconditions (list of strings),\n"
    "produces (list of strings), tags (list of strings).\n\n"
    "THINKING TRACE:\n"
    + _THINKING_PLACEHOLDER
    + "\n"
)


def render_distill_prompt(thinking: str) -> str:
    return DISTILL_PROMPT_TEMPLATE.replace(_THINKING_PLACEHOLDER, thinking)


class Distiller(Protocol):
    name: str

    def distill(self, trace: CapturedTrace) -> list[ReasoningStep]: ...


@dataclass(slots=True)
class HeuristicDistiller:
    """Split on bullets, double-newlines, and sentence boundaries.

    Useful as a deterministic baseline, for tests, and as a fallback when no
    LLM is configured. Produces one step per sentence-ish chunk with a
    trivially derived intent (first 80 characters).
    """

    name: str = "heuristic-v1"
    min_step_chars: int = 24

    def distill(self, trace: CapturedTrace) -> list[ReasoningStep]:
        if not trace.thinking_text.strip():
            return []
        text = _BULLET_RE.sub("", trace.thinking_text).strip()
        raw_chunks = _SENTENCE_SPLIT_RE.split(text)

        steps: list[ReasoningStep] = []
        for chunk in raw_chunks:
            cleaned = chunk.strip()
            if len(cleaned) < self.min_step_chars:
                continue
            intent = cleaned[:80].strip()
            steps.append(
                ReasoningStep.make(
                    capture_id=trace.request_id,
                    text=cleaned,
                    intent=intent,
                    preconditions=(),
                    produces=(),
                    tags=(trace.provider, trace.model),
                )
            )
        return steps


@dataclass(slots=True)
class LLMDistiller:
    """Delegate distillation to a cheap LLM and parse its JSON response.

    `llm` is any callable that takes a prompt string and returns a string
    response. Keeping the interface minimal lets the caller wire in any
    provider SDK (anthropic, openai, ollama, local llama-cpp) without
    coupling this module to a vendor.
    """

    llm: Callable[[str], str]
    name: str = "llm-distill-v1"
    prompt_version: str = DISTILL_PROMPT_VERSION

    def distill(self, trace: CapturedTrace) -> list[ReasoningStep]:
        if not trace.thinking_text.strip():
            return []
        prompt = render_distill_prompt(trace.thinking_text)
        raw = self.llm(prompt)
        items = _parse_distilled_json(raw)
        return [
            ReasoningStep.make(
                capture_id=trace.request_id,
                text=str(item.get("text", "")),
                intent=str(item.get("intent", "")),
                preconditions=tuple(str(x) for x in item.get("preconditions", [])),
                produces=tuple(str(x) for x in item.get("produces", [])),
                tags=tuple(str(x) for x in item.get("tags", [])),
            )
            for item in items
            if str(item.get("text", "")).strip()
        ]


def _parse_distilled_json(text: str) -> list[dict]:
    """Tolerant JSON-array parser that strips markdown fences and prose noise."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"```\s*$", "", s)
        s = s.strip()
    start = s.find("[")
    end = s.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    chunk = s[start : end + 1]
    try:
        data = json.loads(chunk)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def distill_traces(
    distiller: Distiller,
    traces: Iterable[CapturedTrace],
) -> list[ReasoningStep]:
    out: list[ReasoningStep] = []
    for trace in traces:
        out.extend(distiller.distill(trace))
    return out


@dataclass(slots=True)
class AnthropicHaikuDistiller:
    """Production LLM-distiller backed by Anthropic Claude Haiku.

    Lazy-imports the anthropic SDK. Uses ANTHROPIC_API_KEY from the env unless
    a key is passed in. On any vendor error or empty response we fall back
    to the HeuristicDistiller so the pipeline never silently emits zero steps.
    """

    model: str = "claude-3-5-haiku-latest"
    max_tokens: int = 4096
    api_key: str | None = None
    name: str = "anthropic-haiku-distill-v1"
    prompt_version: str = DISTILL_PROMPT_VERSION
    fallback: HeuristicDistiller = field(default_factory=HeuristicDistiller)
    _client: object | None = None

    def _get_client(self) -> object:
        if self._client is not None:
            return self._client
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError as e:
            raise ImportError(
                "anthropic SDK is not installed. Add to your project: "
                "uv pip install anthropic"
            ) from e
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "AnthropicHaikuDistiller requires ANTHROPIC_API_KEY or api_key kwarg."
            )
        self._client = Anthropic(api_key=key)
        return self._client

    def distill(self, trace: CapturedTrace) -> list[ReasoningStep]:
        if not trace.thinking_text.strip():
            return []
        prompt = render_distill_prompt(trace.thinking_text)
        try:
            client = self._get_client()
            resp = client.messages.create(  # type: ignore[attr-defined]
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(
                getattr(block, "text", "") for block in getattr(resp, "content", [])
            )
        except Exception:
            return self.fallback.distill(trace)

        items = _parse_distilled_json(raw)
        steps = [
            ReasoningStep.make(
                capture_id=trace.request_id,
                text=str(item.get("text", "")),
                intent=str(item.get("intent", "")),
                preconditions=tuple(str(x) for x in item.get("preconditions", [])),
                produces=tuple(str(x) for x in item.get("produces", [])),
                tags=tuple(str(x) for x in item.get("tags", [])),
            )
            for item in items
            if str(item.get("text", "")).strip()
        ]
        if not steps:
            return self.fallback.distill(trace)
        return steps


def distiller_for(name: str | None = None, **kwargs) -> Distiller:
    """Factory: pick a distiller by name.

    Names:
        "heuristic"        -> HeuristicDistiller(**kwargs)
        "anthropic-haiku"  -> AnthropicHaikuDistiller(**kwargs)
        None               -> heuristic
    """
    if name is None or name.lower() == "heuristic":
        return HeuristicDistiller(**kwargs)
    n = name.lower()
    if n in {"anthropic-haiku", "haiku", "claude-haiku"}:
        return AnthropicHaikuDistiller(**kwargs)
    raise ValueError(f"unknown distiller {name!r}")
