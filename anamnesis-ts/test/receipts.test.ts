import { describe, expect, it } from "vitest";
import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha2";

import {
  canonicalPayloadBytes,
  pae,
  verifyEnvelope,
  RECEIPT_PAYLOAD_TYPE,
  ReceiptVerificationError,
} from "../src/receipts.js";
import type { ReceiptPayload, SignedEnvelope } from "../src/types.js";

ed.etc.sha512Sync = (...m: Uint8Array[]) => sha512(ed.etc.concatBytes(...m));
ed.etc.sha512Async = async (...m: Uint8Array[]) => sha512(ed.etc.concatBytes(...m));

function toB64(buf: Uint8Array): string {
  if (typeof Buffer !== "undefined") return Buffer.from(buf).toString("base64");
  let bin = "";
  for (const b of buf) bin += String.fromCharCode(b);
  return btoa(bin);
}

async function makeSignedEnvelope(payload: ReceiptPayload, keyid = "ts-test-key"): Promise<{
  envelope: SignedEnvelope;
  publicKeyB64: string;
}> {
  const seed = ed.utils.randomPrivateKey();
  const publicKey = await ed.getPublicKeyAsync(seed);
  const payloadBytes = canonicalPayloadBytes(payload);
  const paeBytes = pae(RECEIPT_PAYLOAD_TYPE, payloadBytes);
  const sig = await ed.signAsync(paeBytes, seed);
  return {
    envelope: {
      payloadType: RECEIPT_PAYLOAD_TYPE,
      payload: toB64(payloadBytes),
      signatures: [{ keyid, sig: toB64(sig) }],
    },
    publicKeyB64: toB64(publicKey),
  };
}

function samplePayload(overrides: Partial<ReceiptPayload> = {}): ReceiptPayload {
  return {
    schema_version: "anamnesis/v1",
    receipt_id: "test-uuid",
    issued_at: "2026-05-17T00:00:00+00:00",
    tenant_id: "tenant-x",
    request_id: "req-1",
    model: { provider: "anthropic", name: "claude-opus-4-7", version: null },
    capture_hash: "sha256:abc",
    distill_model: "heuristic-v1",
    retrieved_step_ids: ["step_a"],
    bound: { tau: 0.2, alpha: 0.1, n_calibration: 64, score_name: "one_minus_cosine" },
    cost_saved_tokens: 100,
    eu_ai_act_claims: { article_15: true, article_50: true },
    ...overrides,
  };
}

describe("pae", () => {
  it("matches DSSE format header", () => {
    const out = pae(RECEIPT_PAYLOAD_TYPE, new Uint8Array([1, 2, 3]));
    const s = new TextDecoder().decode(out);
    expect(s.startsWith("DSSEv1 ")).toBe(true);
    expect(s).toContain(String(RECEIPT_PAYLOAD_TYPE.length));
    expect(s).toContain(" 3 ");
  });
});

describe("verifyEnvelope", () => {
  it("verifies a freshly signed envelope", async () => {
    const payload = samplePayload();
    const { envelope, publicKeyB64 } = await makeSignedEnvelope(payload);
    const recovered = await verifyEnvelope(envelope, [{ keyid: "ts-test-key", publicKeyB64 }]);
    expect(recovered.tenant_id).toBe(payload.tenant_id);
    expect(recovered.bound.tau).toBeCloseTo(0.2);
    expect(recovered.eu_ai_act_claims.article_15).toBe(true);
  });

  it("rejects tampered payload", async () => {
    const { envelope, publicKeyB64 } = await makeSignedEnvelope(samplePayload());
    const tampered: SignedEnvelope = {
      ...envelope,
      payload: toB64(new TextEncoder().encode('{"tenant_id":"different"}')),
    };
    await expect(
      verifyEnvelope(tampered, [{ keyid: "ts-test-key", publicKeyB64 }]),
    ).rejects.toBeInstanceOf(ReceiptVerificationError);
  });

  it("rejects unknown keyid", async () => {
    const { envelope, publicKeyB64 } = await makeSignedEnvelope(samplePayload());
    await expect(
      verifyEnvelope(envelope, [{ keyid: "OTHER", publicKeyB64 }]),
    ).rejects.toBeInstanceOf(ReceiptVerificationError);
  });

  it("rejects wrong payload type", async () => {
    const { envelope, publicKeyB64 } = await makeSignedEnvelope(samplePayload());
    const wrong = { ...envelope, payloadType: "application/json" };
    await expect(
      verifyEnvelope(wrong, [{ keyid: "ts-test-key", publicKeyB64 }]),
    ).rejects.toBeInstanceOf(ReceiptVerificationError);
  });

  it("rejects empty signatures", async () => {
    const env: SignedEnvelope = {
      payloadType: RECEIPT_PAYLOAD_TYPE,
      payload: toB64(new TextEncoder().encode("{}")),
      signatures: [],
    };
    await expect(
      verifyEnvelope(env, [{ keyid: "any", publicKeyB64: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=" }]),
    ).rejects.toBeInstanceOf(ReceiptVerificationError);
  });
});
