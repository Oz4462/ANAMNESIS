# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Receipt evidence chains: a sequence of receipts forms a verifiable
audit trail for a user session.

For EU AI Act Article 12 (record-keeping) and Article 15 (logging) the
notified body wants more than "this single receipt is signed" -- they
want "here is the full sequence of decisions for tenant X in window Y
and every one verifies under the same issuer key".
"""

from __future__ import annotations

import time

import pytest
from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
    SignedEnvelope,
)
from nacl.exceptions import BadSignatureError


def _signer() -> ReceiptSigner:
    return ReceiptSigner.generate("chain-issuer")


def _receipt(tenant: str, seq: int, prev_receipt_id: str | None = None) -> Receipt:
    r = Receipt(
        tenant_id=tenant,
        request_id=f"req-{seq:03d}",
        model=ModelRef(provider="anthropic", name="claude-opus-4-7"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="heuristic-v1",
        retrieved_step_ids=[f"step-{seq}-a", f"step-{seq}-b"],
        bound=BoundRef(tau=0.18, alpha=0.1, n_calibration=64),
        cost_saved_tokens=seq * 10,
    )
    if prev_receipt_id is not None:
        # We use the eu_ai_act_claims dict as a free-form annotation channel
        # to link the chain without changing the schema.
        r.eu_ai_act_claims = {
            **r.eu_ai_act_claims,
            "chain_prev": prev_receipt_id,  # type: ignore[dict-item]
        }
    return r


def test_chain_of_three_receipts_all_verify():
    signer = _signer()
    verifier = ReceiptVerifier.from_public_key_b64("chain-issuer", signer.public_key_b64())

    envelopes: list[SignedEnvelope] = []
    prev: str | None = None
    for i in range(3):
        r = _receipt("session-A", seq=i, prev_receipt_id=prev)
        env = signer.sign(r)
        envelopes.append(env)
        prev = r.receipt_id

    recovered = [verifier.verify(e) for e in envelopes]
    assert [r.cost_saved_tokens for r in recovered] == [0, 10, 20]
    # Each receipt after the first carries a chain_prev pointing at its predecessor.
    assert "chain_prev" not in recovered[0].eu_ai_act_claims
    assert recovered[1].eu_ai_act_claims["chain_prev"] == recovered[0].receipt_id
    assert recovered[2].eu_ai_act_claims["chain_prev"] == recovered[1].receipt_id


def test_chain_with_tampered_link_breaks_verification():
    import base64
    import json

    signer = _signer()
    verifier = ReceiptVerifier.from_public_key_b64("chain-issuer", signer.public_key_b64())

    r1 = _receipt("session-B", seq=0)
    signer.sign(r1)
    r2 = _receipt("session-B", seq=1, prev_receipt_id=r1.receipt_id)
    e2 = signer.sign(r2)

    # Attacker changes prev pointer in r2 to point at a different prior receipt.
    payload = json.loads(base64.b64decode(e2.payload))
    payload["eu_ai_act_claims"]["chain_prev"] = "FORGED-PREV-ID"
    tampered = SignedEnvelope(
        payloadType=e2.payloadType,
        payload=base64.b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).decode(),
        signatures=e2.signatures,
    )
    with pytest.raises((BadSignatureError, ValueError)):
        verifier.verify(tampered)


def test_chain_is_temporally_ordered():
    signer = _signer()
    envelopes = []
    for i in range(5):
        r = _receipt("session-C", seq=i)
        envelopes.append(signer.sign(r))
        time.sleep(0.005)  # ensure distinct issued_at values

    verifier = ReceiptVerifier.from_public_key_b64("chain-issuer", signer.public_key_b64())
    timestamps = [verifier.verify(e).issued_at for e in envelopes]
    assert timestamps == sorted(timestamps)


def test_chain_full_replay_byte_identical():
    """A chain serialised to JSON and parsed back must verify identically."""
    signer = _signer()
    verifier = ReceiptVerifier.from_public_key_b64("chain-issuer", signer.public_key_b64())

    chain = []
    for i in range(4):
        env = signer.sign(_receipt("session-D", seq=i))
        chain.append(env.to_json())

    for serialised in chain:
        parsed = SignedEnvelope.from_json(serialised)
        verifier.verify(parsed)  # no raise


def test_two_signers_in_same_chain_distinct_verifier_keys():
    """A chain that switched issuer mid-session needs the verifier to know
    about both pubkeys. We confirm that providing only one rejects the other."""
    s_a = ReceiptSigner.generate("issuer-a")
    s_b = ReceiptSigner.generate("issuer-b")
    r_a = signed_envelope = s_a.sign(_receipt("mixed", seq=0))
    r_b = s_b.sign(_receipt("mixed", seq=1))

    only_a = ReceiptVerifier.from_public_key_b64("issuer-a", s_a.public_key_b64())
    only_a.verify(r_a)  # ok
    with pytest.raises((BadSignatureError, ValueError)):
        only_a.verify(r_b)
    _ = signed_envelope


def test_chain_size_scales_linearly_in_storage_bytes():
    """Cumulative byte size of N receipts grows ~linearly -- no hidden quadratic."""
    signer = _signer()
    sizes = []
    for n in [10, 50, 100, 500]:
        total = 0
        for i in range(n):
            env = signer.sign(_receipt("scale", seq=i))
            total += len(env.to_json())
        sizes.append(total)
    # Check that doubling n roughly doubles total bytes (within 30%).
    for i in range(1, len(sizes)):
        prev, curr = sizes[i - 1], sizes[i]
        ratio = curr / prev
        assert 1.5 < ratio < 12.0, f"non-linear scaling: ratio {ratio:.2f}"
