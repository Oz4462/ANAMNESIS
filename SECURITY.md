<!--
SPDX-License-Identifier: Apache-2.0
Copyright 2026 Ozan Küsmez
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
See LICENSE for the full text.
-->

# Security Policy — ANAMNESIS

ANAMNESIS implements **EU AI Act Article 15** audit-trail receipts:
DSSE Ed25519 signed reasoning-trace envelopes with SHA-256 hash-chained
provenance, plus a conformal-prediction layer that exposes calibrated
abstention bounds for downstream policy enforcement.

Because the receipts are intended to serve as evidence in regulatory
audits and downstream HITL escalation, **tampering with reasoning traces
or conformal bounds is the principal threat-class** this policy covers.

## Supported Versions

| Version | Supported |
|---|---|
| 0.1.x   | yes |
| < 0.1   | no  |

## Reporting a Vulnerability

Email **ozan.kuesmez@outlook.com** with subject `[SECURITY] ANAMNESIS`.

Do **not** open a public GitHub issue, public discussion thread, or
social-media post before the embargo window has elapsed.

**PGP / OpenPGP encryption:** PGP-Key TBD post-Pre-Seed. Until a key is
published here, send reports unencrypted to the address above; large
PoC payloads or sample reasoning-traces should be shared via 7-zip with
a passphrase exchanged out of band.

### What to include

- Affected version + commit SHA + module (`anamnesis-py/`,
  `anamnesis-server/`, `anamnesis-ts/`, or provider SDK adapter)
- Reproduction steps or proof-of-concept
- Suggested mitigation if known
- Whether the issue affects only signing, only chain-verification, only
  conformal bounds, or multiple layers

### Response SLA

- **Acknowledgment:** within **72 hours** of report receipt
- **Triage + severity classification:** within 7 days
- **Maximum fix window:** **90 days** from triage
- **Embargo period:** **30-day responsible-disclosure window** from the
  patch landing on `main` before public technical details are published.
  CVE coordination for High / Critical severity.
- Credit in `CHANGELOG.md` and project Hall-of-Fame (see below) unless
  the reporter requests anonymity.

## Bug Bounty

ANAMNESIS is **pre-revenue**. **No monetary bounty is offered at this
time.**

In place of payment, valid reports receive:

- Public acknowledgment in `CHANGELOG.md` under the relevant release
- Listing in the project Hall-of-Fame (planned: `docs/security/HALL-OF-FAME.md`)
- Optional reference letter for the disclosure
- Right of first refusal on bounty payouts once a paid programme launches

## Threat Surface

ANAMNESIS sits between an LLM provider (Anthropic / OpenAI / DeepSeek /
Ollama) and a downstream policy enforcer. The receipt is the only durable
artefact, so:

- **Reasoning-trace tampering** — modification of recorded `messages`,
  `tool_calls`, or `thinking` blocks after signing
- **Receipt-chain forgery** — substitution or reorder of `prev_hash`
  links across the SHA-256 chain
- **Conformal-prediction attacks** — crafted inputs that push the
  predictor outside its calibration distribution to produce
  artificially-tight or artificially-wide bounds, bypassing abstention
  or forcing spurious abstention
- **Provider-SDK adapter injection** — payloads that exploit
  multi-provider normalisation in the Anthropic / OpenAI / DeepSeek
  adapters

## Cryptographic Primitives

- **Ed25519 (RFC 8032)** via PyNaCl / libsodium for DSSE envelope
  signing of every receipt.
- **SHA-256 (NIST FIPS 180-4)** for receipt-chain hash-linking; each
  `entry_hash = sha256(prev_hash || canonical(payload))`.
- **F19 KeyStore** (commit `8564e4c`): monotonic `key_generation`
  counters; key-rotation never decreases generation, and `verify_chain`
  rejects rollback.
- **Conformal prediction** (Vovk-Gammerman-Shafer): split-conformal
  intervals with calibrated coverage, MAPIE-compatible.

## In Scope

- Receipt-signing key compromise paths (including disk-leak / env-leak)
- Receipt-chain tampering, reorder, deletion, or rollback
- Reasoning-trace post-hoc modification undetected by `verify_chain`
- DSSE-PAE type-confusion across the multi-provider adapter surface
- Conformal-bound bypass via crafted inputs (in-distribution / OOD)
- Multi-provider SDK injection paths (Anthropic / OpenAI / DeepSeek)
- F19 KeyStore monotonicity bypass / rollback paths

## Out of Scope

- **Social engineering** against the maintainer, contributors, or any
  downstream user.
- **Physical access** to the maintainer's workstation or to any
  deployed ANAMNESIS server.
- **Denial-of-service (DDoS)** against public endpoints, GitHub
  infrastructure, or shared CI.
- Vulnerabilities in upstream LLM providers (Anthropic, OpenAI,
  DeepSeek, Ollama) — report upstream.
- Vulnerabilities in the underlying cryptographic primitives themselves
  (Ed25519, SHA-256, libsodium) — report to NIST / IETF / libsodium
  maintainers.
- Operator-side host compromise outside the ANAMNESIS process.

## Standards References

- **EU AI Act, Article 15** — Accuracy, robustness, and cybersecurity
  requirements for high-risk AI systems
- **EU AI Act, Article 12** — Record-keeping and automatic logging
- **RFC 8032** — Ed25519 / EdDSA signature scheme
- **NIST FIPS 180-4** — SHA-256 secure hash standard
- **DSSE v1.0.2** — Dead Simple Signing Envelope:
  <https://github.com/secure-systems-lab/dsse>
- **NIST SP 800-218** — Secure Software Development Framework (SSDF v1.1)
- Vovk, Gammerman & Shafer (2005) — "Algorithmic Learning in a Random
  World" (conformal prediction foundations)
- Angelopoulos & Bates (2023) — "Conformal Prediction: A Gentle
  Introduction"

## Cross-Repo References

- TRUST-OS Threat-Model (STRIDE):
  `../TRUST-OS/docs/security/2026-05-22-threat-model-stride.md`
- F19 KeyStore Spec:
  `../TRUST-OS/docs/specs/2026-05-22-key-rotation-interface.md`
- F20 verify_chain Spec:
  `../TRUST-OS/docs/specs/2026-05-22-verify-chain-interface.md`
- Cross-Repo Security Sweep:
  `../TRUST-OS/docs/security/2026-05-22-cross-repo-security-sweep.md`
