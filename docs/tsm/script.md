# Tacit — Tradewinds Solutions Marketplace video script (v2, real-data numbers)

Target: 4:50. Focus area: **AI Agent Networks for Mission Superiority** (secondary: Streamlining business processes).
TRL claimed: **6** — prototype demonstrated in a relevant environment (live console, real tool integrations, hosted instance, backtest on a real public repository).
Format: 1920x1080 mp4 < 1 GB, Rec709. Copyright notice only. No pricing beyond what is already public on the site.
Every figure below comes from `docs/tsm/evidence/nextjs.json` (vercel/next.js public issue tracker, history since 1 Jul 2026, run 12 Oct 2026) or from the open repo. The one remaining demonstration-org figure is marked [DEMO] and said so on screen. Public issue-tracker data is unclassified and carries no markings.

---

## 1. Defining the problem — 0:00–0:40 (rubric 15%)

[Screen: title card "Tacit — AI teammates that earn autonomy", then a plain slide of three stats with citations on screen]

NARRATION:
"Every organization is deploying AI agents faster than it can supervise them. Okta's 2025 survey found 87 percent of enterprises encourage agent use but only 47 percent govern it. Gravitee found 88 percent had an agent incident, and half of their agents keep no logs at all.

The Department of War faces the same gap at a larger scale. The CDAO wants agent networks for battle management, targeting, and the business processes behind them. But every agent that acts on a mission system raises the same three questions: has it earned the right to act on its own, is the human approving it actually looking, and can an auditor prove either one afterwards?

Today those questions are answered by trust, not evidence. Tacit replaces that with a record."

## 2. Accelerating the mission — 0:40–2:40 (rubric 40%)

[Screen: live console, Overview page]

NARRATION:
"Tacit is a governance runtime for AI teammates. It sits read-only on the tools a team already uses, GitHub, Slack, Linear, or any system through an event API or MCP, and it does three things.

[Screen: Shadow page, playbook list for vercel/next.js]
First, it learns the job by shadowing. It clusters recurring human actions into playbooks, then for every new trigger it drafts what it would have done and grades that draft against what the human actually did. No labelling, no training set.

We pointed it at a real public repository, the Next.js issue tracker, three months of history: 9,569 human events, 5,878 threads, 2,800 people. It found 28 recurring jobs. One maintainer alone had answered 1,358 bug reports with the same job: verify the reproduction, then close with findings.

[Screen: Shadow page, one playbook with the Judge reasoning panel]
Then it backtested: 117 real triggers, drafted by a frontier model, graded by a separate judge model that asks one question: would this draft have done the same job? The judge said yes 40 percent of the time overall. Two jobs it would have handled every time: locking stale closed issues, 13 of 13, and claiming open bugs for a fix, 8 of 8. The hard job, verify and close, it handled 5 times in 25.

