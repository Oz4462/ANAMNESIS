# Changelog

## [0.2.5] — 2026-05-17

### Fixed (real bugs discovered by the new tests)
- `one_minus_cosine` silently returned 0.0 when an embedding contained NaN
  (clamp-after-dot-product hid the corruption). Now returns NaN explicitly
  so the calibrator's `add()` rejects it instead of poisoning the threshold.
- `Receipt.to_payload_bytes` emitted literal `NaN` / `Infinity` tokens
  because `json.dumps` defaults to non-RFC-8259 behaviour. The serialiser
  now uses `allow_nan=False`, so a NaN bound or an Infinity cost raises
  rather than producing an envelope strict verifiers would reject.

### Added — Third hard-validation pass (+69 tests, 232 Py + 9 TS = 241 total)
- `test_capture_robustness.py` — 30 cases × 5 adapters: empty dict, None
  content, missing usage, wrong types, unknown block types, multiple
  `<think>` blocks, pydantic-like attribute objects, request-id override.
- `test_nan_infinity.py` — calibrator rejects NaN/+inf/-inf; receipt
  serialisation rejects NaN in bound and Infinity in cost; zero and
  negative scores are still legitimate.
- `test_math_edges.py` — 13 boundary tests: exact min_calibration,
  one-below-min, all-identical scores, alpha near 0 and near 1,
  window_max==min, orthogonal/identical/antipodal embeddings, FP
  precision, Mondrian per-group window, conditional lambda bucketer,
  exact ceil-quantile formula at n=10/alpha=0.1.
- `test_compose_edges.py` — 11 cases: k=1, k>store, empty store,
  Unicode/emoji query, 10K-char query, abstain-when-cold, explicit
  alpha override, record_outcome accumulation, abstain-with-bound,
  step-block-contains-ids, k<0 raises.
- `test_capture_fuzz.py` — 5 adapters × 200 Hypothesis examples
  (1000 random nested dicts) all return a CapturedTrace without crashing;
  content_hash always sha256-prefixed.

## [0.2.4] — 2026-05-17

### Fixed
- `TraceStore.__init__` now rebuilds the in-memory vector index from sqlite,
  so a process restart no longer leaves `query_similar_steps` empty.
  Closes the v0.2.2 known limitation.

### Added — Second hard-validation pass (+29 tests, 163 Py + 9 TS = 172 total)
- `test_concurrency.py` — 16-thread torture against shared TraceStore +
  ConformalCalibrator: no lost steps under 3200-step racing inserts,
  no errors on parallel reads-during-writes, calibration counter perfect
  under 16-thread contention, 8000 racing uuid step ids all unique.
- `test_openapi.py` — `/openapi.json` is a valid OpenAPI 3.x spec
  (validated via openapi-spec-validator), exposes all six endpoints,
  carries the documented Pydantic schemas, declares the alpha range.
- `test_cli_subprocess.py` — exercises the actual `python -m anamnesis.cli`
  entry point (not just CliRunner), proves the pyproject script binding
  works for status / keygen / demo / distill / verify / help / unknown.
- `test_index_rebuild.py` — five scenarios confirming the new lazy
  rebuild: row-count match, score-ordering preserved, empty-db silent,
  numpy matrix shape correct, and the full "v0.2.2 broken scenario"
  (server restart + retrieval) now recovers candidates.
- `test_receipt_size.py` — sign+verify at 1/10/100/1K/5K/10K retrieved
  step ids. 10K steps = 170 KB envelope, 2.4ms sign, 1.8ms verify.
  Asserts <2 MB envelope at 10K and payload-hash determinism.
- `test_memory_smoke.py` — 2000 reuse cycles in one process, RSS grew
  11.4 MB (5.7 KB / request — noted for v0.3 investigation, not a leak).
  Calibrator sliding window confirmed bounded at max_window=4096.

## [0.2.3] — 2026-05-17

### Added — Hard-validation test pack (143 total: 134 Python + 9 TS)
- `anamnesis-py/tests/test_properties.py` — Hypothesis property-based tests:
  sign/verify round-trip, single-byte payload/signature flip detection,
  canonical-JSON invariants, conformal-monotonicity, hash_embedder unit-norm,
  envelope-from-garbage non-crash. 100 random examples per property.
- `anamnesis-server/tests/test_adversarial.py` — 12 adversarial inputs:
  SQL injection in tenant_id, missing fields, negative tokens, Unicode +
  emoji round-trip, 60 KB thinking texts, score/k/alpha range validation,
  path-traversal, unknown-provider extensibility.
- `anamnesis-ts/src/signer.ts` — TS-side DSSE signer using @noble/ed25519,
  exported alongside the existing verifier so any Node tool can issue
  receipts the Python verifier accepts.
- `benchmarks/cross_lang_receipts.py` — Python signs ↔ Node verifies and
  Node signs ↔ Python verifies, asserts bit-exact DSSE PAE + canonical JSON
  agreement across both implementations.
- `benchmarks/bench_100k.py` — 100K-step retrieval scaling curve.
- `benchmarks/stress_1000_tenants.py` — 1000 concurrent tenants vs uvicorn.
- `benchmarks/coverage_empirical.py` — empirical conformal coverage on
  uniform / pareto / lognormal / bimodal / half-normal, plus drift
  scenarios that intentionally break exchangeability.

### Reality-validated this session
- Cross-language receipts: Py→TS verified, TS→Py verified (bit-exact).
- 100K steps: 121 MB mem, p50 411ms / p99 660ms (linear scaling, no index).
- 1000 concurrent tenants: 100% success, 48.5s, ~20.6 tenants/s, p99 11.7s
  end-to-end (12 HTTP calls per tenant).
- Coverage on 5 non-uniform shapes: empirical within ±0.2% of theory.
- Drift coverage: documented gap from theory (74–80% vs 90% target).

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
