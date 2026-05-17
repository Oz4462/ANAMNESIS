# @anamnesis/sdk (TypeScript)

Internal-only TypeScript client + DSSE receipt verifier for ANAMNESIS.
Not published to npm.

## Install (workspace-local)

```bash
cd anamnesis-ts
npm install
npm run typecheck
npm run test
npm run build
```

## Usage

```ts
import { AnamnesisClient, verifyEnvelope } from "@anamnesis/sdk";

const client = new AnamnesisClient({ baseUrl: "http://localhost:8000" });
const reuse = await client.reuse({
  tenant_id: "tenant-x",
  user_text: "How do I compute area of a triangle?",
  model: { provider: "anthropic", name: "claude-opus-4-7" },
  k: 5,
});

if (reuse.receipt_envelope) {
  const receipt = await verifyEnvelope(reuse.receipt_envelope, [
    { keyid: "anamnesis-server-default", publicKeyB64: process.env.ANAMNESIS_PUBKEY! },
  ]);
  console.log("EU AI Act 15:", receipt.eu_ai_act_claims.article_15);
}
```
