# Security Policy

ANAMNESIS implements EU AI Act Article 15 audit-trail receipts with
DSSE Ed25519 signing. Security is a primary concern.

## Supported Versions

| Version | Supported |
|---|---|
| 0.1.x | yes |
| < 0.1 | no |

## Reporting a Vulnerability

If you discover a security vulnerability, please email
**ozanks20@gmail.com** with the subject `[SECURITY] ANAMNESIS`.

Do **not** open a public GitHub issue for security reports.

### What to include

- Affected version + commit SHA
- Reproduction steps or proof-of-concept
- Suggested mitigation if known

### What to expect

- Acknowledgment within 72 hours
- Coordinated disclosure window: 90 days from triage
- CVE coordination if applicable
- Credit in CHANGELOG.md unless reporter prefers anonymity

## Cryptographic Primitives

ANAMNESIS receipts are signed with **Ed25519 (RFC 8032)** via PyNaCl /
libsodium. The receipt-chain is SHA-256 hash-linked (NIST FIPS 180-4).

Key-rotation is supported via the F19 KeyStore (commit `8564e4c`) with
monotonic `key_generation` counters to detect rollback attacks.

## Scope

In scope:
- Receipt-signing key compromise paths
- Receipt-chain tampering
- SDK injection paths (Anthropic / OpenAI / DeepSeek)
- Conformal-bound bypass via crafted inputs

Out of scope:
- Vulnerabilities in upstream LLM providers
- Social engineering against operators
- Physical access to the operator's host

## References

- TRUST-OS Threat-Model: `../TRUST-OS/docs/security/2026-05-22-threat-model-stride.md`
- F19 KeyStore Spec: `../TRUST-OS/docs/specs/2026-05-22-key-rotation-interface.md`
- F20 verify_chain Spec: `../TRUST-OS/docs/specs/2026-05-22-verify-chain-interface.md`
