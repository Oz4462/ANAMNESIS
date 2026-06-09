# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""anamnesis CLI — local-first operator tools.

Subcommands:

    anamnesis status
    anamnesis keygen [--out FILE]
    anamnesis verify --pubkey-b64 KEY [--keyid ID] RECEIPT_JSON_FILE
    anamnesis distill [--from-file FILE] [--distiller heuristic|haiku]
    anamnesis demo

Designed to run without network access for `status`, `keygen`, `verify`,
`distill --distiller heuristic`, and `demo`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from anamnesis import __version__
from anamnesis.capture import CapturedTrace
from anamnesis.compose import compose
from anamnesis.conformal import ConformalCalibrator
from anamnesis.distill import distiller_for
from anamnesis.receipts import (
    ReceiptSigner,
    ReceiptVerifier,
    SignedEnvelope,
)
from anamnesis.retrieve import ConformalRetriever
from anamnesis.storage import TraceStore, embedder_for


@click.group()
@click.version_option(__version__, prog_name="anamnesis")
def cli() -> None:
    """ANAMNESIS — verifiable reasoning memory CLI."""


@cli.command()
def status() -> None:
    """Print SDK + extras availability."""
    click.echo(f"anamnesis SDK version: {__version__}")
    try:
        import fastembed  # type: ignore  # noqa: F401

        click.echo("fastembed:            available")
    except ImportError:
        click.echo("fastembed:            NOT available (install 'anamnesis[embed]')")
    try:
        import anthropic  # type: ignore  # noqa: F401

        click.echo("anthropic:            available")
    except ImportError:
        click.echo("anthropic:            NOT available (install 'anthropic')")
    try:
        import openai  # type: ignore  # noqa: F401

        click.echo("openai:               available")
    except ImportError:
        click.echo("openai:               NOT available (install 'openai')")


@cli.command()
@click.option("--out", "-o", default=None, type=click.Path(dir_okay=False), help="Write seed bytes to this file (base64).")
@click.option("--keyid", "-k", default="anamnesis-cli", help="Key identifier label.")
def keygen(out: str | None, keyid: str) -> None:
    """Generate a fresh Ed25519 signing key for issuing receipts."""
    signer = ReceiptSigner.generate(keyid)
    seed_b64 = signer.export_seed_b64()
    pub_b64 = signer.public_key_b64()
    click.echo(f"keyid:      {keyid}")
    click.echo(f"public_b64: {pub_b64}")
    click.echo(f"seed_b64:   {seed_b64}")
    if out:
        Path(out).write_text(
            json.dumps(
                {"keyid": keyid, "seed_b64": seed_b64, "public_b64": pub_b64},
                indent=2,
            )
        )
        click.echo(f"wrote {out}")


@cli.command()
@click.argument("receipt_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--pubkey-b64", required=True, help="Issuer public key (base64).")
@click.option("--keyid", default="anamnesis-cli", help="Key identifier expected in signatures.")
def verify(receipt_file: str, pubkey_b64: str, keyid: str) -> None:
    """Verify a signed DSSE envelope produced by `anamnesis` and dump its payload."""
    raw = Path(receipt_file).read_text()
    env = SignedEnvelope.from_json(raw)
    verifier = ReceiptVerifier.from_public_key_b64(keyid, pubkey_b64)
    try:
        receipt = verifier.verify(env)
    except Exception as e:
        click.echo(f"VERIFICATION FAILED: {e}", err=True)
        sys.exit(2)
    click.echo("VERIFIED")
    click.echo(json.dumps(receipt.to_payload_dict(), indent=2, sort_keys=True))


@cli.command()
@click.option("--from-file", "-i", type=click.Path(exists=True, dir_okay=False), required=True)
@click.option("--distiller", "-d", default="heuristic", show_default=True, help="heuristic | anthropic-haiku")
@click.option("--provider", default="anthropic", show_default=True)
@click.option("--model", default="claude-opus-4-7", show_default=True)
def distill(from_file: str, distiller: str, provider: str, model: str) -> None:
    """Distil a thinking-text file into reasoning steps as JSON."""
    thinking = Path(from_file).read_text(encoding="utf-8")
    trace = CapturedTrace(
        provider=provider,
        model=model,
        request_id=f"cli_{Path(from_file).stem}",
        thinking_text=thinking,
        answer_text="",
        thinking_tokens=len(thinking) // 4,
        output_tokens=0,
    )
    d = distiller_for(distiller)
    steps = d.distill(trace)
    out = [
        {
            "step_id": s.step_id,
            "intent": s.intent,
            "text": s.text,
            "preconditions": list(s.preconditions),
            "produces": list(s.produces),
            "tags": list(s.tags),
        }
        for s in steps
    ]
    click.echo(json.dumps({"distiller": d.name, "n_steps": len(out), "steps": out}, indent=2))


