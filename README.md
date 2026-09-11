# Tacit

**The AI teammate that learns your job by watching, proves it can do it, and then asks to take over — one pattern at a time.**

Every "AI teammate" on the market asks you to trust it on day one. Tacit doesn't. It watches what your team
actually does in GitHub, Slack and Linear, mines the recurring jobs, and then **shadows** each one: it drafts what it
would have done and grades itself against what the human really did. No labelling — the human's real action is the
ground truth. When a job's trust score clears the bar, Tacit asks to graduate it: **shadow → propose → auto**. Every
auto action is a **transaction with undo**. Every run can be **replayed** against a new model without side effects.

```
git clone https://github.com/suncal/tacit && cd tacit
make setup && make demo        # http://127.0.0.1:4800 · demo@northwind.dev / tacit-demo
```

## The ladder

| stage | what happens | how it gets there |
|---|---|---|
| **candidate** | a recurring pattern mined from history (who, trigger, usual reply, cadence) | `POST /playbooks/mine` |
| **shadow** | every trigger produces a draft; the owner's real reply scores it | you tap "Move to Shadow" — it costs nothing |
| **propose** | drafts land in the Inbox with a change preview; a human approves each | trust ≥ 60% over ≥ 10 graded drafts (Wilson lower bound) |
| **auto** | acts on its own, reversibly, under a budget | ≥ 10 approvals, ≤ 10% rejected, 0 undos |

Recommendations are computed, never applied. Demotion is automatic-suggested too (undos, rejections).

**Backtest** runs the shadow engine over history you already have: "Tacit would have handled 79% of these" before a
single live draft exists.

## What a buyer's security team reads first

- **Permissions**: every tool has a risk class (`read` / `write` / `exec`). Rules are `(principal, tool) → allow | ask | deny`;
  `ask` pauses the run in the Inbox with a preview of exactly what will change (files get a unified diff).
- **Transactions**: every write records its inverse (`github_comment` → `github_delete_comment`, `file_write` → previous
  content, …). Undo a run in one click; the undo is audited too.
- **Budgets**: hard caps on writes/hour and $/day per principal pattern. No model can talk its way past them.
- **Audit**: append-only, exportable as JSONL. Who asked, what ran, what changed, whether it worked.
- **Replay**: re-run any recorded run against the current brain with recorded tool results — a regression suite grown
  from production.
- **Data**: one SQLite file (or Postgres). `GET /api/v1/export` hands you everything.
- **Brains**: Anthropic SDK (Claude Opus 5, native tool use), your `claude` CLI subscription, any OpenAI-style endpoint,
  or **none** — the deterministic local brain drafts from your own past replies so the whole harness is testable without a key.

## Architecture

```
api/tacit/core/mining.py     events → candidate playbooks (trigger signature, cadence, medoid reply, consistency)
api/tacit/core/shadow.py     draft on trigger · score against the human's real action · enact (propose/auto)
api/tacit/core/trust.py      Wilson lower bound · graduation & demotion recommendations
api/tacit/core/backtest.py   shadow over history, idempotent
api/tacit/core/agent.py      brain → policy → budget → tool (transaction) → audit · pause/resume on approval · undo
api/tacit/core/replay.py     recorded-tool replay, decision diff
api/tacit/core/brains/       anthropic · claude-cli · openai-compatible · local
api/tacit/connectors/        github · slack · linear (poll, no public URL) · mcp (stdio)
api/tacit/routers/           FastAPI, OpenAPI at /api/docs, cookie sessions + API keys
web/                         React 19 · TypeScript · Vite · Tailwind 4 · TanStack Query · Recharts
```

## Feed it anything

```
curl -X POST localhost:4800/api/v1/events -H "Authorization: Bearer tk_…" -H "Content-Type: application/json" \
  -d '{"system":"zendesk","kind":"message","actor":"priya","text":"…","target":"billing","thread_key":"zd:1234"}'
```
Any system whose actions you can describe as `(actor, kind, text, thread)` can be watched and, eventually, delegated.

## Develop

```
make setup      # uv + npm
make dev        # api :4800 with reload, vite :5173 proxying /api
make test       # 16 backend tests + typecheck
make migrate    # alembic upgrade head
docker compose up --build
```

MIT.
