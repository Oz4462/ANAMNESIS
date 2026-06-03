# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Tests for the anamnesis CLI via Click's CliRunner."""

from __future__ import annotations

import json

from anamnesis.cli import cli
from click.testing import CliRunner


def test_cli_status_runs():
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0, result.output
    assert "anamnesis SDK version" in result.output


def test_cli_keygen_writes_file(tmp_path):
    out = tmp_path / "key.json"
    runner = CliRunner()
    result = runner.invoke(cli, ["keygen", "--out", str(out), "--keyid", "test-key"])
    assert result.exit_code == 0, result.output
    assert "test-key" in result.output
    data = json.loads(out.read_text())
    assert "seed_b64" in data
    assert "public_b64" in data


def test_cli_demo_runs():
    runner = CliRunner()
    result = runner.invoke(cli, ["demo"])
    assert result.exit_code == 0, result.output
    assert "seeded steps" in result.output


def test_cli_distill_heuristic_on_file(tmp_path):
    f = tmp_path / "trace.txt"
    f.write_text(
        "Erste ausfuehrliche Begruendung dieser Aufgabe. "
        "Zweite vollstaendige Argumentationskette mit Schluss."
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["distill", "--from-file", str(f), "--distiller", "heuristic"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed["distiller"] == "heuristic-v1"
    assert parsed["n_steps"] >= 1


def test_cli_verify_round_trip(tmp_path):
    from anamnesis.receipts import (
        BoundRef,
        ModelRef,
        Receipt,
        ReceiptSigner,
    )

    signer = ReceiptSigner.generate("cli-key")
    receipt = Receipt(
        tenant_id="t",
        request_id="r",
        model=ModelRef(provider="anthropic", name="claude-opus-4-7"),
        capture_hash="sha256:demo",
        distill_model="heuristic-v1",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=64),
        cost_saved_tokens=0,
    )
    env = signer.sign(receipt)
    env_path = tmp_path / "receipt.dsse.json"
    env_path.write_text(env.to_json())

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "verify",
            str(env_path),
            "--pubkey-b64",
            signer.public_key_b64(),
            "--keyid",
            "cli-key",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "VERIFIED" in result.output


def test_cli_verify_detects_tampering(tmp_path):
    import base64

    from anamnesis.receipts import (
        BoundRef,
        ModelRef,
        Receipt,
        ReceiptSigner,
        SignedEnvelope,
    )

    signer = ReceiptSigner.generate("cli-key")
    receipt = Receipt(
        tenant_id="t",
        request_id="r",
        model=ModelRef(provider="anthropic", name="claude-opus-4-7"),
        capture_hash="sha256:demo",
        distill_model="heuristic-v1",
        retrieved_step_ids=[],
        bound=BoundRef(tau=0.1, alpha=0.1, n_calibration=64),
        cost_saved_tokens=0,
    )
    env = signer.sign(receipt)
    payload_dict = json.loads(base64.b64decode(env.payload))
    payload_dict["cost_saved_tokens"] = 999999
    bad_payload = json.dumps(payload_dict, sort_keys=True, separators=(",", ":")).encode()
    bad = SignedEnvelope(
        payloadType=env.payloadType,
        payload=base64.b64encode(bad_payload).decode("ascii"),
        signatures=env.signatures,
    )
    env_path = tmp_path / "tampered.dsse.json"
    env_path.write_text(bad.to_json())

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["verify", str(env_path), "--pubkey-b64", signer.public_key_b64(), "--keyid", "cli-key"],
    )
    assert result.exit_code != 0
    assert "FAILED" in result.output or "FAILED" in (result.stderr or "")
