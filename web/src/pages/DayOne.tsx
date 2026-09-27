import { useMutation, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, Printer, Sparkles } from 'lucide-react'
import { api, type DayOne } from '../lib/api'
import { Badge, Button, Card, Empty, PageHeader, Spinner, StagePill, Table, Td, TrustBar } from '../components/ui'
import { SYSTEM_LABEL, pct } from '../lib/format'

/** The pilot, in one page: read history, cost the repetitive work, say what would have been handled.
 *  Nothing writes anywhere — this is what makes it a thirty-minute decision instead of a project. */
export function DayOnePage() {
  const q = useQuery({ queryKey: ['dayone'], queryFn: () => api.get<DayOne>('/pilot/report') })
  const refresh = useMutation({ mutationFn: () => api.post<DayOne>('/pilot/report'), onSuccess: () => q.refetch() })
  if (!q.data) return <Spinner />
  const r = q.data
  const t = r.totals
  return (
    <>
      <PageHeader title="What Tacit found" subtitle={`Read ${r.observed.events.toLocaleString()} actions across ${r.observed.systems.map(s => SYSTEM_LABEL[s.system] || s.system).join(', ')} over ${r.observed.days} days from ${r.observed.people} people. Read-only: nothing has acted.`}
        action={<><Button onClick={() => refresh.mutate()} loading={refresh.isPending}><Sparkles size={15} />Re-run</Button><Button variant="ghost" onClick={() => window.print()}><Printer size={15} />Print</Button></>} />

      {t.jobs === 0 ? <Empty title="No repeating work found yet" hint="Connect a busier source, or give it more history. Patterns need at least three comparable occurrences." /> : (
        <>
          <div className="surface p-6 mb-5">
            <div className="grid grid-cols-[1.2fr_1fr_1fr_1fr] gap-6 items-center">
              <div>
                <div className="muted text-[12px] uppercase tracking-wide font-medium">Recoverable, per year</div>
                <div className="text-[46px] font-semibold leading-none tnum tracking-[-0.04em] text-accent mt-1">{t.hours_recoverable}h</div>
                <div className="muted text-[13px] mt-1.5">≈ ${t.value_usd.toLocaleString()} of your team's time, from {t.jobs} repeating jobs</div>
              </div>
              <div><div className="muted text-[12px] uppercase tracking-wide font-medium">Would have handled</div><div className="text-[30px] font-semibold tnum tracking-[-0.035em] mt-1">{pct(t.coverage)}</div><div className="muted text-[12.5px]">{t.backtest.hits} of {t.backtest.n} past cases, drafted without seeing the answer</div></div>
              <div><div className="muted text-[12px] uppercase tracking-wide font-medium">Total repetitive load</div><div className="text-[30px] font-semibold tnum tracking-[-0.035em] mt-1">{t.hours_per_year}h</div><div className="muted text-[12.5px]">per year across these jobs</div></div>
              <div><div className="muted text-[12px] uppercase tracking-wide font-medium">What it would cost</div><div className="text-[30px] font-semibold tnum tracking-[-0.035em] mt-1">${t.verified_cost_usd.toLocaleString()}</div><div className="muted text-[12.5px]">per year at verified-work pricing</div></div>
            </div>
          </div>

          {r.start_with && (
            <div className="surface p-4 mb-5 border-l-4 border-l-accent flex items-center gap-3">
              <ArrowRight size={18} className="text-accent shrink-0" />
              <div className="flex-1 min-w-0"><div className="font-semibold">Start with “{r.start_with.name}”</div><div className="muted text-[13px]">{r.start_with.why} It's {r.start_with.hours_recoverable}h a year of {r.start_with.owner}'s time.</div></div>
              <Link to={`/playbooks/${r.start_with.id}`}><Button variant="primary" size="sm">Open it</Button></Link>
            </div>
          )}

          <Card className="mb-5" title="The repeating work" subtitle="Ranked by time recoverable. “Would have handled” is measured against what the owner actually did, on cases that already happened.">
            <Table head={['Job', 'Owner', 'Per year', 'Each', 'Hours/yr', 'Would have handled', 'Recoverable', 'Stage']}>
              {r.jobs.map(j => (
                <tr key={j.id}>
                  <Td><Link to={`/playbooks/${j.id}`} className="font-medium hover:text-accent">{j.name}</Link><div className="muted text-[12px]">{SYSTEM_LABEL[j.system] || j.system} · seen {j.seen}× · {j.why}</div></Td>
                  <Td>{j.owner}</Td><Td className="tnum">{j.per_year}</Td><Td className="tnum muted">{j.minutes_each}m</Td><Td className="tnum">{j.hours_per_year}</Td>
                  <Td className="w-40">{j.backtest_n ? <TrustBar value={j.would_have_handled} scored={j.backtest_n} /> : <span className="muted text-[12.5px]">no history</span>}</Td>
                  <Td className="tnum font-medium">{j.hours_recoverable}h<div className="muted text-[11.5px]">${j.value_usd.toLocaleString()}</div></Td>
                  <Td><StagePill stage={j.stage} /></Td>
                </tr>
              ))}
            </Table>
            <p className="muted text-[12px] mt-3">{r.hours_note}</p>
          </Card>

          <div className="grid grid-cols-[1fr_1.2fr] gap-4">
            <Card title="Where the load sits" subtitle="Repetitive hours per year, by person. The top of this list is your bus-factor risk.">
              <Table head={['Person', 'Jobs', 'Hours/yr']}>
                {r.bus_factor.map(b => <tr key={b.owner}><Td className="font-medium">{b.owner}</Td><Td className="tnum">{b.jobs}</Td><Td className="tnum">{b.hours_per_year}</Td></tr>)}
              </Table>
              <div className="mt-3"><Link to="/people" className="text-accent text-[13px] font-medium">Cover them while they're out →</Link></div>
            </Card>
            <Card title="What happens next" subtitle="In order. You can stop at any step.">
              <ol className="flex flex-col gap-3">
                {r.next_steps.map((s, i) => (
                  <li key={i} className="flex gap-3 text-[14px]"><span className="w-6 h-6 rounded-full surface-2 inline-flex items-center justify-center text-[12px] font-semibold shrink-0">{i + 1}</span><span className="ink2">{s}</span></li>
                ))}
              </ol>
              <div className="mt-4 flex gap-2"><Link to="/playbooks"><Button variant="primary" size="sm">See the jobs</Button></Link><Link to="/oversight"><Button size="sm">Supervise an AI you already pay for</Button></Link></div>
              <p className="muted text-[12px] mt-4">Mined in {r.seconds}s. <Badge tone="ok">read-only</Badge> No write access was used or requested to produce this.</p>
            </Card>
          </div>
        </>
      )}
    </>
  )
}
