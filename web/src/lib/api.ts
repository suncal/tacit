/** Typed API client. One place knows about /api/v1. */
const BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) }, ...init })
  if (r.status === 204) return undefined as T
  const text = await r.text()
  let body: unknown = null
  try { body = text ? JSON.parse(text) : null } catch { body = text }
  if (!r.ok) {
    const detail = (body as { detail?: unknown })?.detail
    throw new ApiError(r.status, typeof detail === 'string' ? detail : Array.isArray(detail) ? (detail as { msg: string }[]).map(d => d.msg).join(', ') : r.statusText)
  }
  return body as T
}

export const api = {
  get: <T>(p: string) => req<T>(p),
  post: <T>(p: string, body?: unknown) => req<T>(p, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(p: string, body?: unknown) => req<T>(p, { method: 'PATCH', body: body === undefined ? undefined : JSON.stringify(body) }),
  del: <T>(p: string) => req<T>(p, { method: 'DELETE' }),
}

// ---------------------------------------------------------------- types
export type Stage = 'candidate' | 'shadow' | 'propose' | 'auto' | 'retired'
export interface Trust { scored: number; hits: number; hit_rate: number; mean_score: number; trust: number; approvals: number; rejections: number; approval_rate: number | null; executions: number; undos: number }
export interface Recommendation { to: Stage; why: string }
export interface Example { trigger: string; response: string; ts: number }
export interface Playbook {
  id: string; name: string; summary?: string; system: string; actor: string; stage: Stage
  trigger: { mode: 'reply' | 'schedule'; kind?: string; keywords?: string[]; target?: string; match?: string; cadence?: { human: string } }
  response: { kind: string; target: string; template: string; tool: string }
  evidence_count: number; consistency: number; median_latency_s: number; examples: Example[]
  drafts_total: number; trust: Trust; recommendation: Recommendation | null; created_at: number; stage_changed_at: number
  stage_history: { from: Stage; to: Stage; by: string; why: string; ts: number }[]
  drafts?: Draft[]
}
export interface EventRef { id: string; actor: string; text: string; target?: string; ts: number; system?: string }
export interface Draft {
  id: string; playbook_id: string; status: 'pending' | 'scored' | 'expired' | 'proposed' | 'executed' | 'rejected'; mode: 'live' | 'backtest'
  content: { text: string; target: string; tool: string; args: Record<string, unknown>; confidence?: number }
  score: number | null; score_detail: { hit?: boolean; similarity?: number; human?: boolean; graded_by?: 'model' | 'overlap'; why?: string; equivalent?: boolean }; human_grade: number | null; run_id: string | null
  created_at: number; resolved_at: number | null; trigger: EventRef | null; actual: EventRef | null
  playbook?: { id: string; name: string; stage: Stage; actor: string }
}
export interface Preview { system?: string; kind?: string; summary?: string; text?: string; target?: string; diff?: string; irreversible?: boolean }
export interface Step { type: 'say' | 'tool' | 'approval' | 'error'; text?: string; name?: string; ok?: boolean; args?: unknown; result?: string; approval?: string; preview?: Preview; reversible?: boolean; replayed?: boolean; ts: number }
export interface Action { id: string; tool: string; args: Record<string, unknown>; result: Record<string, unknown>; undo: { tool: string; args: unknown } | null; status: 'done' | 'undone' | 'undo_failed'; preview: Preview; ts: number }
export interface Run {
  id: string; channel: string; principal: string; input: string; output: string; status: 'running' | 'waiting' | 'done' | 'error'
  steps: Step[]; tx_status: 'open' | 'committed' | 'undone' | 'partial'; playbook_id: string | null; draft_id: string | null; replay_of: string | null
  usage: { input_tokens?: number; output_tokens?: number; usd?: number; model?: string }; created_at: number; finished_at: number | null; actions: Action[]
}
export interface Approval { id: string; run_id: string; tool: string; args: Record<string, unknown>; preview: Preview; principal: string; reason: string; escalated?: boolean; confidence?: number | null; status: string; created_at: number; decided_at: number | null; decided_by: string | null; playbook: { id: string; name: string; stage: Stage; trust: number } | null }
export interface Overview {
  org: string; handle: string; demo?: boolean; brain: { provider: string; model: string; llm: boolean }
  counts: { events: number; events_24h: number; playbooks: Record<Stage, number>; drafts_pending: number; approvals: number; runs_24h: number; actions_reversible: number; memories: number; tasks_open: number; automations: number }
  shadow: { scored: number; hits: number; hit_rate: number; series: { day: string; score: number; n: number }[] }
  hours_returned: number; return_method: string; lessons_open: number
  recommendations: (Recommendation & { playbook_id: string; name: string; stage: Stage; trust: number })[]
  top_playbooks: { id: string; name: string; stage: Stage; actor: string; system: string; trust: number; scored: number; evidence: number }[]
  integrations: Integration[]
  fleet: { agents: number; actions: number; vendor_spend_usd: number; rework_rate: number | null; worst: { name: string; rework_rate: number | null; cost_per_landed_action_usd: number | null } | null }
  billing: { verified: number; disputed: number; pending: number; amount_usd: number; credited_usd: number; hours_saved: number; value_usd: number; roi: number | null; seat_equivalent_usd: number }
}
export interface Integration { key: string; name: string; connected: boolean; detail: string; how: string; mode: string }
export interface Memory { id: string; kind: string; text: string; tags: string[]; source: string; created_at: number }
export interface Task { id: string; title: string; detail: string; status: string; assignee: string; source: string; due: string; created_at: number }
export interface Automation { id: string; name: string; trigger: { human: string; kind: string }; prompt: string; enabled: boolean; last_run_at: number | null; next_run_at: number | null; last_status: string }
export interface Meeting { id: string; title: string; notes: string; action_items: { title: string; owner: string; due: string; accepted?: boolean; task_id?: string }[]; created_at: number }
export interface AuditEvent { id: number; ts: number; actor: string; action: string; target: string; detail: Record<string, unknown>; ok: boolean }
export interface Policy { id: string; principal: string; tool: string; decision: 'allow' | 'ask' | 'deny'; note: string }
export interface Budget { id: string; scope: string; max_writes_per_hour: number; max_usd_per_day: number; note: string }
export interface Tool { name: string; description: string; risk: 'read' | 'write' | 'exec'; source: string; system: string; params: string[]; reversible: boolean }
export interface User { id: string; email: string; name: string; role: string }
export interface Backtest { total: { n: number; hits: number; hit_rate: number }; seconds: number; playbooks: { id: string; name: string; stage: Stage; n: number; hits: number; hit_rate: number; mean_score: number; rows: { trigger: string; draft: string; actual: string; score: number; hit: boolean }[] }[] }
export interface Lesson { suggestion?: string; id: string; playbook: { id: string; name: string; actor: string; stage: Stage } | null; draft_id: string | null; trigger_text: string; draft_text: string; actual_text: string; question: string; answer: string | null; status: string; created_at: number; answered_at: number | null; answered_by: string | null }
export interface Person { actor: string; events: number; jobs: number; playbooks: { id: string; name: string; stage: Stage; trust: number; evidence: number; minutes_each: number }[]; coverable: number; bus_factor_risk: number; weekly_minutes: number; cover: { id: string; backup: string; until: number } | null }

// ---------------------------------------------------------------- verified work, oversight, compliance, day one
export interface LedgerLine { id: string; status: 'pending' | 'verified' | 'disputed' | 'waived'; basis: string; amount_usd: number; minutes_saved: number; playbook_id: string | null; run_id: string | null; detail: Record<string, unknown>; created_at: number; settled_at: number | null }
export interface Ledger {
  period_days: number; price_per_verified_action_usd: number; dispute_window_hours: number
  verified: number; disputed: number; pending: number; not_billable: number
  amount_usd: number; credited_usd: number; hours_saved: number; value_usd: number; roi: number | null
  seat_equivalent_usd: number; people: number; seat_price_usd: number
  by_playbook: { playbook_id: string; name: string; verified: number; disputed: number; amount_usd: number; hours_saved: number }[]
  lines: LedgerLine[]
}
export interface Grading { graded_by?: 'model' | 'overlap'; similarity?: number; why?: string; equivalent?: boolean }
export interface AgentCard {
  agent: { id: string; handle: string; name: string; vendor: string; systems: string[]; risk_tier: string; owner: string; price_per_action_usd: number; monthly_fee_usd: number }
  period_days: number; actions: number; graded: number; conformance: number | null; conformant: number; off_standard: number
  reworked: number; rework_rate: number | null; landed_rate: number | null; vendor_spend_usd: number; cost_per_landed_action_usd: number | null; unmatched: number
  worst: { id: string; conformance: number | null; reworked: boolean; expected: string; actual: string; rework_by: string | null; ts: number; detail?: Grading }[]
  actions_detail?: { id: string; conformance: number | null; verdict: string; reworked: boolean; rework_by: string | null; expected: string; actual: string; ts: number; playbook_id: string | null; human_grade: number | null; detail?: Grading }[]
}
export interface Fleet { agents: AgentCard[]; tacit: { name: string; actions: number; reworked: number; rework_rate: number | null; governed: boolean }; totals: { agents: number; actions: number; vendor_spend_usd: number; ungoverned_actions: number } }
export interface Evidence {
  generated_at: number; organisation: string; period_days: number; framework: string[]; statement: string
  log_integrity: { intact: boolean; sealed_events: number; unsealed_events: number; root: string; first_break: { id: number; actor: string; action: string; reason: string } | null }
  model: { provider: string; model: string; llm: boolean }
  oversight: { actions_taken: number; actions_reversed_by_humans: number; approvals_requested: number; approvals_granted: number; approvals_refused: number; low_confidence_escalations: number; median_time_to_decision_s: number | null; corrections_taught_by_humans: number }
  controls: { permission_rules: { principal: string; tool: string; decision: string }[]; defaults: Record<string, string>; budgets: { scope: string; max_writes_per_hour: number; max_usd_per_day: number }[]; data_residency: string; retention: string }
  ai_systems: { system_id: string; name: string; owner: string; surface: string; autonomy: Stage; risk_tier: string; human_oversight: string; evidence: Record<string, number>; stage_changes: unknown[] }[]
  supervised_third_party_agents: AgentCard[]
}
export interface DayOne {
  generated_at: number; organisation: string; seconds: number
  observed: { events: number; days: number; people: number; systems: { system: string; events: number }[] }
  jobs: { id: string; name: string; owner: string; system: string; stage: Stage; seen: number; per_year: number; minutes_each: number; hours_per_year: number; consistency: number; backtest_n: number; would_have_handled: number; hours_recoverable: number; value_usd: number; trust: number; why: string }[]
  totals: { jobs: number; hours_per_year: number; hours_recoverable: number; value_usd: number; coverage: number; backtest: { n: number; hits: number; hit_rate: number }; verified_cost_usd: number }
  bus_factor: { owner: string; jobs: number; hours_per_year: number }[]
  start_with: DayOne['jobs'][number] | null; next_steps: string[]; hours_note: string
}

export interface ReviewerQuality {
  reviewer: string; decisions: number; approved: number; refused: number; refusal_rate: number
  median_seconds: number; p90_seconds: number; rubber_stamped: number; rubber_stamp_rate: number
  reversed_after_approval: number; miss_rate: number | null; calibration: number | null
  fatigue_slope_seconds_per_day: number; span_days: number
  early_seconds: number | null; late_seconds: number | null; escalations_seen: number
}
export interface DecisionQuality {
  id: number; tool: string; playbook_id: number | null; by: string; status: string
  seconds: number; needed_seconds: number; attention: 'rubber-stamped' | 'considered'
  confidence: number | null; reversed_after: boolean; created_at: number; decided_at: number; escalated: boolean
}
export interface OversightQuality {
  period_days: number; decisions: number; index: number; band: string
  components: { name: string; score: number; weight: number; what: string }[]
  reviewers: ReviewerQuality[]
  findings: { severity: 'high' | 'medium' | 'low'; title: string; detail: string; do: string }[]
  pending: number; pending_oldest_hours: number; method: string; recent: DecisionQuality[]
}
