// Stand-alone DSSE receipt verifier. No server contact required.
// Uses @noble/ed25519 (audited, zero-dep).

import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha2";

import type { ReceiptPayload, SignedEnvelope } from "./types.js";

// @noble/ed25519 v2.x requires us to wire a SHA-512 implementation explicitly.
ed.etc.sha512Sync = (...m: Uint8Array[]) => sha512(ed.etc.concatBytes(...m));
ed.etc.sha512Async = async (...m: Uint8Array[]) => sha512(ed.etc.concatBytes(...m));

export const RECEIPT_PAYLOAD_TYPE = "application/vnd.anamnesis.receipt+json";

/** Pre-Authentication Encoding from the DSSE spec. */
export function pae(payloadType: string, payload: Uint8Array): Uint8Array {
  const enc = new TextEncoder();
  const tBytes = enc.encode(payloadType);
  const prefix = enc.encode("DSSEv1 " + tBytes.length + " ");
  const middle = enc.encode(" " + payload.length + " ");
  const out = new Uint8Array(prefix.length + tBytes.length + middle.length + payload.length);
  let i = 0;
  out.set(prefix, i); i += prefix.length;
  out.set(tBytes, i); i += tBytes.length;
  out.set(middle, i); i += middle.length;
  out.set(payload, i);
  return out;
}

function fromB64(s: string): Uint8Array {
  if (typeof Buffer !== "undefined") return new Uint8Array(Buffer.from(s, "base64"));
  const bin = atob(s);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return arr;
}

export class ReceiptVerificationError extends Error {}

export interface VerifierKey {
  keyid: string;
  /** Raw 32-byte Ed25519 public key, base64-encoded. */
  publicKeyB64: string;
}

/** Verify a SignedEnvelope and return the inner ReceiptPayload. */
export async function verifyEnvelope(
  envelope: SignedEnvelope,
  keys: VerifierKey[],
): Promise<ReceiptPayload> {
  if (envelope.payloadType !== RECEIPT_PAYLOAD_TYPE) {
    throw new ReceiptVerificationError(`unexpected payloadType ${envelope.payloadType}`);
  }
  if (!envelope.signatures.length) {
    throw new ReceiptVerificationError("no signatures present");
  }
  const payloadBytes = fromB64(envelope.payload);
  const paeBytes = pae(envelope.payloadType, payloadBytes);

  const keyMap = new Map(keys.map((k) => [k.keyid, fromB64(k.publicKeyB64)]));

  let lastError: unknown;
  for (const sigEntry of envelope.signatures) {
    const pub = keyMap.get(sigEntry.keyid);
    if (!pub) continue;
    try {
      const ok = await ed.verifyAsync(fromB64(sigEntry.sig), paeBytes, pub);
      if (ok) {
        const text = new TextDecoder().decode(payloadBytes);
        return JSON.parse(text) as ReceiptPayload;
      }
    } catch (e) {
      lastError = e;
    }
  }
  throw new ReceiptVerificationError(
    `verification failed${lastError ? ": " + String(lastError) : ""}`,
  );
}

/** Compute the deterministic sha256-style content hash of a payload object. */
export function canonicalPayloadBytes(receipt: ReceiptPayload): Uint8Array {
  return new TextEncoder().encode(JSON.stringify(sortKeysDeep(receipt)));
}

function sortKeysDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeysDeep);
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    return Object.keys(obj)
      .sort()
      .reduce<Record<string, unknown>>((acc, k) => {
        acc[k] = sortKeysDeep(obj[k]);
        return acc;
      }, {});
  }
  return value;
}
