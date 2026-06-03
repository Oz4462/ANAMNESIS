# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Cross-language receipt round-trip: Python <-> TypeScript.

Procedure:
  1. Python generates a key, signs a receipt, writes envelope.json + pubkey.
  2. Node script loads the file, verifies via @noble/ed25519. Must succeed.
  3. Node generates a separate key, signs a different receipt, writes a
     second envelope.json + pubkey.
  4. Python verifies the Node-signed envelope. Must succeed.

If either direction breaks, the DSSE PAE encoding or the canonical-JSON
ordering disagrees across languages -- a blocker for any auditor who wants
to verify our receipts without our SDK.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
    ReceiptVerifier,
    SignedEnvelope,
)

REPO = Path(__file__).resolve().parent.parent
TS_DIR = REPO / "anamnesis-ts"
TMP = REPO / "_xlang_tmp"


def _write(p: Path, content: str) -> None:
    p.write_text(content)


def _make_receipt(tenant: str, saved: int) -> Receipt:
    return Receipt(
        tenant_id=tenant,
        request_id="xlang-req",
        model=ModelRef(provider="anthropic", name="claude-opus-4-7"),
        capture_hash="sha256:demo-xlang",
        distill_model="heuristic-v1",
        retrieved_step_ids=["xs1", "xs2"],
        bound=BoundRef(tau=0.18, alpha=0.1, n_calibration=64),
        cost_saved_tokens=saved,
    )


NODE_SCRIPT = r"""
import { readFile, writeFile } from "node:fs/promises";
import {
  verifyEnvelope,
  generateSigningKey,
  signReceipt,
} from "./dist/index.js";

const args = Object.fromEntries(
  process.argv.slice(2).map((a) => a.split("=")).map(([k, v]) => [k.replace(/^--/, ""), v])
);

async function verifyPyFromNode() {
  const envText = await readFile(args["envelope"], "utf-8");
  const pubText = await readFile(args["pubkey"], "utf-8");
  const envelope = JSON.parse(envText);
  const { keyid, publicKeyB64 } = JSON.parse(pubText);
  const receipt = await verifyEnvelope(envelope, [{ keyid, publicKeyB64 }]);
  console.log("NODE_VERIFIED_PY", JSON.stringify({
    tenant_id: receipt.tenant_id,
    cost_saved_tokens: receipt.cost_saved_tokens,
    bound_tau: receipt.bound.tau,
  }));
}

async function signFromNode() {
  const key = await generateSigningKey("xlang-node-key");
  const payload = {
    schema_version: "anamnesis/v1",
    receipt_id: "node-uuid-12345",
    issued_at: "2026-05-17T18:00:00+00:00",
    tenant_id: "node-tenant",
    request_id: "node-req",
    model: { provider: "anthropic", name: "claude-opus-4-7", version: null },
    capture_hash: "sha256:node-demo",
    distill_model: "node-heuristic",
    retrieved_step_ids: ["ns1"],
    bound: { tau: 0.22, alpha: 0.05, n_calibration: 128, score_name: "one_minus_cosine" },
    cost_saved_tokens: 777,
    eu_ai_act_claims: { article_15: true, article_50: true },
  };
  const envelope = await signReceipt(payload, key);
  await writeFile(args["out_envelope"], JSON.stringify(envelope));
  await writeFile(args["out_pubkey"], JSON.stringify({ keyid: key.keyid, publicKeyB64: key.publicKeyB64 }));
  console.log("NODE_SIGNED_OK");
}

if (args["mode"] === "verify-py-from-node") await verifyPyFromNode();
else if (args["mode"] === "sign-from-node") await signFromNode();
else throw new Error("unknown mode");
"""


def main() -> int:
    TMP.mkdir(exist_ok=True)

    print("=== STEP 1: Python signs, Node verifies ===")
    py_signer = ReceiptSigner.generate("xlang-py-key")
    receipt = _make_receipt(tenant="py-tenant", saved=12345)
    envelope = py_signer.sign(receipt)

    env_path = TMP / "py_envelope.json"
    pub_path = TMP / "py_pubkey.json"
    _write(env_path, envelope.to_json())
    _write(pub_path, json.dumps({"keyid": "xlang-py-key", "publicKeyB64": py_signer.public_key_b64()}))

    script_path = TS_DIR / "xlang_runner.mjs"
    _write(script_path, NODE_SCRIPT)

    r = subprocess.run(
        ["node", str(script_path), "--mode=verify-py-from-node",
         f"--envelope={env_path}", f"--pubkey={pub_path}"],
        cwd=TS_DIR, capture_output=True, text=True, timeout=30,
    )
    print("  node stdout:", r.stdout.strip())
    if r.returncode != 0:
        print("  node stderr:", r.stderr)
        return 1
    assert "NODE_VERIFIED_PY" in r.stdout
    payload_summary = json.loads(r.stdout.split("NODE_VERIFIED_PY ", 1)[1])
    assert payload_summary["tenant_id"] == "py-tenant"
    assert payload_summary["cost_saved_tokens"] == 12345
    print("  Node verified Python-issued receipt OK")

    print("\n=== STEP 2: Node signs, Python verifies ===")
    out_env = TMP / "node_envelope.json"
    out_pub = TMP / "node_pubkey.json"
    r2 = subprocess.run(
        ["node", str(script_path), "--mode=sign-from-node",
         f"--out_envelope={out_env}", f"--out_pubkey={out_pub}"],
        cwd=TS_DIR, capture_output=True, text=True, timeout=30,
    )
    print("  node stdout:", r2.stdout.strip())
    if r2.returncode != 0:
        print("  node stderr:", r2.stderr)
        return 2

    node_env_text = out_env.read_text()
    node_pub_meta = json.loads(out_pub.read_text())
    parsed = SignedEnvelope.from_json(node_env_text)
    verifier = ReceiptVerifier.from_public_key_b64(node_pub_meta["keyid"], node_pub_meta["publicKeyB64"])
    recovered = verifier.verify(parsed)
    print(
        f"  Python verified Node-issued receipt OK: tenant={recovered.tenant_id} "
        f"saved={recovered.cost_saved_tokens}"
    )
    assert recovered.tenant_id == "node-tenant"
    assert recovered.cost_saved_tokens == 777

    # cleanup
    for f in TMP.glob("*"):
        f.unlink()
    TMP.rmdir()
    script_path.unlink()

    print("\nCROSS-LANGUAGE RECEIPTS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
