# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""End-to-end reuse demo: warm a calibrator, retrieve, compose, sign, verify.

Run with: uv run python examples/02_reuse_demo.py

The point of this script is to show the full pipeline producing a non-zero
token-savings estimate plus a verifiable receipt on synthetic data — no real
LLM credentials needed.
"""

from __future__ import annotations

import textwrap

from anamnesis import (
    BoundRef,
    CapturedTrace,
    ConformalCalibrator,
    HeuristicDistiller,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
    TraceStore,
    hash_embedder,
)
from anamnesis.compose import compose
from anamnesis.retrieve import ConformalRetriever

SYNTHETIC_TRACES = [
    "Compute the area of a triangle from base and height. The formula is one half times base times height. Substitute b = 10 and h = 6 to get A = 30.",
    "Solve a linear equation a*x + b = 0. Isolate x by subtracting b and dividing by a. Result: x = -b / a.",
    "Compute the volume of a sphere with radius r. Volume formula is four thirds pi r cubed. Substitute r = 3 to get 36 pi.",
    "Translate the sentence from German to English by identifying subject, verb, and object. Use a bilingual dictionary for vocabulary.",
    "Bake a sourdough loaf with rye flour overnight. Mix water and starter and let ferment for twelve hours.",
]

NEW_QUERY = (
    "How do I find the area of a triangle when I know the base and the height?"
)


def main() -> None:
    embedder = hash_embedder(dim=128)
    store = TraceStore(embedder=embedder)
    distiller = HeuristicDistiller(min_step_chars=20)

    print("=== seeding store with synthetic traces ===")
    for i, thinking in enumerate(SYNTHETIC_TRACES):
        trace = CapturedTrace(
            provider="anthropic",
            model="claude-opus-4-7",
            request_id=f"seed_req_{i:03d}",
            thinking_text=thinking,
            answer_text="(answer omitted in seed)",
            thinking_tokens=len(thinking) // 4,
            output_tokens=20,
        )
        tid = store.add_trace(trace)
        steps = distiller.distill(trace)
        store.add_steps(steps)
        print(f"  trace {tid} -> {len(steps)} steps")

    cal = ConformalCalibrator(alpha=0.1, min_calibration=30)
    cal.extend([0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75] * 5)
    print(f"\ncalibrator: ready={cal.ready}, n={cal.n}")
    if cal.ready:
        b = cal.threshold()
        print(f"  bound: tau={b.tau:.4f}  alpha={b.alpha:.2f}  n_calibration={b.n_calibration}")

    retriever = ConformalRetriever(store=store, calibrator=cal, k=5)
    print("\n=== running retrieval on new query ===")
    print(f'  query: "{NEW_QUERY}"')
    result = retriever.retrieve(NEW_QUERY)
    print(f"  abstained: {result.abstained}")
    print(f"  candidates: {len(result.candidates)}")
    print(f"  accepted:   {len(result.accepted)}")
    for i, cand in enumerate(result.accepted, start=1):
        print(f"    [{i}] score={cand.score:.4f}  intent={cand.step.intent[:60]!r}")

    composed = compose(result, user_text=NEW_QUERY)
    print("\n=== composed system fragment (first 600 chars) ===")
    print(textwrap.indent(composed.system_fragment[:600], "  "))

    if not composed.abstained and result.bound is not None:
        signer = ReceiptSigner.generate("anamnesis-demo-key")
        saved = sum(
            store.get_step(sid).text.count(" ") + 1 for sid in composed.reused_step_ids
        )
        receipt = Receipt(
            tenant_id="demo-tenant",
            request_id=f"reuse_{NEW_QUERY[:32]}",
            model=ModelRef(provider="anthropic", name="claude-opus-4-7"),
            capture_hash="reuse:" + ",".join(composed.reused_step_ids),
            distill_model=distiller.name,
            retrieved_step_ids=list(composed.reused_step_ids),
            bound=BoundRef(
                tau=result.bound.tau,
                alpha=result.bound.alpha,
                n_calibration=result.bound.n_calibration,
            ),
            cost_saved_tokens=saved,
        )
        envelope = signer.sign(receipt)
        verifier = ReceiptVerifier.from_public_key_b64(
            "anamnesis-demo-key", signer.public_key_b64()
        )
        recovered = verifier.verify(envelope)
        print("\n=== signed receipt ===")
        print(f"  receipt_id:        {recovered.receipt_id}")
        print(f"  cost_saved_tokens: {recovered.cost_saved_tokens}")
        print(f"  bound:             tau={recovered.bound.tau:.4f}  "
              f"alpha={recovered.bound.alpha}  n={recovered.bound.n_calibration}")
        print(f"  EU AI Act Art 15:  {recovered.eu_ai_act_claims['article_15']}")
        print(f"  EU AI Act Art 50:  {recovered.eu_ai_act_claims['article_50']}")


if __name__ == "__main__":
    main()
