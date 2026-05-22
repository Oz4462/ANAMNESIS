# LICENSE Change — 2026-05-22

## Summary

ANAMNESIS re-licensed from **All-Rights-Reserved (Pre-Alpha)** → **Apache License 2.0**.

## Authorization

This project is the sole work of Ozan Küsmez. The license change was authorized
by the copyright holder (Ozan Küsmez) on 2026-05-22 in the context of TRUST-OS
fusion-architecture planning.

User direktive: „Rest-Risiken auch fixxen planen umsetzen" (ANAMNESIS gehört
Ozan vollständig, Pre-Alpha-Status).

## Rationale

TRUST-OS is a fusion of 5 components (VCOS, VERIDEX, ANAMNESIS, Aegis-Veto,
AGORA) intended for joint pre-seed pitch and unified deployment. The previous
"All Rights Reserved" proprietary notice was incompatible with the TRUST-OS
unified-license architecture and blocked downstream open-source consumption,
SDK distribution, and community evaluation of the reference implementation.

Apache License 2.0 unifies the license across all 5 fusion components, enables
managed-service deployment (DACH-Mittelstand SaaS go-to-market), and aligns
with the existing licensing of Aegis-Veto, AGORA, and VCOS Spec.

## Preservation

The previous All-Rights-Reserved text is preserved at
`LICENSE.all-rights-reserved.backup` for historical and audit reference.

The git history that introduced and used the All-Rights-Reserved notice is
not rewritten.

## Effective Date

2026-05-22

## Impact

- Downstream consumers may now use, modify, and redistribute ANAMNESIS
  (Python SDK, FastAPI server, TypeScript SDK, web shell) under Apache-2.0.
- Downstream consumers may offer ANAMNESIS as a managed service.
- Apache-2.0 attribution requirements apply (preserve NOTICE files where
  present, retain copyright notices, include LICENSE in distributions).
- No patent restrictions imposed beyond Apache-2.0 default patent grant.
- DSSE receipt format, conformal-prediction calibration, and EU-AI-Act
  Article-15/50 receipts are all covered by the new license.

## Copyright

Copyright 2026 Ozan Küsmez. All rights reserved under Apache License 2.0.
