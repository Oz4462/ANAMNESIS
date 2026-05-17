import { describe, expect, it } from "vitest";

import {
  generateSigningKey,
  signingKeyFromSeedB64,
  signReceipt,
  verifyEnvelope,
  ReceiptVerificationError,
  canonicalPayloadBytes,
  pae,
  RECEIPT_PAYLOAD_TYPE,
} from "../src/index.js";
import type { ReceiptPayload, SignedEnvelope } from "../src/index.js";

function samplePayload(saved = 100): ReceiptPayload {
  return {
    schema_version: "anamnesis/v1",
    receipt_id: "ts-uuid-1",
    issued_at: "2026-05-17T00:00:00+00:00",
    tenant_id: "ts-tenant",
    request_id: "ts-req",
    model: { provider: "anthropic", name: "claude-opus-4-7", version: null },
    capture_hash: "sha256:demo",
    distill_model: "ts-heuristic",
    retrieved_step_ids: ["ts1", "ts2"],
    bound: { tau: 0.18, alpha: 0.1, n_calibration: 64, score_name: "one_minus_cosine" },
    cost_saved_tokens: saved,
    eu_ai_act_claims: { article_15: true, article_50: true },
  };
}

describe("generateSigningKey", () => {
  it("produces a 32-byte seed and 32-byte pubkey", async () => {
    const key = await generateSigningKey("k");
    expect(Buffer.from(key.seedB64, "base64").length).toBe(32);
    expect(Buffer.from(key.publicKeyB64, "base64").length).toBe(32);
  });

  it("two generates yield distinct keys", async () => {
    const a = await generateSigningKey("a");
    const b = await generateSigningKey("b");
    expect(a.publicKeyB64).not.toBe(b.publicKeyB64);
  });
});

describe("signingKeyFromSeedB64", () => {
  it("recovers same public key from same seed", async () => {
    const orig = await generateSigningKey("orig");
    const restored = await signingKeyFromSeedB64(orig.seedB64, "restored");
    expect(restored.publicKeyB64).toBe(orig.publicKeyB64);
  });

  it("changes keyid without changing key material", async () => {
    const orig = await generateSigningKey("a");
    const restored = await signingKeyFromSeedB64(orig.seedB64, "b");
    expect(restored.keyid).toBe("b");
    expect(restored.publicKeyB64).toBe(orig.publicKeyB64);
  });
});

describe("signReceipt", () => {
  it("round-trips through verifyEnvelope", async () => {
    const key = await generateSigningKey("ts-rt");
    const env = await signReceipt(samplePayload(7), key);
    const recovered = await verifyEnvelope(env, [
      { keyid: key.keyid, publicKeyB64: key.publicKeyB64 },
    ]);
    expect(recovered.cost_saved_tokens).toBe(7);
    expect(recovered.tenant_id).toBe("ts-tenant");
  });

  it("changes the signature when cost_saved_tokens changes", async () => {
    const key = await generateSigningKey("ts-rt");
    const a = await signReceipt(samplePayload(1), key);
    const b = await signReceipt(samplePayload(2), key);
    expect(a.signatures[0].sig).not.toBe(b.signatures[0].sig);
    expect(a.payload).not.toBe(b.payload);
  });

  it("is deterministic for the same key + same payload", async () => {
    const key = await generateSigningKey("ts-det");
    const a = await signReceipt(samplePayload(99), key);
    const b = await signReceipt(samplePayload(99), key);
    expect(a.signatures[0].sig).toBe(b.signatures[0].sig);
    expect(a.payload).toBe(b.payload);
  });

  it("produces an envelope with the canonical payloadType", async () => {
    const key = await generateSigningKey("ts-pt");
    const env = await signReceipt(samplePayload(), key);
    expect(env.payloadType).toBe(RECEIPT_PAYLOAD_TYPE);
    expect(env.signatures.length).toBe(1);
    expect(env.signatures[0].keyid).toBe("ts-pt");
  });
});

describe("verifyEnvelope failure modes", () => {
  it("rejects empty signatures array", async () => {
    const env: SignedEnvelope = {
      payloadType: RECEIPT_PAYLOAD_TYPE,
      payload: Buffer.from("{}").toString("base64"),
      signatures: [],
    };
    await expect(verifyEnvelope(env, [{ keyid: "x", publicKeyB64: "AAAA" }]))
      .rejects.toBeInstanceOf(ReceiptVerificationError);
  });

  it("rejects when keyid is not in the verifier set", async () => {
    const key = await generateSigningKey("legit");
    const env = await signReceipt(samplePayload(), key);
    await expect(
      verifyEnvelope(env, [{ keyid: "other-keyid", publicKeyB64: key.publicKeyB64 }]),
    ).rejects.toBeInstanceOf(ReceiptVerificationError);
  });

  it("rejects when payloadType is altered", async () => {
    const key = await generateSigningKey("k");
    const env = await signReceipt(samplePayload(), key);
    const bad = { ...env, payloadType: "application/json" };
    await expect(
      verifyEnvelope(bad, [{ keyid: key.keyid, publicKeyB64: key.publicKeyB64 }]),
    ).rejects.toBeInstanceOf(ReceiptVerificationError);
  });
});

describe("canonical encoding", () => {
  it("canonicalPayloadBytes is byte-stable per object", () => {
    const p = samplePayload(50);
    const a = canonicalPayloadBytes(p);
    const b = canonicalPayloadBytes(p);
    expect(Buffer.from(a).toString()).toBe(Buffer.from(b).toString());
  });

  it("pae output is deterministic", () => {
    const a = pae(RECEIPT_PAYLOAD_TYPE, new Uint8Array([1, 2, 3]));
    const b = pae(RECEIPT_PAYLOAD_TYPE, new Uint8Array([1, 2, 3]));
    expect(Buffer.from(a).toString("base64")).toBe(Buffer.from(b).toString("base64"));
  });
});
