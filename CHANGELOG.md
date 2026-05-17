# Changelog

## [0.2.2] — 2026-05-17

### Added — Reality-validation pass
- `anamnesis_server.main.TenantRegistry` learns a `db_root` parameter and
  honours `ANAMNESIS_DB_ROOT` env var to persist per-tenant sqlite files.
- `_signer_from_env_or_random` recovers a deterministic Ed25519 issuer from
  `ANAMNESIS_SIGNING_SEED_B64` + `ANAMNESIS_SIGNING_KEYID` so receipts
  issued before a server restart still verify against the restored pubkey.
- `benchmarks/bench_10k.py` — insert + retrieval performance test on 10K steps.
- `benchmarks/multi_tenant_load.py` — async httpx load test, 20 tenants
  parallel, asserts calibration isolation + receipt issuance.
- `benchmarks/persistence_test.py` — boots two sequential uvicorn processes
  with shared env, verifies sqlite rows + pre-restart receipts survive.

### Reality-validated
- 10K traces: 12 MB memory, p50 14.6 ms / p95 18.6 ms / p99 40 ms retrieval.
- Multi-tenant: 20 tenants in 2.39 s, 0 failures, 8.4 tenants/sec (~343 HTTP RPS).
- Sqlite persistence over hard restart: 5 traces + 10 steps survive,
  pre-restart receipt still verifies (deterministic signer via env).
- In-browser receipt verifier (`anamnesis-web/src/pages/receipts.astro`):
  Playwright/Chromium loaded, Python-signed envelope verified, tamper
  detection produced "FAILED" as expected.

### Known limitation
- Numpy vector index lives in-process; after restart `query_similar_steps`
  is empty until the index is rebuilt from sqlite rows. Fix is queued
  for v0.3.

## [0.2.1] — 2026-05-17

### Fixed
- Ruff cleanups (29 violations) so CI passes on Ubuntu Python 3.11/3.12/3.13.
- `.dockerignore` no longer hides `README.md` (pyproject references it).

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
