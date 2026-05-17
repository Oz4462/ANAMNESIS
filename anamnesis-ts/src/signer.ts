// Optional Ed25519 DSSE signer for TypeScript. Mirrors the Python signer in
// receipts.py so a Node-side tool can issue receipts that any Python
// verifier accepts (and vice versa).

import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha2";

import { pae, RECEIPT_PAYLOAD_TYPE, canonicalPayloadBytes } from "./receipts.js";
import type { ReceiptPayload, SignedEnvelope } from "./types.js";

ed.etc.sha512Sync = (...m: Uint8Array[]) => sha512(ed.etc.concatBytes(...m));
ed.etc.sha512Async = async (...m: Uint8Array[]) => sha512(ed.etc.concatBytes(...m));

function toB64(buf: Uint8Array): string {
  if (typeof Buffer !== "undefined") return Buffer.from(buf).toString("base64");
  let bin = "";
  for (const b of buf) bin += String.fromCharCode(b);
  return btoa(bin);
}

function fromB64(s: string): Uint8Array {
  if (typeof Buffer !== "undefined") return new Uint8Array(Buffer.from(s, "base64"));
  const bin = atob(s);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return arr;
}

export interface SigningKey {
  keyid: string;
  seedB64: string;
  publicKeyB64: string;
}

/** Generate a fresh Ed25519 keypair encoded as base64. */
export async function generateSigningKey(keyid: string): Promise<SigningKey> {
  const seed = ed.utils.randomPrivateKey();
  const pub = await ed.getPublicKeyAsync(seed);
  return {
    keyid,
    seedB64: toB64(seed),
    publicKeyB64: toB64(pub),
  };
}

/** Recover an existing keypair from a base64-encoded 32-byte seed. */
export async function signingKeyFromSeedB64(seedB64: string, keyid: string): Promise<SigningKey> {
  const seed = fromB64(seedB64);
  const pub = await ed.getPublicKeyAsync(seed);
  return { keyid, seedB64, publicKeyB64: toB64(pub) };
}

/** Sign a ReceiptPayload and return a DSSE envelope identical in wire shape
 *  to the Python ReceiptSigner output. */
export async function signReceipt(
  receipt: ReceiptPayload,
  key: SigningKey,
): Promise<SignedEnvelope> {
  const payloadBytes = canonicalPayloadBytes(receipt);
  const paeBytes = pae(RECEIPT_PAYLOAD_TYPE, payloadBytes);
  const sig = await ed.signAsync(paeBytes, fromB64(key.seedB64));
  return {
    payloadType: RECEIPT_PAYLOAD_TYPE,
    payload: toB64(payloadBytes),
    signatures: [{ keyid: key.keyid, sig: toB64(sig) }],
  };
}
