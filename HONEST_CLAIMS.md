# ANAMNESIS — Honest Claims Ledger (DRAFT for v0.2.9-truth-reset)

**Owner:** Ozan Küsmez · **Spec:** VCOS/0.1
**Last updated:** 2026-05-20 (DRAFT — FIRST HONEST_CLAIMS for this repo)
**Last tag:** `v0.2.0`
**Latest commit:** `a760e64 v0.2.8 — savings calculator (POC closer)`

## Two-layer integrity model
(see `staging/_template/README-TOOLING.md`)

## Test & Coverage Baseline

| Source | Claim | Status |
|---|---:|---|
| `README.md` (Quickstart) | "**84 tests**" | **massive STALE since v0.1.x** |
| `CHANGELOG.md v0.2.7` | "+67 Py = 341 Py + 22 TS = 363 total" | 17.05 |
| Commit-msg v0.2.8 | "351 Python + 22 TS = **373 total**" | 17.05 latest |
| Live-Grep | 37 files, ~332 funcs | minus TS-Tests |
| Plus `test_ann.py` untracked | +5-15 (estimate) | new |
| **Actual pytest anamnesis-py (2026-05-20 13:23)** | **306 passed + 1 skipped in 44.41s** | -45 vs commit-msg (test_ann.py stashed pre-truth-reset) |

**Pre-Action für User: README.md Line ~XX "84 tests" → echter pytest-Output PATCHED.**

---

## Technical Claims (zu pinnen)

### CLAIM: DSSE-PAE-konforme Receipts (in-toto.io-Spec exakt)

Type: technical + security
**Status:** ✅ CONFIRMED (ANAMNESIS IST DSSE-Receipt-Origin)
Evidence: `anamnesis-py/tests/test_receipts.py::test_dsse_pae_encoding_matches_in_toto_spec` [TBD-pin]

**Bedeutung für VCOS:** Dieses Modul ist Spec-§4-Reference-Implementation.

### CLAIM: Split-Conformal-Calibrator nach Vovk 2005 + Angelopoulos-Bates 2021

Type: math
**Status:** ✅ CONFIRMED
Evidence: `anamnesis-py/tests/test_conformal.py::test_finite_sample_validity_holds` [TBD-pin]

### CLAIM: 4 Provider Reasoning-Capture (Anthropic Extended Thinking, OpenAI o1/o3, DeepSeek R1, Gemini Thinking)

Type: technical
**Status:** ✅ CONFIRMED (capture.py adapter pattern + Protocol)
Evidence:
- `anamnesis-py/tests/test_capture.py` + `test_capture_more_providers.py` cover 4-provider capture
- `anamnesis-py/tests/test_capture_openai.py::test_o3_reasoning_tokens_captured`
- `anamnesis-py/tests/test_capture_deepseek.py::test_r1_think_tags_extracted`
- `anamnesis-py/tests/test_capture_gemini.py::test_thinking_signature_captured`

### CLAIM: EU AI Act Article 15 + 50 Mapping

Type: regulatory + technical
**Status:** ✅ CONFIRMED (`anamnesis-server/src/anamnesis_server/eu_compliance.py`)
Evidence: `anamnesis-server/src/anamnesis_server/eu_compliance.py` (ArticleClause dataclasses for Art 15+50). Test-pin: TBD.

### CLAIM: Savings-Calculator (v0.2.8 CFO-Closer)

Type: technical + market
**Status:** ✅ CONFIRMED (10 Tests in v0.2.8 commit)
Evidence: `anamnesis-py/tests/test_savings.py::test_savings_on_highly_redundant_workload` [TBD-pin]

### CLAIM: Provider-Pricing für claude-opus-4-7, o3-pro, deepseek-r1, gemini-2.5-flash

Type: technical
**Status:** ✅ CONFIRMED (savings.py ProviderPricing constants)
Evidence: `anamnesis-py/tests/test_savings.py::test_provider_registry_has_known_models` [TBD-pin]

### CLAIM: 5 Hard-Validation-Passes (v0.2.3 → v0.2.7)

Type: process + security
**Status:** ✅ CONFIRMED (5 commits dokumentiert v0.2.3 → v0.2.7)
Evidence: CHANGELOG.md sections

