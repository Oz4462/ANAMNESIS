# Architecture

## Five-layer pipeline

```
   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │  CAPTURE    │ → │  DISTILL    │ → │   INDEX     │
   └─────────────┘   └─────────────┘   └─────────────┘
        ↑                                    ↓
   ┌─────────────┐                    ┌─────────────┐
   │  RECEIPT    │ ←─────────────── │RETRIEVE+    │
   │  (Ed25519)  │                    │  COMPOSE    │
   └─────────────┘                    └─────────────┘
```

### CAPTURE (`anamnesis.capture`)

Provider-agnostic wrappers around Anthropic, OpenAI, and DeepSeek responses.
Each adapter implements the `CaptureAdapter` protocol and emits a `CapturedTrace`
with the same shape regardless of how the underlying SDK surfaces the thinking
tokens.

### DISTILL (`anamnesis.distill`)

Splits a `CapturedTrace.thinking_text` into atomic `ReasoningStep`s. Two backends:

- `HeuristicDistiller` — deterministic sentence/bullet split, no LLM.
- `LLMDistiller` — calls a configured callable with the versioned prompt
  template `DISTILL_PROMPT_TEMPLATE`, parses the JSON-array response.

### INDEX (`anamnesis.storage`)

`TraceStore` keeps trace + step metadata in sqlite (`:memory:` for tests, a
file path for persistence) and step embeddings in an in-process numpy matrix.
Embedders are plug-in callables; `hash_embedder` is the deterministic
test-friendly default.

### RETRIEVE + COMPOSE (`anamnesis.retrieve`, `anamnesis.compose`)

`ConformalRetriever` pulls the k-nearest steps and filters by a split-conformal
threshold (see `CONFORMAL_THEORY.md`). `compose()` turns the retained
candidates into a deterministic system-prompt fragment that the caller splices
into their downstream reasoning call.

### RECEIPT (`anamnesis.receipts`)

Each accepted reuse decision is wrapped in a DSSE-shaped envelope signed with
Ed25519 (via PyNaCl). Receipts carry `(tau, alpha, n_calibration)` plus the
retrieved step ids plus the EU AI Act compliance claims. See
`EU_AI_ACT_MAPPING.md` for clause-by-clause evidence mapping.

## Server (`anamnesis_server`)

A FastAPI app exposes the SDK over HTTP. Per-tenant `TraceStore`s and
`ConformalCalibrator`s live in a `TenantRegistry` on `app.state`. The MVP
keeps everything in-process; production deployments swap in shared
sqlite/postgres + redis for the calibrators.

Endpoints:

| Method | Path                              | Purpose                       |
|--------|-----------------------------------|-------------------------------|
| GET    | /health                           | Liveness                      |
| GET    | /v1/compliance/eu_ai_act          | Static clause matrix          |
| GET    | /v1/calibration/{tenant_id}       | Calibrator status             |
| POST   | /v1/calibration                   | Append a fresh-vs-retrieved score |
| POST   | /v1/captures                      | Persist trace + distil steps  |
| POST   | /v1/reuse                         | Retrieve + compose + sign receipt |

## Data shapes

- `CapturedTrace` — frozen, slotted; `content_hash` is sha256 of provider, model,
  thinking, answer joined by NUL bytes.
- `ReasoningStep` — frozen, slotted; ids are `step_<16-hex>`; tuples for collections.
- `ReuseBound` — frozen; `(tau, alpha, n_calibration, score_name)`.
- `Receipt` — mutable so `issued_at` and `receipt_id` can be set deterministically
  in tests; serialised payload is sorted-key compact JSON; PAE wraps it before signing.

## Threading / IO

`TraceStore` opens its sqlite connection with `check_same_thread=False` and
serialises mutating operations with a `threading.RLock`. This is the FastAPI
sync-endpoint pattern; switch to aiosqlite if you go fully async.
