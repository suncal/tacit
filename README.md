<div align="center">

<img src="site/favicon.svg" width="56" height="56" alt="">

# Tacit

**The verified work layer.**
Grade every AI in your company — including the ones you bought — against what your own team actually does.
Then let the proven ones work, and pay only for the actions that stood.

[![License](https://img.shields.io/badge/license-MIT-0B5C50)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-27%20passing-16794C)](api/tests)
[![Self-hosted](https://img.shields.io/badge/self--hosted-one%20process%2C%20one%20database-0B5C50)](#run-it)

</div>

---

Every company now pays two or three AI vendors and cannot tell whether any of them did the job right.
"Resolved" means the conversation ended. It does not mean it was correct.

Tacit has the only ground truth that matters: **what your own people do.** It learns the recurring jobs by
watching, then uses that standard two ways — to grade the AI you already bought, and to earn the work itself,
one job at a time.

```bash
git clone https://github.com/suncal/tacit && cd tacit
make setup && make demo     # http://127.0.0.1:4800 · demo@northwind.dev / tacit-demo
```

Python 3.12 + Node 22. No key required — there is a deterministic local brain so the whole harness runs
without a model. `docker compose up --build` also works.

## What it does

### 1. Oversight — free, read-only, works on anyone's agent

Register an AI that acts in a system Tacit can see (Sierra, Intercom Fin, Copilot, a homegrown agent). Its
actions arrive as ordinary events; the vendor is not involved and nothing on their side changes. Tacit grades
each action against the standard it learned from your team, and reports the number no vendor publishes:

> **Fin (Intercom)** — 52 actions, **48% needed a human afterwards**.
> Billed $0.99 each → **$1.91 per action that actually landed.**

### 2. Work — earned one job at a time

| Stage | What happens | How it gets there |
|---|---|---|
| **candidate** | a recurring pattern mined from history | `POST /playbooks/mine` |
| **shadow** | drafts silently; the owner's real reply scores each draft | you promote it — it costs nothing |
| **propose** | drafts land in an inbox with a change preview; a human approves each | trust ≥ 60% over ≥ 10 graded drafts (Wilson lower bound) |
| **auto** | acts alone, reversibly, within a budget | ≥ 10 approvals, ≤ 10% rejected, 0 undos |

Recommendations are computed, never applied. Demotion is recommended the same way. On auto, a trigger that
doesn't resemble the pattern is **escalated to a human anyway**. When a draft misses, Tacit asks the owner one
question and the answer becomes a rule that conditions every future draft.

**Backtest** replays the shadow engine over history you already have — "we would have handled 70% of last
quarter" — before anything acts.

### 3. Verified work — billing you can audit

An action is billable only once **a human approved it**, or it ran on a job that had earned autonomy and
**nobody reversed it inside the dispute window**. Reversed or refused work is credited permanently. Work a
person drove themselves is never billed. Every line names the action, the job, and the reason.

### 4. Evidence — EU AI Act art. 12 and 14, generated from the log

Enforceable since 2 August 2026. Tacit's audit log is append-only and **sealed into a hash chain**, so an
altered or removed record is detectable by anyone holding an earlier root. One call produces the bundle:
every system in scope, its autonomy level, the oversight that applies, approvals, refusals, escalations,
reversals — including for the third-party agents you supervise.

## Run it

```bash
make setup          # uv venv + npm install
make demo           # seeded demo org: 629 events, 5 mined jobs, 2 supervised vendors
make dev            # api :4800 with reload, vite :5173 proxying /api
make test           # 27 backend tests + typecheck
make migrate        # alembic upgrade head
```

Point it at your own team (polling — no public URL, no tunnels):

```bash
export TACIT_GITHUB_REPOS=acme/api           # or leave empty to use `gh auth token`
export TACIT_SLACK_CHANNELS=C0BILLING
export TACIT_ANTHROPIC_API_KEY=sk-…          # optional; without it the local brain runs
```

Feed anything else through the event API:

```bash
curl -X POST localhost:4800/api/v1/events -H 'Content-Type: application/json' \
  -d '{"system":"zendesk","kind":"message","actor":"priya","text":"…","thread_key":"zd:1234"}'
```

## Brains

| provider | how | when |
|---|---|---|
| `anthropic` | `TACIT_ANTHROPIC_API_KEY` | best — Claude Opus 5, native tool use, adaptive thinking |
| `claude-cli` | `TACIT_BRAIN_PROVIDER=claude-cli` | uses the `claude` subscription you already have |
| `openai-compatible` | `TACIT_BRAIN_BASE_URL` | Groq, OpenRouter, vLLM, anything |
| `local` | nothing | no model at all: drafts from your team's own past replies |

The harness — mining, shadow scoring, trust, approvals, budgets, undo, audit — behaves identically under all four.

## What a security review asks

- **Permissions** — every tool has a risk class (`read` / `write` / `exec`). Rules map `(principal, tool) → allow | ask | deny`; denied tools are never offered to the model.
- **Transactions** — every write records its inverse. Undo a run across systems in one click; the undo is audited too.
- **Budgets** — hard caps on writes/hour and $/day per principal, enforced before execution.
- **Replay** — re-run any recorded run against a new model with recorded tool results. A regression suite grown from production.
- **Data** — one SQLite or Postgres database on your infrastructure. Secrets are environment variables, never rows. `GET /api/v1/export` returns everything.

## Architecture

```
api/tacit/core/mining.py       events → candidate jobs (trigger signature, cadence, medoid reply, consistency)
api/tacit/core/shadow.py       draft on trigger · score against the human's real action · confidence + escalation
api/tacit/core/trust.py        Wilson lower bound · graduation and demotion recommendations
api/tacit/core/oversight.py    grade third-party agents · rework detection · retroactive regrading
api/tacit/core/ledger.py       verified-work accounting
api/tacit/core/compliance.py   hash-chained audit · art. 12/14 evidence bundle
api/tacit/core/opportunity.py  the Day-One report
api/tacit/core/agent.py        brain → policy → budget → tool (transaction) → audit · pause/resume · undo
api/tacit/connectors/          github · slack · linear (poll) · mcp (stdio)
api/tacit/routers/             FastAPI · OpenAPI at /api/docs · cookie sessions + hashed API keys
web/                           React 19 · TypeScript · Vite · Tailwind 4 · TanStack Query · Recharts
```

## Pricing (hosted)

Oversight is **free forever**, self-hosted or not: unlimited supervised agents, shadow mode, backtests.
Work is **$0.30 per verified action** — nothing else, and nothing for work a human took back.
A **compliance** tier adds signed evidence exports, auditor roles and SSO.

MIT licensed. Not affiliated with Intercom, Sierra, GitHub, Slack, Linear or Anthropic.