[Screen: the judge's reasons, three rows]
Why so low? Because the judge caught the model making things up. Its words: 'Draft cites a different PR number and rationale.' 'Draft invents a different root cause rather than citing the actual fix PRs.' 'Draft gives a fabricated reason instead of the actual reason the component was removed.' Word-overlap scoring would have passed several of those. The judge did not.

[Screen: Playbook trust ladder: shadow → propose → auto]
Second, autonomy is earned per job, never granted per agent. Trust is a Wilson lower bound on judged results. On that repository, two jobs would qualify for promotion. The other six stay in shadow until the evidence changes. A job moves from shadow to propose, where a human approves each action from a preview, and only then to auto, where actions run as transactions with undo under budgets. Undos and rejections demote it. Editing a playbook resets its trust, because the evidence belonged to the old definition.

[Screen: Oversight Quality page, reviewer table with the 1.3-second reviewer highlighted]
Third, it measures the human, not just the machine. An approval granted faster than the preview could be read is logged as unread and excluded from promotion evidence. In our demonstration org, one reviewer's decisions fell from 20 seconds to 1.3 seconds and 64 percent were unread. Without this, rubber-stamping would have promoted the job. [DEMO, say "demonstration" on screen]

[Screen: Oversight page, third-party agent fleet]
The same supervision works on agents Tacit did not build. Point it at a vendor agent's output and it reports rework rate, how often a human had to step in afterwards, against what the vendor claimed.

Dependencies: a frontier model for drafting and judging, run through any OpenAI-compatible or Anthropic endpoint, including government-hosted ones, or a local deterministic brain with no model at all. Everything else is one container and one database, SQLite or Postgres, on your infrastructure. Risk is managed by design: Tacit never acts without an earned trust record, and every action is reversible."

## 3. Advancing the state of the art — 2:40–4:15 (rubric 35%)

[Screen: comparison slide, four columns]

NARRATION:
"How is this different from what exists?

Outcome-priced agents such as Sierra and Intercom Fin sell resolutions, but a resolution only means the conversation ended. They cannot tell you whether a human had to redo the work. Tacit's unit is the verified action: billed only if a human approved it or nobody reversed it within a dispute window.

Evaluation platforms such as LangSmith, Braintrust, and Arize score the model offline against a fixed dataset. Tacit scores online against the human's real reply, continuously, and uses that score to decide autonomy. No eval platform gates permissions on its own results.

Platform governance from Copilot Studio or Agentforce only governs agents on that platform. Tacit supervises any agent from read-only events, so a mixed fleet from several vendors gets one standard.

And to our knowledge no product measures oversight quality. The idea exists in a 2026 academic paper as an index; Tacit ships it, and makes it consequential by excluding unread approvals from trust.

[Screen: Compliance page, hash-chained audit, evidence bundle]
The audit log is append-only and hash-chained, so tampering is detectable, and it generates an evidence bundle on demand. We built it against EU AI Act articles 12 and 14, in force since August 2026, and it maps directly to the Department's Responsible AI principle of governable systems.

Evidence: the code is open under MIT at github.com/suncal/tacit with 41 automated tests, a hosted instance anyone on this panel can log into today, and the Next.js backtest published in full, including the 60 percent the model got wrong and the judge's reason for each. We publish the misses because a governance tool that oversells its own model is not a governance tool."

## 4. Business model — 4:15–4:50 (rubric 10%)

[Screen: pricing slide as published on the site]

NARRATION:
"Tacit is self-hosted software with public pricing. Oversight of third-party agents is free forever. Earned work is priced per verified action, so the customer pays only for actions a human accepted or did not reverse. A compliance tier adds signed evidence exports, auditor roles, and SSO. Enterprise and government customers run it inside their own VPC or on-premises, so no mission data leaves their boundary. The same model applies to commercial and government buyers.

For the Department we propose a prototype OT: a 90-day deployment on one business-process workflow, measured by the Day One report Tacit produces before any automation is turned on."

## Close — 4:50–5:00

[Screen: P CHAK Consulting, Tacit mark, contact, "© 2026 P CHAK Consulting LLC"]
"Tacit. Autonomy that is earned, oversight that is measured, evidence that is generated. Thank you."

---

## Numbers used, and where each comes from
| Figure | Value | Source |
|---|---|---|
| Human events / threads / people | 9,569 / 5,878 / 2,800 | evidence/nextjs.md |
| Recurring jobs mined | 28 | evidence/nextjs.json `mine.found` |
| One maintainer's triage replies | 1,358 | events table, actor marcoshernanz |
| Real triggers judged (7 fully judged jobs) | 117, 47 handled = 40% | evidence/nextjs.md caveat; 142 / 33% if the budget-interrupted 8th job is included |
| Lock stale closed issues | 13 / 13 | evidence/nextjs.md |
| Claim open bugs for a PR | 8 / 8 | evidence/nextjs.md |
| Verify repro and close | 5 / 25 | evidence/nextjs.md |
| Judge quotes | verbatim | drafts.score_detail.why in api/nextjs.db |
| Tests | 41 | `pytest` on this commit |
| Reviewer 20s → 1.3s, 64% unread | [DEMO] | seeded org, Oversight Quality page |

## On-screen citation list (show as footers when quoted)
- Okta, "AI at Work" 2025 — 87% encourage / 47% govern
- Gravitee, State of Agentic AI 2025 — 88% incident, ~50% no logging
- EU AI Act, Regulation (EU) 2024/1689, arts. 12 and 14, applicable 2 Aug 2026
- DoD Responsible AI principles (Feb 2020): Responsible, Equitable, Traceable, Reliable, Governable
- github.com/suncal/tacit — tests, backtest report, judge reasons
