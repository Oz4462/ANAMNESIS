"""Hypothesis fuzz: capture adapters must never crash on arbitrary nested input.

We generate deeply random dict-of-dict-of-list-of-strings structures and feed
them to every adapter. The contract is: produce a CapturedTrace (with any
fields empty if the data isn't recognisable) and NEVER raise.
"""

from __future__ import annotations

from anamnesis.capture import (
    AnthropicCapture,
    CapturedTrace,
    DeepSeekCapture,
    GeminiCapture,
    MistralCapture,
    OpenAICapture,
)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_FUZZ = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


json_atom = st.one_of(st.none(), st.booleans(), st.integers(-1000, 1000),
                     st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=20))
json_value = st.recursive(
    base=json_atom,
    extend=lambda inner: st.one_of(
        st.lists(inner, max_size=4),
        st.dictionaries(st.text(max_size=12), inner, max_size=4),
    ),
    max_leaves=20,
)


@_FUZZ
@given(payload=st.dictionaries(st.text(max_size=12), json_value, max_size=8))
def test_anthropic_never_crashes_on_random_dict(payload):
    out = AnthropicCapture().extract(payload)
    assert isinstance(out, CapturedTrace)


@_FUZZ
@given(payload=st.dictionaries(st.text(max_size=12), json_value, max_size=8))
def test_openai_never_crashes_on_random_dict(payload):
    out = OpenAICapture().extract(payload)
    assert isinstance(out, CapturedTrace)


@_FUZZ
@given(payload=st.dictionaries(st.text(max_size=12), json_value, max_size=8))
def test_deepseek_never_crashes_on_random_dict(payload):
    out = DeepSeekCapture().extract(payload)
    assert isinstance(out, CapturedTrace)


@_FUZZ
@given(payload=st.dictionaries(st.text(max_size=12), json_value, max_size=8))
def test_gemini_never_crashes_on_random_dict(payload):
    out = GeminiCapture().extract(payload)
    assert isinstance(out, CapturedTrace)


@_FUZZ
@given(payload=st.dictionaries(st.text(max_size=12), json_value, max_size=8))
def test_mistral_never_crashes_on_random_dict(payload):
    out = MistralCapture().extract(payload)
    assert isinstance(out, CapturedTrace)


@_FUZZ
@given(text=st.text(max_size=2000), tokens=st.integers(min_value=0, max_value=10**8))
def test_content_hash_is_always_sha256_prefixed(text, tokens):
    trace = CapturedTrace(
        provider="anthropic",
        model="m",
        request_id="r",
        thinking_text=text,
        answer_text="",
        thinking_tokens=tokens,
        output_tokens=0,
    )
    h = trace.content_hash
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64
