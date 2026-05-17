# ANAMNESIS

Internal project. Not for public distribution.

## What this is

A Python SDK + FastAPI server that captures thinking-tokens from reasoning
LLMs (Claude Extended Thinking, OpenAI o1/o3, DeepSeek R1, Gemini Thinking),
distills them into atomic reasoning steps, indexes them, and reuses them via
conformal-bounded retrieval for semantically-similar future queries.

Every reuse decision is wrapped in an Ed25519-signed DSSE receipt that
satisfies EU AI Act Article 15 (logging) and Article 50 (transparency).

## Layout

```
anamnesis-py/         Python SDK (capture, distill, retrieve, compose, receipts)
anamnesis-server/     FastAPI backend (storage, conformal calibration, billing)
docs/                 Internal architecture, EU-AI-Act mapping, conformal theory
examples/             Notebooks and scripts demonstrating reuse + receipts
```

## Status

Pre-alpha. Not safe for production. Not safe for public release.

## Quickstart (internal)

```bash
uv sync --all-packages --extra dev
uv run pytest                                # 84 tests
uv run python examples/01_basic_capture.py
uv run python examples/02_reuse_demo.py
uv run python examples/03_compliance_audit.py
uv run uvicorn anamnesis_server.main:app --reload
```

## License

All Rights Reserved. See LICENSE.
