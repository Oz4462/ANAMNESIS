# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Exercise the CLI as an actual installed binary.

The Click `CliRunner` covers in-process behaviour, but it bypasses the
pyproject `[project.scripts] anamnesis = "anamnesis.cli:cli"` entry point.
This module proves the entry point is registered and dispatches correctly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "anamnesis.cli", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cli_module_invocation_status():
    """python -m anamnesis.cli status -- proves the module is importable as main."""
    r = _run(["status"])
    assert r.returncode == 0, r.stderr
    assert "anamnesis SDK version" in r.stdout


def test_cli_module_invocation_keygen():
    r = _run(["keygen", "--keyid", "subprocess-test"])
    assert r.returncode == 0, r.stderr
    assert "subprocess-test" in r.stdout
    assert "public_b64:" in r.stdout
    assert "seed_b64:" in r.stdout


def test_cli_module_invocation_demo():
    r = _run(["demo"])
    assert r.returncode == 0, r.stderr
    assert "seeded steps" in r.stdout
    assert "candidates" in r.stdout


def test_cli_module_help():
    r = _run(["--help"])
    assert r.returncode == 0
    assert "status" in r.stdout
    assert "keygen" in r.stdout
    assert "verify" in r.stdout
    assert "demo" in r.stdout


def test_cli_distill_via_subprocess(tmp_path):
    f = tmp_path / "trace.txt"
    f.write_text(
        "Erste vollstaendige Begruendung der Aufgabe im Detail. "
        "Zweite mathematische Ableitung mit Schluss."
    )
    r = _run(["distill", "--from-file", str(f), "--distiller", "heuristic"])
    assert r.returncode == 0, r.stderr
    parsed = json.loads(r.stdout)
    assert parsed["n_steps"] >= 1
    assert parsed["distiller"] == "heuristic-v1"


def test_cli_verify_subprocess_round_trip(tmp_path):
    """Generate a key with the CLI, sign with the SDK, verify with the CLI."""
    from anamnesis.receipts import (
        BoundRef,
        ModelRef,
        Receipt,
        ReceiptSigner,
    )

    signer = ReceiptSigner.generate("subproc-key")
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
    envelope = signer.sign(receipt)
    env_path = tmp_path / "receipt.dsse.json"
    env_path.write_text(envelope.to_json())

    r = _run([
        "verify",
        str(env_path),
        "--pubkey-b64",
        signer.public_key_b64(),
        "--keyid",
        "subproc-key",
    ])
    assert r.returncode == 0, r.stderr
    assert "VERIFIED" in r.stdout


def test_cli_unknown_subcommand_exits_nonzero():
    r = _run(["does-not-exist"])
    assert r.returncode != 0
