# Changelog

## [0.2.0] — 2026-05-17

### Added — Phase 2 (autonomous build extension)
- `fastembed_embedder` + `embedder_for` factory: real ONNX sentence embeddings (BAAI/bge-small-en-v1.5) with graceful hash-embedder fallback.
- `AnthropicHaikuDistiller` + `distiller_for`: production LLM distiller with mocked tests; falls back to heuristic on any vendor error.
- `GeminiCapture` + `MistralCapture`: capture adapters for Gemini 2.5 thinking and Magistral / Mistral reasoning (`<think>` tag + `reasoning` field).
- `ConditionalConformalCalibrator`: per-bucket conformal thresholds for per-slice coverage; bucket function is user-supplied.
- `anamnesis` Click-based CLI: `status`, `keygen`, `verify`, `distill`, `demo`.
- `Dockerfile` + `.dockerignore` for the FastAPI server (multi-stage uv-based, healthcheck, 2 workers).
- `.github/workflows/ci.yml`: matrix tests py3.11/3.12/3.13, ruff, docker build (no push).
- `anamnesis-ts/` TypeScript SDK: HTTP client + standalone Ed25519 DSSE verifier (@noble/ed25519), 9 vitest cases, tsup build to ESM + CJS + d.ts.
- `anamnesis-web/` Astro + Tailwind internal dashboard: overview, architecture, EU AI Act mapping, tenants stub, in-browser receipt verifier wired to the TS SDK.

### Test count
- Python: 115 passed, 1 skipped (fastembed-missing path)
- TypeScript: 9 passed
- Astro: 5 static pages built clean

## [0.1.0] — 2026-05-17

### Added
- Initial repo scaffold (anamnesis-py SDK, anamnesis-server FastAPI)
- Workspace pyproject.toml with ruff + mypy strict + pytest config
- Internal README, proprietary LICENSE, comprehensive .gitignore
- Conformal calibrator (split + mondrian), receipts (Ed25519 DSSE), capture adapters (Anthropic/OpenAI/DeepSeek), heuristic + LLM distiller protocol, sqlite + numpy storage, conformal retriever, prompt composer, FastAPI server with EU AI Act mapping.
- 84/84 tests green.
