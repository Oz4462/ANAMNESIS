# ANAMNESIS

Pre-alpha. Licensed under Apache-2.0 as part of the TRUST-OS unified-license architecture.

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

Pre-alpha. Not safe for production. License-wise public-distribution-ready under Apache-2.0.

## Quickstart (internal)

```bash
uv sync --all-packages --extra dev
uv run pytest                                # 373 tests (V0.2.8 baseline: 351 Py + 22 TS)
uv run python examples/01_basic_capture.py
uv run python examples/02_reuse_demo.py
uv run python examples/03_compliance_audit.py
uv run uvicorn anamnesis_server.main:app --reload
```

## License

Apache License 2.0. See [LICENSE](LICENSE).

Re-licensed from All-Rights-Reserved on 2026-05-22 as part of the TRUST-OS unified-license architecture. Copyright 2026 Ozan Küsmez.
