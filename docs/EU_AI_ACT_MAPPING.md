# EU AI Act Compliance Mapping

Mapping of Regulation (EU) 2024/1689 clauses to specific evidence fields in
the ANAMNESIS receipt schema. Every signed receipt carries the data points
listed in the `evidence_fields` column so an auditor can verify each clause
mechanically.

This document is informational. It is **not** legal advice. Operators of
high-risk AI systems must consult their own counsel before claiming
compliance.

## Article 15 — Accuracy, robustness and cybersecurity

| Clause | Summary | Receipt fields |
|--------|---------|----------------|
| 15(1) | Designed and developed to achieve an appropriate level of accuracy, robustness, and cybersecurity throughout their lifecycle. | `bound.tau`, `bound.alpha`, `bound.n_calibration` |
| 15(2) | Levels of accuracy and the relevant accuracy metrics are declared in the accompanying instructions of use. | `bound.score_name`, `bound.alpha` |
| 15(3) | Technical solutions to address AI-specific vulnerabilities, including measures to prevent, detect, respond to, resolve, and control attacks. | `schema_version`, `issued_at`, signed Ed25519 envelope |
| 15(4) | Robust against errors, faults, or inconsistencies. Operates with a consistent performance throughout the lifecycle. | `bound.tau`, `bound.alpha`, `bound.n_calibration` |

### How the bound supplies clause 15(1) and 15(4) evidence

The `(tau, alpha, n_calibration)` triple is a finite-sample, distribution-free
upper bound on the probability that the reuse pipeline emits an answer that
diverges (by `one_minus_cosine` over embeddings) from the model's fresh
answer by more than `tau`. Concretely:

    P[ d(fresh, reused) > tau ]  ≤  alpha   given >= n_calibration samples

This satisfies the wording "appropriate level of accuracy, robustness, and
cybersecurity throughout their lifecycle" because:

1. It is **declared** — the operator publishes `(tau, alpha)` to users.
2. It is **measured** — the calibration log records every observation.
3. It is **preserved through the lifecycle** — the sliding-window calibrator
   adapts when the underlying model changes.

### How the Ed25519 envelope supplies 15(3) evidence

Receipts are signed with Ed25519 using the DSSE pre-authentication encoding.
Any tampering of the payload invalidates the signature. The verifier is the
single source of truth for "did this receipt come from our issuer key".

## Article 50 — Transparency obligations

| Clause | Summary | Receipt fields |
|--------|---------|----------------|
| 50(2) | Outputs of generative AI systems are marked in a machine-readable format, detectable as artificially generated or manipulated. | `capture_hash`, `model.provider`, `model.name` |
| 50(4) | Deployers disclose AI generation/manipulation when content is published with the purpose of informing the public on matters of public interest. | `receipt_id`, `issued_at`, `tenant_id` |

The signed receipt itself is the machine-readable transparency artifact
called for by Article 50(2). Downstream applications can attach the
`receipt_id` to any published content to satisfy Article 50(4) disclosure.

## Retention

Article 12 requires high-risk systems to retain automatically-generated logs
for a period appropriate to the intended purpose, at least 6 months. The
`TraceStore` backing the production deployment must therefore configure
sqlite/postgres retention accordingly. The MVP `:memory:` store is for
development only and does **not** meet Article 12 retention.

## Machine-readable matrix

The same mapping is served live at `GET /v1/compliance/eu_ai_act` so
automated auditors can pull the current clause table without parsing this
markdown.
