# Changelog

## [0.2.8] — 2026-05-17

### Added — Savings Calculator (the POC closer)
- `anamnesis.savings` module: offline simulator that takes a JSONL transcript
  of (query, thinking_tokens, output_tokens) triples and reports
    * reuse rate, savings rate, dollar value at provider rates
    * conformal bound (tau, alpha, n_calibration) used to decide reuse
  No LLM calls, no API keys, runs entirely on the prospect's machine
  against their own workload.
- `ProviderPricing` constants for claude-opus-4-7, o3-pro, deepseek-r1,
  gemini-2.5-flash with thinking-token rates from public pricing pages.
- `anamnesis savings` CLI subcommand wired to `--from-file`, `--provider`,
  `--alpha`, `--min-calibration`.
- `examples/04_savings_demo.py` — runs the simulator across all four
  providers on a synthetic 110-query workload, prints per-provider $$$.
- `test_savings.py` — 10 tests: redundant workload yields high reuse,
  diverse workload yields low reuse, dollar math exact, JSONL load
  round trip, empty lines tolerated, invalid lines raise with line
  number, registry has known models, zero-token rows handled.

### Why this matters for a prospect call
- The pitch "we save 40-70% of your reasoning tokens" is unverifiable
  until you point it at a real workload. This module produces the
  per-workload number a CFO can sign off on.
- No need to hand us an API key or a dataset -- the simulator can run
  inside the customer's VPC against their JSONL transcript.

## [0.2.7] — 2026-05-17

### Added — Fifth hard-validation pass (HARD tests, +67 Py = 341 Py + 22 TS = 363 total)
- `test_crypto_attacks.py` — 16 adversarial crypto patterns: all-zero
  pubkey, signature truncation to 0/32/128 bytes, key substitution with
  attacker pubkey, PAE length-prefix confusion, payloadType swap, random
  garbage sig, two-bad-sigs replay, mixed valid/invalid sigs (one wins),
  missing keyid, extra base64 padding, non-canonical JSON, empty keyset.
- `test_storage_corruption.py` — 10 disk-level disasters: truncated db,
  random bytes for file, empty file = fresh schema, exotic UTF-8 round
  trip (RTL, emoji ZWJ, umlauts), embedded NUL byte, concurrent writers
  no corruption, forward-schema with extra column readable by old client,
  nonexistent directory raises, read-only file raises on write, path-
  traversal step_id stored safely.
- `test_state_machine.py` — Hypothesis RuleBasedStateMachine: 30 random
  pipeline traces × 40 steps each = ~1200 random interleavings of add_trace
  / add_step / add_calibration / query / sign_receipt with 5 invariants
  checked after every step.
- `test_pathological.py` — 9 DoS-grade inputs: 100K retrieved_step_ids
  sign+verify each under 1.5s, 1 MB thinking_text round trip, 100K
  calibration writes cap at max_window, 10K-step query under 500ms,
  empty-text step indexed, 500 KB single-step text, 20× repeated signing
  of large receipts (10K + 50K), 1000 independent concurrent calibrators.
- `test_encoding_attacks.py` — 11 byte-level games: BOM-prefixed payload
  breaks signature, trailing whitespace breaks signature, url-safe alphabet
  swap rejected, lone surrogate raises UnicodeEncodeError on content_hash,
  API rejects raw invalid-UTF8 body, payload_type with extra space
  rejected, internal b64 whitespace tolerated as wire variation
  (documented), forward-compatible extra envelope fields accepted, full
  Unicode + Chinese + emoji round trip.
- `test_time_edges.py` — 20 timestamp edges: epoch 0, Y2K38, year 9999,
  year 99999, BC year, DST boundary, naive datetime, microseconds, Z
  suffix, ±14h timezone, timezone with seconds offset, default is UTC,
  default is strictly increasing under sleep.

## [0.2.6] — 2026-05-17

### Added — Fourth hard-validation pass (+55 tests, 274 Py + 22 TS = 296 total)
- `test_determinism.py` — 9 byte-exactness tests: canonical payload bytes
  identical for identical receipts, Ed25519 signatures bit-stable for the
  same seed + message, signature changes when ONE field differs, top-level
  keys alphabetically sorted in the encoded JSON, hash_embedder byte-stable.
- `test_idempotency_replay.py` — 6 server-level cases documenting that
  /v1/captures is NOT idempotent on request_id (intentional for MVP) and
  that receipt verification IS idempotent: replay yields identical
  recovered payload, tampered receipt fails consistently on both attempts,
  cross-tenant trace_ids never collide.
- `test_http_middleware.py` — 13 HTTP-layer tests: content-type negotiation,
  invalid JSON returns 422 not 500, 405 method-not-allowed, large 50 KB
  body accepted, gzip-encoded body handled without 5xx, /docs and /redoc
  render HTML, no stack-traces leaked on error paths.
- `test_storage_cross_instance.py` — 7 cases: two TraceStores on the same
  db file see the same rows, embedder dimension change between sessions
  doesn't crash retrieval, close releases the handle for outside sqlite,
  in-memory stores stay isolated, metadata persists.
- `test_receipt_chain.py` — 6 evidence-chain cases: three signed receipts
  forming a chain all verify, chain_prev tampering breaks verification,
  receipts arrive in temporal order, byte-identical replay after JSON
  round-trip, two-signer chains require both pubkeys, chain bytes scale
  linearly (no hidden quadratic).
- `anamnesis-ts/test/signer.test.ts` — +13 TS tests (9 → 22 total): key
  generation, seed round-trip, sign+verify, deterministic-signature
  property, payload-type / keyid / signature-array failure modes,
  canonical-payload byte stability across calls, PAE determinism.

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
