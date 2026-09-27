import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { CheckCircle2, Download, FileCheck2, ShieldAlert } from 'lucide-react'
import { api, type Evidence } from '../lib/api'
import { Badge, Card, PageHeader, Spinner, Stat, StagePill, Table, Td } from '../components/ui'
import { when } from '../lib/format'

/** EU AI Act art. 12 (records) and art. 14 (human oversight) became enforceable on 2 Aug 2026.
 *  Tacit produces the evidence as a by-product, so this page is an export, not a project. */
export function CompliancePage() {
  const [days, setDays] = useState(90)
  const q = useQuery({ queryKey: ['compliance', days], queryFn: () => api.get<Evidence>(`/compliance?days=${days}`) })
  if (!q.data) return <Spinner />
  const e = q.data
  const o = e.oversight
  return (
    <>
      <PageHeader title="Oversight evidence" subtitle="What a regulator, an auditor or a customer's security team asks for — generated from the log, not written by hand."
        action={<><select className="h-9 rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-2.5 text-sm" value={days} onChange={e2 => setDays(+e2.target.value)}>{[30, 90, 365].map(d => <option key={d} value={d}>last {d} days</option>)}</select>
          <a className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-lg bg-accent text-white font-medium text-sm" href={`/api/v1/compliance/export?days=${days}`}><Download size={15} />Export evidence</a></>} />

      <div className={`surface p-4 mb-5 flex items-center gap-3 border-l-4 ${e.log_integrity.intact ? 'border-l-ok' : 'border-l-bad'}`}>
        {e.log_integrity.intact ? <CheckCircle2 className="text-ok shrink-0" size={20} /> : <ShieldAlert className="text-bad shrink-0" size={20} />}
        <div className="min-w-0 flex-1">
          <div className="font-semibold">{e.log_integrity.intact ? 'Log intact' : 'Log integrity broken'}</div>
          <div className="muted text-[13px]">{e.log_integrity.sealed_events.toLocaleString()} events sealed into a hash chain{e.log_integrity.unsealed_events ? `, ${e.log_integrity.unsealed_events} awaiting the next seal` : ''}. {e.log_integrity.intact ? 'Every record still commits to the one before it — nothing was edited or removed.' : `First break at event ${e.log_integrity.first_break?.id}: ${e.log_integrity.first_break?.reason}.`}</div>
        </div>
        <code className="mono text-[11px] muted hidden lg:block" title="chain root — keep a copy and anyone can re-verify later">{e.log_integrity.root.slice(0, 24)}…</code>
      </div>

      <div className="grid grid-cols-4 gap-4 mb-5">
        <Stat label="Actions taken by AI" value={o.actions_taken} hint={`${o.actions_reversed_by_humans} reversed by a human`} />
        <Stat label="Human decisions" value={`${o.approvals_granted}/${o.approvals_requested}`} hint={`${o.approvals_refused} refused · median ${o.median_time_to_decision_s !== null ? `${Math.round(o.median_time_to_decision_s / 60)} min` : '—'} to decide`} tone="accent" />
        <Stat label="Escalated to a human" value={o.low_confidence_escalations} hint="low-confidence cases the AI declined to handle alone" tone="warn" />
        <Stat label="Corrections taught" value={o.corrections_taught_by_humans} hint="rules a person wrote after a miss" tone="ok" />
      </div>

      <Card className="mb-5" title="Statement of oversight" subtitle={e.framework.join(' · ')}>
        <p className="ink2 text-[14.5px] leading-relaxed max-w-4xl">{e.statement}</p>
        <div className="grid grid-cols-3 gap-4 mt-4 text-[13px]">
          <div><div className="muted text-[11.5px] uppercase tracking-wide mb-1">Model</div>{e.model.llm ? <span className="mono">{e.model.model}</span> : <span>no model — deterministic</span>}</div>
          <div><div className="muted text-[11.5px] uppercase tracking-wide mb-1">Data residency</div>{e.controls.data_residency}</div>
          <div><div className="muted text-[11.5px] uppercase tracking-wide mb-1">Retention</div>{e.controls.retention}</div>
        </div>
      </Card>

      <Card className="mb-5" title={`AI systems in scope (${e.ai_systems.length})`} subtitle="Each job, its autonomy level, and the human oversight that applies to it.">
        <Table head={['System', 'Owner', 'Autonomy', 'Human oversight that applies', 'Evidence']}>
          {e.ai_systems.map(s => (
            <tr key={s.system_id}>
              <Td><div className="font-medium">{s.name}</div><div className="muted text-[12px]">{s.surface}</div></Td>
              <Td>{s.owner}</Td>
              <Td><StagePill stage={s.autonomy} /></Td>
              <Td className="muted max-w-md">{s.human_oversight}</Td>
              <Td className="mono text-[11.5px] muted">{s.evidence.graded_drafts} graded · {Math.round((s.evidence.match_rate || 0) * 100)}% match<br />{s.evidence.human_approvals} approved / {s.evidence.human_rejections} refused<br />{s.evidence.executions} acted · {s.evidence.reversals} reversed</Td>
            </tr>
          ))}
        </Table>
      </Card>

      {e.supervised_third_party_agents.length > 0 && (
        <Card className="mb-5" title="Third-party agents under supervision" subtitle="AI you bought, held to the same record-keeping as the AI you run.">
          <Table head={['Agent', 'Vendor', 'Risk tier', 'Actions', 'Needed a human after']}>
            {e.supervised_third_party_agents.map(a => (
              <tr key={a.agent.id}><Td className="font-medium">{a.agent.name}</Td><Td>{a.agent.vendor || 'in-house'}</Td><Td><Badge>{a.agent.risk_tier}</Badge></Td><Td className="tnum">{a.actions}</Td><Td className="tnum">{a.reworked}{a.rework_rate !== null && <span className="muted"> ({Math.round(a.rework_rate * 100)}%)</span>}</Td></tr>
            ))}
          </Table>
        </Card>
      )}

      <Card title="Controls in force" subtitle="Enforced before execution, not documented after the fact.">
        <div className="grid grid-cols-2 gap-6">
          <div>
            <div className="muted text-[11.5px] uppercase tracking-wide mb-2">Permission rules</div>
            <div className="text-[13px] mono flex flex-col gap-1">
              {e.controls.permission_rules.map((r, i) => <div key={i}>{r.principal} × {r.tool} → <span className={r.decision === 'deny' ? 'text-bad' : r.decision === 'allow' ? 'text-ok' : 'text-warn'}>{r.decision}</span></div>)}
              <div className="muted">defaults: {Object.entries(e.controls.defaults).map(([k, v]) => `${k}→${v}`).join(' · ')}</div>
            </div>
          </div>
          <div>
            <div className="muted text-[11.5px] uppercase tracking-wide mb-2">Budgets</div>
            <div className="text-[13px] mono flex flex-col gap-1">{e.controls.budgets.map((b, i) => <div key={i}>{b.scope} → {b.max_writes_per_hour} writes/h · ${b.max_usd_per_day}/day</div>)}</div>
          </div>
        </div>
        <p className="muted text-[12px] mt-4 flex items-center gap-1.5"><FileCheck2 size={13} />Generated {when(e.generated_at)} for {e.organisation}. The export is the same content as JSON, with the chain root, for your records.</p>
      </Card>
    </>
  )
}
