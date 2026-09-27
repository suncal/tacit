import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { clsx } from 'clsx'
import { api, type Ledger } from '../lib/api'
import { Badge, Card, Empty, PageHeader, Spinner, Stat, Table, Td } from '../components/ui'
import { ago, pct } from '../lib/format'

const BASIS: Record<string, string> = { human_approved: 'a human approved it', undisputed_auto: 'ran on an earned job, nobody reversed it', supervised_agent: 'supervised third-party action' }

/** Billing you can audit line by line — only possible because the product knows whether the work was right. */
export function LedgerPage() {
  const [days, setDays] = useState(30)
  const q = useQuery({ queryKey: ['ledger', days], queryFn: () => api.get<Ledger>(`/ledger?days=${days}`), refetchInterval: 30000 })
  if (!q.data) return <Spinner />
  const l = q.data
  const total = l.verified + l.disputed
  return (
    <>
      <PageHeader title="Verified work" subtitle={`You are billed $${l.price_per_verified_action_usd.toFixed(2)} for an action only once a human approved it, or it ran on a job that had earned its autonomy and nobody reversed it within ${l.dispute_window_hours} hours. Everything else is free, permanently.`}
        action={<select className="h-9 rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-2.5 text-sm" value={days} onChange={e => setDays(+e.target.value)}>{[7, 30, 90].map(d => <option key={d} value={d}>last {d} days</option>)}</select>} />

      <div className="grid grid-cols-4 gap-3.5 mb-5">
        <Stat label="Billable this period" value={`$${l.amount_usd.toFixed(2)}`} hint={`${l.verified} verified action${l.verified === 1 ? '' : 's'}`} tone="accent" />
        <Stat label="Credited back" value={`$${l.credited_usd.toFixed(2)}`} hint={`${l.disputed} reversed or refused — never billed`} tone={l.disputed ? 'bad' : undefined} />
        <Stat label="Time returned" value={`${l.hours_saved}h`} hint={`≈ $${l.value_usd.toLocaleString()} of your team's time`} tone="ok" />
        <Stat label="Return on spend" value={l.roi ? `${l.roi}×` : '—'} hint={`vs $${l.seat_equivalent_usd.toFixed(0)} if ${l.people} people paid per seat`} />
      </div>

      <div className="grid grid-cols-[1.3fr_1fr] gap-4 mb-5">
        <Card title="How this period was settled" subtitle="Nothing is billed while a human can still take it back.">
          <div className="flex flex-col gap-2.5">
            {[['verified', l.verified, 'ok', 'Billed — approved by a human, or ran on an earned job and stood'],
              ['disputed', l.disputed, 'bad', 'Credited — a human reversed or refused it'],
              ['pending', l.pending, 'warn', 'Not billed yet — still inside the dispute window'],
              ['not billable', l.not_billable, 'neutral', 'Work a person drove themselves, or with no job behind it']].map(([k, n, tone, why]) => (
              <div key={k as string} className="flex items-center gap-3">
                <Badge tone={tone as 'ok'}>{k as string}</Badge>
                <div className="h-2 rounded-full bg-[var(--surface-2)] flex-1 overflow-hidden"><div className={clsx('h-full rounded-full', tone === 'ok' ? 'bg-ok' : tone === 'bad' ? 'bg-bad' : tone === 'warn' ? 'bg-warn' : 'bg-[var(--line-strong)]')} style={{ width: `${Math.max(1, ((n as number) / Math.max(1, l.verified + l.disputed + l.pending + l.not_billable)) * 100)}%` }} /></div>
                <span className="tnum font-semibold w-8 text-right">{n as number}</span>
                <span className="muted text-[12.5px] w-[54%]">{why as string}</span>
              </div>
            ))}
          </div>
          {total > 0 && <p className="muted text-[12.5px] mt-4">Of work that finished settling, <b className="text-ink">{pct(l.verified / total)}</b> was verified. A vendor charging per “resolution” would have billed you for all {total}.</p>}
        </Card>
        <Card title="By job" subtitle="What each job earned and cost.">
          {l.by_playbook.length === 0 ? <Empty title="No billable work yet" hint="Promote a job to Propose or Auto and it will show up here." /> : (
            <Table head={['Job', 'Verified', 'Hours', '$']}>
              {l.by_playbook.map(p => (
                <tr key={p.playbook_id}>
                  <Td><Link to={`/playbooks/${p.playbook_id}`} className="hover:text-accent">{p.name}</Link>{p.disputed > 0 && <div className="muted text-[11.5px]">{p.disputed} credited back</div>}</Td>
                  <Td className="tnum">{p.verified}</Td><Td className="tnum">{p.hours_saved}</Td><Td className="tnum">${p.amount_usd.toFixed(2)}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
      </div>

      <Card title="Every line" subtitle="Each one names the action, the job and the reason it was or wasn't billed.">
        {l.lines.length === 0 ? <Empty title="Nothing here yet" /> : (
          <Table head={['When', 'Status', 'Why', 'Job', 'Minutes saved', 'Amount']}>
            {l.lines.map(r => (
              <tr key={r.id}>
                <Td className="muted whitespace-nowrap">{ago(r.created_at)}</Td>
                <Td><Badge tone={r.status === 'verified' ? 'ok' : r.status === 'disputed' ? 'bad' : r.status === 'pending' ? 'warn' : 'neutral'}>{r.status}</Badge></Td>
                <Td className="muted">{r.basis ? BASIS[r.basis] || r.basis : (r.detail.reason as string) || '—'}</Td>
                <Td>{r.playbook_id ? <Link to={`/playbooks/${r.playbook_id}`} className="mono text-[12px] hover:text-accent">{r.playbook_id.slice(0, 12)}…</Link> : <span className="muted">—</span>}{r.run_id && <Link to={`/runs/${r.run_id}`} className="block text-accent text-[11.5px]">run →</Link>}</Td>
                <Td className="tnum">{r.minutes_saved}</Td>
                <Td className="tnum font-medium">{r.amount_usd ? `$${r.amount_usd.toFixed(2)}` : <span className="muted">$0.00</span>}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  )
}
