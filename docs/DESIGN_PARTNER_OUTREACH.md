# Design Partner Outreach Plan

Status: **PAUSED**. Repo is private. No outreach until owner explicitly
authorises.

When unfrozen, the first three candidates and the pitch frame are below.

## Candidates

| # | Company | Why | Best entry point |
|---|---------|-----|------------------|
| 1 | Harvey | Legal AI, reasoning-heavy workloads, EU client base (A&O Shearman et al.) → Article 15 exposure | Product / Eng lead, not Sales |
| 2 | Cursor | $3.5B raised on cost-escape thesis; Composer 1.5/2 exists to dodge API margin compression | Composer team, infra channel |
| 3 | Hebbia | Finance + regulated EU customers = compliance + cost dual hook | Eng/Platform team |

## Pitch frame

1. **Open with compliance, not cost.** EU AI Act Article 15 enforcement starts
   August 2026. Their existing observability stack (Langfuse / LangSmith) is
   not designed to produce notified-body-ready signed evidence.
2. **Quantify their cost-pain.** From public statements alone, point at the
   603-vs-60-token bloat case + Cursor Composer rationale.
3. **Show the demo.** Run the live notebook from `examples/`; show
   token-savings curve + a tampered-receipt rejection.
4. **Offer the SMB gainshare tier first.** Zero risk for them, easy yes.
   Upsell to enterprise tier once volume is established.

## What we do NOT do in outreach

- No public Show HN / Twitter / LinkedIn announcement until owner approves.
- No "official partner" claims attaching their logo to our materials.
- No price sheet in cold-outbound — wait for the second meeting.

## Tracking schema

When outreach starts, log per-prospect in this file:

```
- [Company] — Status: [contacted | demo-scheduled | pilot | signed | dead]
              Date: YYYY-MM-DD
              Owner: [name]
              Next action: [...]
              Notes: [...]
```
