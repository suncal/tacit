# Tacit — what "complete working model" means for the TSM pitch (2026-10-12)

State today (verified this session): 39 tests green, hosted demo live at tacit-demo-km3d.onrender.com,
~6,400 lines of backend, connectors for GitHub/Slack/Linear/MCP written, Anthropic key wired.
Everything proven so far runs on the seeded "Northwind Labs" org. That is the gap: no evidence from real traffic.

## Must-have before recording (converts demo → TRL 6 evidence)

1. **Real-data proof via GitHub backfill.** Add `tacit backfill-github owner/repo --since 2025-01-01` (the poller
   only reads forward from the last hour). Run it on a public repo with real maintainer traffic, mine, backtest with
   the judge, and replace every [DEMO] figure in script.md with those numbers. Public OSS issue data is unclassified
   and carries no markings. ~1 day. Only item I can finish without you.
2. **One live Slack workspace end-to-end.** DONE on Tacit's side (12 Oct): Socket Mode client, thread pairing,
   export importer, app manifest, 5 tests. VERIFIED LIVE 12 Oct on the "Tacit Demo" workspace: Socket Mode connect,
   message ingest with real names, @mention → threaded reply, console-gated slack_post approved from the Inbox,
   undo removed the post, oversight-quality logged the approval as "considered" (11.6 s read vs 4.3 s needed).
   SHADOW FLOW VERIFIED LIVE (12 Oct, #invoices, brain = Claude via CLI subscription): 3 ask/reply pairs from two
   humans → mined "Resend client invoice copy" (3 examples) → promoted to shadow → 4th ask drafted in 12 s, nothing
   posted → human replied → judge 1.00 ("same action, same payment terms, same file location"), overlap only 0.61.
   Miner fix from this run: stemmed-word similarity for paraphrase families. Ready to film.
3. **Postgres run verified.** Compose already declares it but it has never been exercised; no Postgres on this Mac
   and no Docker. Easiest: Render free Postgres attached to the hosted demo, run Alembic migrations, re-seed.
   Needs your Render dashboard once. ~2 hours.
4. **Secrets and demo hygiene.** Rotate the Anthropic key that was pasted in a chat transcript; confirm the
   hosted demo has no key and no shell tools (TACIT_DEMO_MODE). ~30 minutes.

## Should-have (strengthens the 35% criterion and the "government-deployable" story)

5. **Generic agent adapter for Oversight.** Today third-party agents report through the Event API. Add an
   OpenTelemetry/OTLP span receiver so any instrumented agent (LangGraph, Copilot, homegrown) is supervised with
   zero code. This is the "cross-platform governance" gap named in the acquisition research. ~2 days.
6. **Auditor role + signed evidence export.** The compliance tier is a claim. Implement a read-only auditor role and
   sign the evidence bundle (Ed25519) so the bundle verifies offline. ~1 day.
7. **Container hardening.** DONE (12 Oct): bases pinned by digest, deps from a hash-checked lock, non-root uid 10001,
   no pip at runtime, SBOM + Trivy gate in CI (0 open alerts), image at ghcr.io/suncal/tacit.
8. **Name and domain.** "Tacit" is still a working name; check trademark conflict and buy a domain before the
   video's title card locks it. Your call.

## Nice-to-have (after awardable)

9. SSO/OIDC (login.gov / Azure AD) for the compliance tier.
10. A 2-week pilot with one real team (a friend's startup is enough). A single real case study is the strongest
    possible evidence for criterion 3 and the thing assessors most often say is missing.

## Submission logistics
- Submit as New TSM Submission under P CHAK Consulting (UEI from SAM.gov), small business → nontraditional, FOCI no.
- FedRAMP: Not applicable. ATO: Sponsor required. IL: Not currently authorized. FCL: none. These do not affect scoring.
- Keywords: AI agent governance, human oversight, audit trail, agent evaluation, autonomy, MCP, responsible AI.
- Submit before Oct 25 to leave room for a compliance bounce before the Oct 31 noon EST cutoff.
