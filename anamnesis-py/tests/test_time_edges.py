"""Time + clock edge cases.

Receipts carry an `issued_at` field that auditors will sanity-check.
Out-of-range or pathological timestamps must not crash signing or
verification, and the canonical ISO-8601 serialisation must round-trip
through every supported timezone offset.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
)


def _r(issued_at: str) -> Receipt:
    return Receipt(
        tenant_id="time-t",
        request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=0,
        issued_at=issued_at,
    )


@pytest.mark.parametrize("iso", [
    "1970-01-01T00:00:00+00:00",      # epoch zero
    "1969-12-31T23:59:59+00:00",      # negative epoch
    "2038-01-19T03:14:07+00:00",      # Y2K38 (signed 32-bit unix)
    "2038-01-19T03:14:08+00:00",      # Y2K38 + 1 second
    "2100-02-29T00:00:00+00:00",      # 2100 is NOT a leap year, this is invalid
    "9999-12-31T23:59:59+00:00",      # far future, last representable in YYYY ISO
    "2026-05-17T12:00:00+14:00",      # extreme east timezone
    "2026-05-17T12:00:00-12:00",      # extreme west timezone
])
def test_issued_at_accepts_extreme_timestamps(iso: str):
    """Our receipt model accepts any string for issued_at -- we never
    parse it back to a datetime, just sign it as bytes. Auditors do the
    semantic check. Confirm nothing crashes."""
    signer = ReceiptSigner.generate("t")
    receipt = _r(iso)
    env = signer.sign(receipt)
    verifier = ReceiptVerifier.from_public_key_b64("t", signer.public_key_b64())
    recovered = verifier.verify(env)
    assert recovered.issued_at == iso


def test_default_issued_at_is_iso8601_utc():
    receipt = Receipt(
        tenant_id="t",
        request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=0,
    )
    parsed = datetime.fromisoformat(receipt.issued_at)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)


def test_two_receipts_in_quick_succession_have_distinct_default_timestamps_or_equal():
    """Two receipts created in the same millisecond may share issued_at;
    that's fine because receipt_id (uuid4) still disambiguates."""
    r1 = Receipt(
        tenant_id="t",
        request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=0,
    )
    r2 = Receipt(
        tenant_id="t",
        request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=0,
    )
    assert r1.receipt_id != r2.receipt_id
    # Timestamps may or may not be equal depending on clock resolution.
    assert r1.issued_at <= r2.issued_at


def test_issued_at_round_trips_through_dst_boundary():
    """Local-time strings with DST offsets must survive sign+verify. We
    use Europe/Berlin offsets to span the spring-forward."""
    sunday_march_winter = "2026-03-29T01:30:00+01:00"
    sunday_march_summer = "2026-03-29T03:30:00+02:00"  # right after DST
    for ts in (sunday_march_winter, sunday_march_summer):
        signer = ReceiptSigner.generate("dst")
        env = signer.sign(_r(ts))
        verifier = ReceiptVerifier.from_public_key_b64("dst", signer.public_key_b64())
        recovered = verifier.verify(env)
        assert recovered.issued_at == ts


def test_naive_datetime_in_issued_at_round_trips_as_string():
    """Even a naive (no-timezone) ISO string is signed as bytes."""
    naive = "2026-05-17T12:00:00"
    signer = ReceiptSigner.generate("n")
    env = signer.sign(_r(naive))
    verifier = ReceiptVerifier.from_public_key_b64("n", signer.public_key_b64())
    assert verifier.verify(env).issued_at == naive


def test_iso_microseconds_in_issued_at_preserved():
    fine = "2026-05-17T12:34:56.123456+00:00"
    signer = ReceiptSigner.generate("u")
    env = signer.sign(_r(fine))
    verifier = ReceiptVerifier.from_public_key_b64("u", signer.public_key_b64())
    assert verifier.verify(env).issued_at == fine


def test_issued_at_with_z_suffix_preserved():
    z = "2026-05-17T12:00:00Z"
    signer = ReceiptSigner.generate("z")
    env = signer.sign(_r(z))
    verifier = ReceiptVerifier.from_public_key_b64("z", signer.public_key_b64())
    assert verifier.verify(env).issued_at == z


def test_receipt_chain_is_temporally_sortable_by_issued_at():
    signer = ReceiptSigner.generate("sort")
    receipts = [
        _r("2026-05-17T12:00:00+00:00"),
        _r("2026-05-17T12:00:01+00:00"),
        _r("2026-05-17T12:00:02+00:00"),
        _r("2026-05-17T12:00:03+00:00"),
    ]
    envelopes = [signer.sign(r) for r in receipts]
    verifier = ReceiptVerifier.from_public_key_b64("sort", signer.public_key_b64())
    times = [verifier.verify(e).issued_at for e in envelopes]
    assert times == sorted(times)


def test_huge_year_in_issued_at_does_not_crash():
    big_year = "99999-12-31T23:59:59+00:00"
    signer = ReceiptSigner.generate("y")
    env = signer.sign(_r(big_year))
    verifier = ReceiptVerifier.from_public_key_b64("y", signer.public_key_b64())
    assert verifier.verify(env).issued_at == big_year


def test_negative_year_in_issued_at_treated_as_string():
    """Pre-Common-Era timestamps: signed as opaque string, never parsed."""
    pre_ce = "-0500-01-01T00:00:00+00:00"
    signer = ReceiptSigner.generate("bce")
    env = signer.sign(_r(pre_ce))
    verifier = ReceiptVerifier.from_public_key_b64("bce", signer.public_key_b64())
    assert verifier.verify(env).issued_at == pre_ce


def test_timezone_offset_with_seconds_preserved():
    """Some historical timezones have offsets with seconds; ISO 8601 allows
    it. Our serialisation must not normalise it away."""
    tz_secs = "2026-05-17T12:00:00+05:30:15"
    signer = ReceiptSigner.generate("tz")
    env = signer.sign(_r(tz_secs))
    verifier = ReceiptVerifier.from_public_key_b64("tz", signer.public_key_b64())
    assert verifier.verify(env).issued_at == tz_secs


def test_issued_at_default_is_strictly_increasing_under_sleep():
    import time as _t
    r1 = Receipt(
        tenant_id="t", request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d", retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=0,
    )
    _t.sleep(0.01)
    r2 = Receipt(
        tenant_id="t", request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d", retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=0,
    )
    assert r1.issued_at < r2.issued_at


def test_utc_now_is_used_not_local_time():
    """The default issued_at MUST be UTC; auditors in different timezones
    must see the same value."""
    receipt = Receipt(
        tenant_id="t", request_id="r",
        model=ModelRef(provider="anthropic", name="m"),
        capture_hash="sha256:" + ("0" * 64),
        distill_model="d", retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=10),
        cost_saved_tokens=0,
    )
    parsed = datetime.fromisoformat(receipt.issued_at)
    now_utc = datetime.now(UTC)
    # Allow up to 5s slack between construction and assertion.
    assert abs((now_utc - parsed).total_seconds()) < 5.0