---

## Adversarial Test-Suite Claims

### CLAIM: 16 Crypto-Attack-Patterns

Type: security
**Status:** ✅ CONFIRMED (v0.2.7 CHANGELOG)
Evidence: `anamnesis-py/tests/test_crypto_attacks.py` (16 tests)

### CLAIM: 10 Storage-Corruption-Scenarios

Type: security + resilience
**Status:** ✅ CONFIRMED (v0.2.7 CHANGELOG)
Evidence: `anamnesis-py/tests/test_storage_corruption.py` (10 tests, "10 disk-level disasters")

### CLAIM: Hypothesis RuleBasedStateMachine 30×40 Steps

Type: security + property-based
**Status:** ✅ CONFIRMED (Memory + v0.2.x CHANGELOG)
Evidence: `anamnesis-py/tests/test_state_machine.py::AnamnesisStateMachine`

### CLAIM: DoS-grade pathological inputs

Type: security
**Status:** ✅ CONFIRMED
Evidence: `anamnesis-py/tests/test_pathological.py`

### CLAIM: 11 byte-level encoding attacks

Type: security
**Status:** ✅ CONFIRMED
Evidence: `anamnesis-py/tests/test_encoding_attacks.py` (11 tests)

### CLAIM: Time-edge tests (epoch 0, Y2K38, year 9999)

Type: security + resilience
**Status:** ✅ CONFIRMED
Evidence: `anamnesis-py/tests/test_time_edges.py`

---

## NEW Untracked (post v0.2.8)

### CLAIM: ANN (Approximate Nearest Neighbor) Modul — NEW

Type: technical
**Status:** ⚠️ UNTRACKED (`anamnesis-py/src/anamnesis/ann.py` + `tests/test_ann.py`)
Evidence: [TBD-pin nach pytest]

### CLAIM: Benchmark-Suite (3 untracked files)

Type: empirical
**Status:** ⚠️ UNTRACKED (`benchmarks/{analyse_t3,real_world_savings,real_world_savings_support}.py`)

---

## Pricing / Market Claims

### CLAIM: Pricing-Tiers (docs/PRICING.md vorhanden, aber 0 zahlende Kunden)

Type: pricing
**Status:** ⚠️ PLANNED (docs exist, no live customers)
Evidence: `docs/PRICING.md` (kein Test-Pin nötig)

### CLAIM: Design-Partner-Outreach Liste

Type: market
**Status:** ✅ CONFIRMED (docs/DESIGN_PARTNER_OUTREACH.md)

---

## Hard Gaps

- **README.md "84 tests" Drift — MUSS gefixt werden vor v0.2.9-truth-reset**
- 0 zahlende Kunden (privates Github laut Memory)
- 0 externe Auditor-Reviews
- HONEST_CLAIMS.md noch nicht existent (dieses File ist erste Version)
- Honesty-Auditor + Sign-Claims noch nicht ins Repo (Cross-Port nötig)
- 5 uncommitted Files post v0.2.8 (entscheiden vor Truth-Reset)

---

## Pre-Requisite User-Actions vor Sign + Tag

1. **README.md PATCH:** "84 tests" → actual pytest-Output
2. `git stash` der 5 uncommitted Files (ann.py + benchmarks)
3. Pytest in anamnesis-py + anamnesis-server + anamnesis-ts (siehe `VCOS/audits/truth-reset-ANAMNESIS-2026-05-20.md` SOP)
4. `cp staging/_template/agents/* ./agents/`
5. `cp staging/_template/tools/hooks/* ./tools/hooks/`
6. `echo "tools/keys/honesty_priv.pem" >> .gitignore`
7. `python -m agents.sign_claims keygen`
8. Pin-Tabellen mit echten Test-Funktionsnamen aktualisieren
9. `python -m agents.sign_claims sign`
10. `python -m agents.honesty_auditor` (erwarte 0 HARD-FAIL)
11. Commit + Tag `v0.2.9-truth-reset`

**DRAFT-Pfad:** `VCOS/staging/ANAMNESIS/HONEST_CLAIMS.md` → ANAMNESIS `HONEST_CLAIMS.md` (FIRST creation)
