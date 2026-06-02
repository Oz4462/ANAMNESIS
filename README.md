<div align="center">

# 🧠 ANAMNESIS

### Verifiable reasoning-trace memory for LLM agents

**Capture thinking-tokens → distill to atomic steps → reuse via conformal-bounded retrieval → an Ed25519-signed receipt for every reuse.**

[![License](https://img.shields.io/badge/license-Apache--2.0-3da639?style=flat-square)](#license)
[![Tests](https://img.shields.io/badge/tests-367_passing-2ea44f?style=flat-square)](#status)
[![Python](https://img.shields.io/badge/python-3.11+-3776ab?style=flat-square&logo=python&logoColor=white)](#quickstart)
[![Receipts](https://img.shields.io/badge/receipts-Ed25519_DSSE-8a2be2?style=flat-square)](#what-this-is)
[![EU AI Act](https://img.shields.io/badge/maps_to-EU_AI_Act_Art._15_%26_50-1f5fbf?style=flat-square)](#what-this-is)

[What](#what-this-is) · [Layout](#layout) · [Quickstart](#quickstart) · [Status](#status)

</div>

---

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

## Quickstart

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

## 📬 Contact

Questions, collaboration, or inquiries: **Ozan Küsmez** — <ozan.kuesmez@outlook.com>
