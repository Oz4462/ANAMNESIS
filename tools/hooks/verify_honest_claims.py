#!/usr/bin/env python3
# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Pre-commit / CI hook: verify HONEST_CLAIMS.sig against HONEST_CLAIMS.md.

VCOS-Spec §5 normative.

Failure modes:
  - HONEST_CLAIMS.md modified but HONEST_CLAIMS.sig not    -> FAIL
  - signature exists but does not verify against public key -> FAIL
  - public key missing                                       -> FAIL
  - both files missing                                       -> WARN (bootstrap case)
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents import sign_claims  # noqa: E402


def main() -> int:
    claims = REPO_ROOT / "HONEST_CLAIMS.md"
    pub = REPO_ROOT / "tools" / "keys" / "honesty_pub.pem"
    sig = REPO_ROOT / "HONEST_CLAIMS.sig"

    if not claims.exists():
        print("HONEST_CLAIMS.md not found at repo root — nothing to verify.", file=sys.stderr)
        return 0

    if not pub.exists() or not sig.exists():
        print(
            "WARN: HONEST_CLAIMS signing not yet bootstrapped (missing pub key or signature).\n"
            "Run: python -m agents.sign_claims keygen && python -m agents.sign_claims sign",
            file=sys.stderr,
        )
        return 0

    ok, msg = sign_claims.verify(claims, pub, sig)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
