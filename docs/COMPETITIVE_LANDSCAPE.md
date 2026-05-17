# Competitive Landscape (2026-05-17)

Source: three sub-agent research reports executed at project start.

## Summary verdict

- **Algorithmic moat: gone.** 5+ direct academic precedents in 2024-2026
  (T3, REMem, ArcMemo, ToTAL, Procedural-Knowledge-at-Scale, ProcMEM,
  AgentFly). Anyone who reads three of these papers can rebuild the core
  reuse mechanism in 3 weeks.
- **Commercial whitespace: real but narrow.** No SaaS or SDK ships the
  combination of (a) multi-provider capture, (b) Ed25519 signed receipts,
  (c) conformal correctness bound, (d) pay-on-savings billing.
- **Time window: 6-12 months.** Watch Zaharia/Databricks (T3 paper authors),
  Anthropic/OpenAI (could bolt onto existing caches), Langfuse/LangSmith
  (could extend observability → reuse).

## Category breakdown

### LLM memory frameworks
| Vendor | Stores | Reasoning traces? |
|--------|--------|-------------------|
| Mem0 | user/session/agent facts | no |
| Zep | temporal knowledge graph | no |
| Letta (MemGPT) | editable memory blocks | no |
| Cognee | GraphRAG over documents | no |
| OpenAI / Anthropic native | user preferences | no |

All store facts. None capture the `<think>` block from R1, o1's reasoning
summary, or Claude's `thinking` content as a first-class retrievable asset.

### LLM observability
LangSmith, Langfuse (acquired by ClickHouse Jan 2026), Arize Phoenix,
Helicone, W&B Weave, Braintrust — log reasoning steps as parent-child spans,
allow replay. None do **cross-query semantic retrieve-then-reuse**.

### Reasoning-cache / distillation OSS
| Repo | What it does | Gap vs Anamnesis |
|------|--------------|------------------|
| Narabzad/t3 (Arabzadeh + Zaharia, arXiv 2605.03344, May 2026) | Caches reasoning traces from Gemini-2-thinking / QwQ-32B as retrieval corpus; +56% AIME, -15% inference cost. | Research repo, no SDK, no receipts, no multi-provider, no compliance. |
| ReasoningPathCompression, R-KV, LazyEviction, MemoSight, STEP | KV-cache compression within a single inference. | Different problem entirely (intra-inference, not cross-query). |
| Thinking with Reasoning Skills (arXiv 2604.21764) | Distils skills from traces, retrieves at inference. | Research only. |

### Compliance / audit-trail crypto
SYEN Comply, VeritasChain, Nono — ed25519/Merkle-signed AI decision logs for
MiFID II / EU AI Act. Sign **decisions and inputs**, not reasoning traces,
no retrieval-reuse. Crypto layer is commoditised; our defensibility comes
from coupling it with the reasoning-reuse layer.

### Vendor announcements
- Anthropic: Extended Thinking is shipped, prompt-caching exists but
  invalidates on thinking-budget change.
- OpenAI: o1/o3 expose `usage.reasoning_tokens` but no storage/reuse product.
- DeepSeek: emits `<think>` inline, no storage/reuse product.
- Google / Mistral: nothing announced.

## Market sizing (sub-agent report)

- Realistic 5-year TAM: ~$67M ARR. Stretch: ~$450M.
  Math: ~3000 enterprises >$1M/yr reasoning spend × 50% addressable × 30%
  savings × 15% take rate.
- EU AI Act audit-trail upsell adds ~$75M overlay.
- Comparable raises:
    - Mem0: $24M Seed+A on memory-layer thesis alone (Oct 2025, no
      compliance angle, no reasoning-cache angle).
    - Cursor: $3.5B raised on cost-escape thesis (their Composer 1.5/2
      release exists explicitly to escape API margin compression).
    - Cognition/Devin: repriced $500/mo to $20 + $2.25/ACU after compute
      reality hit.

## Pricing model derived from comparables

- **OSS SDK (Apache 2.0)** for adoption — Mem0/Helicone/Langfuse pattern.
- **SaaS tiers**:
    - SMB: 15-20% gainshare of saved-token cost.
    - Mid-market: $2-10K/mo flat.
    - Enterprise: $50-150K/yr with EU-AI-Act-compliance pack.
- **Signed audit-trail add-on**: $30-50K/yr, slots into Credo/Trustible band.

## Top design-partner candidates (no outreach yet — private build)

1. **Harvey** — legal, reasoning-heavy, EU clients need Article 15.
2. **Cursor** — proven willingness to pay to escape reasoning-token economics.
3. **Hebbia** — finance + regulated EU customers = compliance + cost dual hook.

## Risk dashboard

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Zaharia/Databricks productises T3 | medium (6-12mo) | high | Compliance + multi-provider moat |
| Anthropic/OpenAI bolt reasoning-memory onto cache | high (3-6mo) | medium-high | Provider lock-in cuts against multi-vendor neutrality |
| Langfuse/LangSmith extend observability → reuse | medium (6-12mo) | high | They are observability-DNA, not compliance/crypto |
| EU AI Act enforcement slips | low | high | Cost savings alone justify ROI |
| Pay-on-savings unmeasurable | medium | medium | Receipts encode ex-ante and ex-post token deltas |
| Customer worries about trace privacy | low | high | On-prem SDK option + zero-trust server (customer key encrypts) |

## Sources

(See `docs/competitive-landscape-sources.md` if expanded later. Inline
citations preserved in the original research-agent transcripts; archive of
agent outputs available on request.)
