# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Mapping from EU AI Act Articles 15 + 50 requirements to receipt fields.

This module is the audit-grade glue that lets a notified body or a customer
auditor pull up a receipt and immediately see which Article 15 / 50 clauses
it claims to satisfy and how.

References:
    Regulation (EU) 2024/1689 of the European Parliament and of the Council
    of 13 June 2024 laying down harmonised rules on artificial intelligence
    (Artificial Intelligence Act). OJ L, 2024/1689, 12.7.2024.

    Article 15  -- Accuracy, robustness and cybersecurity
    Article 50  -- Transparency obligations for providers and deployers
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArticleClause:
    article: str
    clause: str
    summary: str
    evidence_fields: tuple[str, ...]


ARTICLE_15_CLAUSES: tuple[ArticleClause, ...] = (
    ArticleClause(
        article="15",
        clause="15(1)",
        summary=(
            "Designed and developed to achieve an appropriate level of accuracy, "
            "robustness, and cybersecurity throughout their lifecycle."
        ),
        evidence_fields=("bound.tau", "bound.alpha", "bound.n_calibration"),
    ),
    ArticleClause(
        article="15",
        clause="15(2)",
        summary=(
            "Levels of accuracy and the relevant accuracy metrics are declared in "
            "the accompanying instructions of use."
        ),
        evidence_fields=("bound.score_name", "bound.alpha"),
    ),
    ArticleClause(
        article="15",
        clause="15(3)",
        summary=(
            "Technical solutions to address AI-specific vulnerabilities, including "
            "measures to prevent, detect, respond to, resolve, and control attacks."
        ),
        evidence_fields=("schema_version", "issued_at"),
    ),
    ArticleClause(
        article="15",
        clause="15(4)",
        summary=(
            "Robust against errors, faults, or inconsistencies. Operates with a "
            "consistent performance throughout the lifecycle."
        ),
        evidence_fields=("bound.tau", "bound.alpha", "bound.n_calibration"),
    ),
)

ARTICLE_50_CLAUSES: tuple[ArticleClause, ...] = (
    ArticleClause(
        article="50",
        clause="50(2)",
        summary=(
            "Providers of generative AI systems ensure the outputs are marked "
            "in a machine-readable format and detectable as artificially "
            "generated or manipulated."
        ),
        evidence_fields=("capture_hash", "model.provider", "model.name"),
    ),
    ArticleClause(
        article="50",
        clause="50(4)",
        summary=(
            "Deployers disclose that the content has been artificially generated "
            "or manipulated where the AI system generates or manipulates text "
            "published with the purpose of informing the public on matters of "
            "public interest."
        ),
        evidence_fields=("receipt_id", "issued_at", "tenant_id"),
    ),
)


def compliance_matrix() -> dict[str, list[dict[str, object]]]:
    return {
        "article_15": [
            {
                "clause": c.clause,
                "summary": c.summary,
                "evidence_fields": list(c.evidence_fields),
            }
            for c in ARTICLE_15_CLAUSES
        ],
        "article_50": [
            {
                "clause": c.clause,
                "summary": c.summary,
                "evidence_fields": list(c.evidence_fields),
            }
            for c in ARTICLE_50_CLAUSES
        ],
    }