@cli.command()
@click.option(
    "--from-file", "-i",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="JSONL ({query, thinking_tokens, output_tokens} per line) or CSV "
         "(.csv with matching header columns) workload file",
)
@click.option(
    "--provider", "-p",
    type=click.Choice(["claude-opus-4-7", "o3-pro", "deepseek-r1", "gemini-2.5-flash"]),
    default="claude-opus-4-7",
    show_default=True,
)
@click.option("--alpha", type=float, default=0.1, show_default=True)
@click.option(
    "--min-calibration", type=int, default=30, show_default=True,
    help="Minimum scores before the conformal threshold is computed",
)
def savings(from_file: str, provider: str, alpha: float, min_calibration: int) -> None:
    """Estimate token-savings on a prospect's own workload (no LLM calls)."""
    from anamnesis.savings import (
        PROVIDER_REGISTRY,
        load_workload,
        run_savings_simulation,
    )
    rows = list(load_workload(from_file))
    pricing = PROVIDER_REGISTRY[provider]
    report = run_savings_simulation(
        rows,
        pricing=pricing,
        alpha=alpha,
        min_calibration=min_calibration,
    )
    out = report.to_dict()
    click.echo(json.dumps(out, indent=2))
    click.echo(
        f"\n=== summary ===\n"
        f"  {report.reuse_rate_pct:.1f}% of queries reusable, "
        f"saving {report.savings_rate_pct:.1f}% of thinking-tokens\n"
        f"  ${report.reused_thinking_cost_usd:.2f} saved out of "
        f"${report.total_thinking_cost_usd:.2f} (provider {provider})",
        err=True,
    )


@cli.command()
def demo() -> None:
    """End-to-end demo: seed traces, calibrate, retrieve, compose, sign, verify."""
    embedder = embedder_for("hash", dim=128)
    store = TraceStore(embedder=embedder)
    distiller = distiller_for("heuristic", min_step_chars=20)

    seeds = [
        "Compute the area of a triangle from base and height. The formula is one half times base times height.",
        "Solve a linear equation a*x + b = 0 by isolating x.",
        "Compute the volume of a sphere with radius r using V = (4/3) pi r^3.",
        "Translate the sentence from German to English using bilingual dictionary.",
        "Bake a sourdough loaf with rye flour overnight.",
    ]
    for i, t in enumerate(seeds):
        trace = CapturedTrace(
            provider="anthropic",
            model="claude-opus-4-7",
            request_id=f"seed_{i}",
            thinking_text=t,
            answer_text="",
            thinking_tokens=len(t) // 4,
            output_tokens=10,
        )
        store.add_trace(trace)
        store.add_steps(distiller.distill(trace))

    cal = ConformalCalibrator(alpha=0.1, min_calibration=30)
    cal.extend([0.4, 0.5, 0.6, 0.7] * 10)
    retriever = ConformalRetriever(store=store, calibrator=cal, k=5)

    query = "How do I find the area of a triangle when I know the base and the height?"
    result = retriever.retrieve(query)
    composed = compose(result, user_text=query)

    click.echo("=== demo ===")
    click.echo(f"  seeded steps:   {store.n_steps}")
    click.echo(f"  candidates:     {len(result.candidates)}")
    click.echo(f"  accepted:       {len(result.accepted)}")
    click.echo(f"  abstained:      {composed.abstained}")
    if not composed.abstained:
        click.echo(f"  bound:          tau={result.bound.tau:.4f} alpha={result.bound.alpha} n={result.bound.n_calibration}")
        for i, c in enumerate(result.accepted, start=1):
            click.echo(f"    [{i}] score={c.score:.4f} intent={c.step.intent[:60]!r}")


if __name__ == "__main__":
    cli()
