# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Splice accepted reasoning steps into a new prompt.

The composer turns a RetrievalResult into a system-prompt fragment that
tells the downstream reasoning model:

    1. here is your task (the original user prompt),
    2. here are prior reasoning steps from your own organisation that are
       relevant under a calibrated conformal bound,
    3. you may reuse those steps as scaffolding -- you do NOT have to re-derive
       them, and the bound below quantifies the worst-case semantic drift.

The text format is deterministic so it can be hashed and recorded in the
receipt for full audit replay.
"""

from __future__ import annotations

from dataclasses import dataclass

from anamnesis.retrieve import RetrievalResult


@dataclass(frozen=True, slots=True)
class ComposedPrompt:
    """A spliced prompt plus the audit metadata that produced it."""

    system_fragment: str
    user_text: str
    reused_step_ids: tuple[str, ...]
    tau: float | None
    alpha: float | None
    n_calibration: int | None
    abstained: bool

    @property
    def full_system_prompt(self) -> str:
        return self.system_fragment


_HEADER = (
    "## ANAMNESIS REUSE CONTEXT\n"
    "The reasoning steps below come from prior solved problems in the same\n"
    "organisation. They are retrieved under a calibrated conformal bound and\n"
    "may be reused as scaffolding without re-deriving them. The bound (tau,\n"
    "alpha) records the worst-case semantic drift the operator has accepted.\n"
)


_FOOTER = (
    "## END OF REUSE CONTEXT\n"
    "If a reused step is inapplicable, reason from scratch and ignore it.\n"
)


def compose(retrieval: RetrievalResult, user_text: str) -> ComposedPrompt:
    """Build a ComposedPrompt from a RetrievalResult and the new user query."""
    if retrieval.abstained or not retrieval.accepted:
        return ComposedPrompt(
            system_fragment="",
            user_text=user_text,
            reused_step_ids=(),
            tau=retrieval.bound.tau if retrieval.bound else None,
            alpha=retrieval.bound.alpha if retrieval.bound else None,
            n_calibration=retrieval.bound.n_calibration if retrieval.bound else None,
            abstained=True,
        )

    bound = retrieval.bound
    if bound is None:  # accepted is non-empty only when a bound was computed
        raise ValueError("retrieval has accepted candidates but no conformal bound")

    lines = [_HEADER]
    lines.append(
        f"bound: tau={bound.tau:.4f} alpha={bound.alpha:.3f} n_calibration={bound.n_calibration}\n"
    )
    lines.append("steps:\n")
    for i, cand in enumerate(retrieval.accepted, start=1):
        s = cand.step
        precs = "; ".join(s.preconditions) if s.preconditions else "none"
        prods = "; ".join(s.produces) if s.produces else "none"
        tags = ",".join(s.tags) if s.tags else "none"
        lines.append(
            f"  [{i}] id={s.step_id} score={cand.score:.4f}\n"
            f"      intent: {s.intent}\n"
            f"      text: {s.text}\n"
            f"      preconditions: {precs}\n"
            f"      produces: {prods}\n"
            f"      tags: {tags}\n"
        )
    lines.append(_FOOTER)

    return ComposedPrompt(
        system_fragment="".join(lines),
        user_text=user_text,
        reused_step_ids=retrieval.accepted_step_ids,
        tau=bound.tau,
        alpha=bound.alpha,
        n_calibration=bound.n_calibration,
        abstained=False,
    )
