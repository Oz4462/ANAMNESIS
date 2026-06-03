# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Portable VCOS-conformant Sign/Verify for HONEST_CLAIMS.md.

Adapted from VERIDEX/agents/sign_claims.py (179 LoC).
Made portable: no backend-dependency. Uses cryptography library directly.

Threat model: a contributor (or an LLM) edits HONEST_CLAIMS.md without
re-running the honesty auditor or earning approval from a key holder.
The signature catches this:
  * Anybody can change the markdown.
  * Only a holder of the private key can produce a valid `.sig` for the new content.
  * CI rejects a commit where the markdown changed but the signature did not verify.

Schema:
  - public key:    `tools/keys/honesty_pub.pem`   (committed)
  - private key:   `tools/keys/honesty_priv.pem`  (gitignored)
  - signature:     `HONEST_CLAIMS.sig`            (committed; base64 Ed25519 sig of SHA-256)
  - sidecar:       `HONEST_CLAIMS.sig.json`       (committed; key-fingerprint + iso-timestamp)

VCOS-Spec §5 normative reference (when adopted).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
except ImportError as exc:
    print(f"ERROR: cryptography library required. Install: pip install cryptography\n  {exc}", file=sys.stderr)
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CLAIMS = REPO_ROOT / "HONEST_CLAIMS.md"
DEFAULT_PUB = REPO_ROOT / "tools" / "keys" / "honesty_pub.pem"
DEFAULT_PRIV = REPO_ROOT / "tools" / "keys" / "honesty_priv.pem"
DEFAULT_SIG = REPO_ROOT / "HONEST_CLAIMS.sig"
DEFAULT_SIDECAR = REPO_ROOT / "HONEST_CLAIMS.sig.json"


def _content_digest(path: Path) -> bytes:
    """SHA-256 of file bytes — no normalization. Editing whitespace WILL invalidate the signature."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.digest()


def _key_fingerprint(pub_pem: bytes) -> str:
    return hashlib.sha256(pub_pem).hexdigest()[:16]


def _generate_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    priv = Ed25519PrivateKey.generate()
    return priv, priv.public_key()


def _serialize_private_key(priv: Ed25519PrivateKey, password: bytes | None = None) -> bytes:
    enc = serialization.BestAvailableEncryption(password) if password else serialization.NoEncryption()
    return priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=enc,
    )


def _serialize_public_key(pub: Ed25519PublicKey) -> bytes:
    return pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _load_private_key(pem: bytes, password: bytes | None = None) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem, password=password)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError(f"expected Ed25519PrivateKey, got {type(key).__name__}")
    return key


def _load_public_key(pem: bytes) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError(f"expected Ed25519PublicKey, got {type(key).__name__}")
    return key


def generate_keypair(priv_path: Path, pub_path: Path, password: bytes | None = None) -> None:
    if priv_path.exists() or pub_path.exists():
        raise FileExistsError(f"refusing to overwrite existing keys at {priv_path} / {pub_path}")
    priv_path.parent.mkdir(parents=True, exist_ok=True)
    priv, pub = _generate_keypair()
    priv_path.write_bytes(_serialize_private_key(priv, password=password))
    pub_path.write_bytes(_serialize_public_key(pub))


def sign(
    claims_path: Path,
    priv_path: Path,
    sig_path: Path,
    sidecar_path: Path,
    password: bytes | None = None,
) -> dict:
    if not claims_path.exists():
        raise FileNotFoundError(f"claims file not found: {claims_path}")
    if not priv_path.exists():
        raise FileNotFoundError(f"private key not found: {priv_path}")

    digest = _content_digest(claims_path)
    priv = _load_private_key(priv_path.read_bytes(), password=password)
    sig = priv.sign(digest)
    sig_path.write_text(base64.b64encode(sig).decode("ascii") + "\n", encoding="utf-8")

    pub_pem_bytes = _serialize_public_key(priv.public_key())
    sidecar = {
        "claims_file": str(claims_path.name),
        "digest_sha256_hex": digest.hex(),
        "signature_b64": base64.b64encode(sig).decode("ascii"),
        "public_key_fingerprint_sha256_16": _key_fingerprint(pub_pem_bytes),
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "Ed25519",
        "spec": "VCOS/0.1",
    }
    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8")
    return sidecar


def verify(claims_path: Path, pub_path: Path, sig_path: Path) -> tuple[bool, str]:
    if not claims_path.exists():
        return False, f"claims file missing: {claims_path}"
    if not pub_path.exists():
        return False, f"public key missing: {pub_path}"
    if not sig_path.exists():
        return False, f"signature missing: {sig_path}"

    digest = _content_digest(claims_path)
    pub = _load_public_key(pub_path.read_bytes())
    try:
        sig = base64.b64decode(sig_path.read_text(encoding="utf-8").strip().encode("ascii"))
    except Exception as exc:
        return False, f"signature is not valid base64: {exc}"

    try:
        pub.verify(sig, digest)
        return True, f"signature OK (digest {digest.hex()[:16]}...)"
    except InvalidSignature:
        return False, "signature does NOT verify — HONEST_CLAIMS.md was modified without re-signing"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Sign / verify HONEST_CLAIMS.md (VCOS/0.1)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("keygen", help="generate a fresh Ed25519 keypair")
    p_gen.add_argument("--priv", default=str(DEFAULT_PRIV))
    p_gen.add_argument("--pub", default=str(DEFAULT_PUB))

    p_sign = sub.add_parser("sign", help="sign HONEST_CLAIMS.md")
    p_sign.add_argument("--claims", default=str(DEFAULT_CLAIMS))
    p_sign.add_argument("--priv", default=str(DEFAULT_PRIV))
    p_sign.add_argument("--sig", default=str(DEFAULT_SIG))
    p_sign.add_argument("--sidecar", default=str(DEFAULT_SIDECAR))

    p_verify = sub.add_parser("verify", help="verify HONEST_CLAIMS.sig")
    p_verify.add_argument("--claims", default=str(DEFAULT_CLAIMS))
    p_verify.add_argument("--pub", default=str(DEFAULT_PUB))
    p_verify.add_argument("--sig", default=str(DEFAULT_SIG))

    args = p.parse_args(argv)

    if args.cmd == "keygen":
        try:
            generate_keypair(Path(args.priv), Path(args.pub))
        except FileExistsError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"wrote {args.priv} and {args.pub}")
        return 0

    if args.cmd == "sign":
        sidecar = sign(Path(args.claims), Path(args.priv), Path(args.sig), Path(args.sidecar))
        print(json.dumps(sidecar, indent=2, sort_keys=True))
        return 0

    if args.cmd == "verify":
        ok, msg = verify(Path(args.claims), Path(args.pub), Path(args.sig))
        print(msg)
        return 0 if ok else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
