"""Capture a synthetic Anthropic-shaped response and verify the signed receipt.

Run with: uv run python examples/01_basic_capture.py
"""

from __future__ import annotations

from anamnesis import (
    AnthropicCapture,
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
)


FAKE_ANTHROPIC_RESPONSE = {
    "id": "msg_demo_001",
    "model": "claude-opus-4-7",
    "content": [
        {
            "type": "thinking",
            "thinking": (
                "Schritt 1: Die Aufgabe verlangt das Berechnen einer Dreiecks-Flaeche.\n"
                "Schritt 2: Die Formel ist A = (1/2) * b * h mit b = Basis und h = Hoehe.\n"
                "Schritt 3: Mit b = 10 und h = 6 ergibt sich A = 30 Flaecheneinheiten."
            ),
            "signature": "sig_demo_001",
        },
        {"type": "text", "text": "Die Flaeche betraegt 30 Flaecheneinheiten."},
    ],
    "usage": {"input_tokens": 50, "output_tokens": 12, "thinking_tokens": 220},
    "stop_reason": "end_turn",
}


def main() -> None:
    trace = AnthropicCapture().extract(FAKE_ANTHROPIC_RESPONSE)
    print("=== Captured trace ===")
    print(f"  provider:        {trace.provider}")
    print(f"  model:           {trace.model}")
    print(f"  request_id:      {trace.request_id}")
    print(f"  thinking_tokens: {trace.thinking_tokens}")
    print(f"  output_tokens:   {trace.output_tokens}")
    print(f"  has_thinking:    {trace.has_thinking}")
    print(f"  content_hash:    {trace.content_hash}")

    signer = ReceiptSigner.generate("anamnesis-demo")
    print(f"\nIssuer public key (b64): {signer.public_key_b64()}")

    receipt = Receipt(
        tenant_id="demo-tenant",
        request_id=trace.request_id,
        model=ModelRef(provider=trace.provider, name=trace.model),
        capture_hash=trace.content_hash,
        distill_model="heuristic-v1",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.0, alpha=0.1, n_calibration=0),
        cost_saved_tokens=0,
    )
    envelope = signer.sign(receipt)
    print("\n=== Signed envelope ===")
    print(envelope.to_json()[:200] + " ...")

    verifier = ReceiptVerifier.from_public_key_b64("anamnesis-demo", signer.public_key_b64())
    recovered = verifier.verify(envelope)
    print("\n=== Verified receipt ===")
    print(f"  receipt_id:      {recovered.receipt_id}")
    print(f"  tenant_id:       {recovered.tenant_id}")
    print(f"  EU AI Act Art 15 claim: {recovered.eu_ai_act_claims['article_15']}")
    print(f"  EU AI Act Art 50 claim: {recovered.eu_ai_act_claims['article_50']}")


if __name__ == "__main__":
    main()
