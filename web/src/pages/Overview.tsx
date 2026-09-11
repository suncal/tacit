import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowRight, Sparkles } from 'lucide-react'
import { api, type Overview, type Playbook } from '../lib/api'
import { Avatar, Button, Card, Empty, PageHeader, Spinner, StagePill, Stat, TrustBar, useToast } from '../components/ui'
import { STAGE_LABEL, SYSTEM_LABEL, pct } from '../lib/format'

export function OverviewPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['overview'], queryFn: () => api.get<Overview>('/overview'), refetchInterval: 15000 })
  const graduate = useMutation({
    mutationFn: ({ id, to, why }: { id: string; to: string; why: string }) => api.post<Playbook>(`/playbooks/${id}/stage`, { stage: to, why }),
    onSuccess: (pb) => { toast(`${pb.name} → ${STAGE_LABEL[pb.stage]}`, 'ok'); qc.invalidateQueries() },
    onError: (e: Error) => toast(e.message, 'bad'),
  })
  if (!q.data) return <Spinner />
  const o = q.data
  const stages = o.counts.playbooks
  const watching = stages.shadow + stages.propose + stages.auto
  return (
    <>
      <PageHeader title={`Good ${greeting()}. @${o.handle} is watching ${watching} job${watching === 1 ? '' : 's'}.`}
        subtitle={`${o.counts.events.toLocaleString()} observed actions across your tools · ${o.counts.events_24h} in the last 24h · ${o.shadow.scored} shadow drafts graded against what your team actually did.`} />

      <div className="grid grid-cols-4 gap-4 mb-5">
        <Stat label="Shadow accuracy" value={pct(o.shadow.hit_rate)} hint={`${o.shadow.hits} of ${o.shadow.scored} drafts matched the human`} tone="accent" />
        <Stat label="Running on auto" value={stages.auto} hint={`${stages.propose} proposing · ${stages.shadow} shadowing · ${stages.candidate} candidates`} />
        <Stat label="Awaiting a tap" value={o.counts.approvals} hint={o.counts.approvals ? <Link to="/inbox" className="text-accent">Open the Inbox →</Link> : 'Nothing waiting'} tone={o.counts.approvals ? 'warn' : undefined} />
        <Stat label="Hours returned" value={o.hours_returned.toFixed(1)} hint={`${o.counts.actions_reversible} reversible actions on record`} tone="ok" />
      </div>

      <div className="grid grid-cols-[1.4fr_1fr] gap-4 mb-5">
        <Card title="Ready to graduate" subtitle="Recommendations are computed, never applied. You decide.">
          {o.recommendations.length === 0 ? <Empty title="Nothing to decide right now" hint="As shadow drafts get graded, playbooks that earn it will show up here." /> : (
            <div className="flex flex-col gap-2">
              {o.recommendations.map(r => (
                <div key={r.playbook_id} className="flex items-center gap-3 rounded-lg border line px-3 py-2.5">
                  <Sparkles size={16} className="text-gold shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2"><Link to={`/playbooks/${r.playbook_id}`} className="font-medium truncate hover:text-accent">{r.name}</Link><StagePill stage={r.stage} /><ArrowRight size={12} className="muted" /><StagePill stage={r.to} /></div>
                    <div className="muted text-[12.5px] mt-0.5">{r.why}</div>
                  </div>
                  <Button size="sm" variant={r.to === 'retired' ? 'secondary' : 'primary'} loading={graduate.isPending && graduate.variables?.id === r.playbook_id} onClick={() => graduate.mutate({ id: r.playbook_id, to: r.to, why: r.why })}>{r.to === 'retired' ? 'Retire' : `Move to ${STAGE_LABEL[r.to]}`}</Button>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card title="Shadow accuracy over time" subtitle="Mean draft score per day, graded against real actions.">
          {o.shadow.series.length < 2 ? <Empty title="Not enough graded drafts yet" hint="Put a playbook in shadow, or run a backtest." /> : (
            <div className="h-44">
              <ResponsiveContainer>
                <AreaChart data={o.shadow.series} margin={{ top: 6, right: 6, left: -22, bottom: 0 }}>
                  <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0E7C86" stopOpacity={.35} /><stop offset="100%" stopColor="#0E7C86" stopOpacity={0} /></linearGradient></defs>
                  <XAxis dataKey="day" tick={{ fontSize: 11, fill: 'var(--muted)' }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 11, fill: 'var(--muted)' }} axisLine={false} tickLine={false} tickFormatter={v => `${v * 100}`} />
                  <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 8, fontSize: 12 }} formatter={(v) => [`${(Number(v) * 100).toFixed(0)}`, "score"]} />
                  <Area type="monotone" dataKey="score" stroke="#0E7C86" strokeWidth={2} fill="url(#g)" dot={{ r: 2.5, fill: '#0E7C86' }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-[1.4fr_1fr] gap-4">
        <Card title="Playbooks by trust" action={<Link to="/playbooks" className="text-accent text-[13px] font-medium">All playbooks →</Link>}>
          {o.top_playbooks.length === 0 ? <Empty title="No playbooks yet" hint="Connect a tool or feed events, then mine patterns." action={<Link to="/playbooks"><Button variant="primary">Go to playbooks</Button></Link>} /> : (
            <div className="flex flex-col">
              {o.top_playbooks.map(p => (
                <Link key={p.id} to={`/playbooks/${p.id}`} className="grid grid-cols-[1fr_120px_180px] items-center gap-3 py-2.5 border-b line last:border-0 hover:bg-[var(--surface-2)] -mx-2 px-2 rounded">
                  <div className="flex items-center gap-2.5 min-w-0"><Avatar name={p.actor} /><div className="min-w-0"><div className="font-medium truncate">{p.name}</div><div className="muted text-[12px]">{p.actor} · {SYSTEM_LABEL[p.system] || p.system} · {p.evidence} past occurrences</div></div></div>
                  <StagePill stage={p.stage} />
                  <TrustBar value={p.trust} scored={p.scored} />
                </Link>
              ))}
            </div>
          )}
        </Card>
        <Card title="Connected" subtitle="Where Tacit watches and acts.">
          <div className="flex flex-col gap-2">
            {o.integrations.map(i => (
              <div key={i.key} className="flex items-center justify-between gap-3 text-[13.5px]">
                <div className="min-w-0"><div className="font-medium">{i.name}</div><div className="muted text-[12px] truncate">{i.connected ? i.detail : i.how}</div></div>
                <span className={`w-2 h-2 rounded-full shrink-0 ${i.connected ? 'bg-ok' : 'bg-[var(--line-strong)]'}`} />
              </div>
            ))}
          </div>
          {!o.brain.llm && <p className="mt-4 text-[12.5px] rounded-lg surface-2 p-3 ink-2">Running the <b>local brain</b> (no model): drafts come from your own past replies, replies are literal. Set <span className="mono">TACIT_ANTHROPIC_API_KEY</span> to make it smart — nothing else changes.</p>}
        </Card>
      </div>
    </>
  )
}

function greeting() { const h = new Date().getHours(); return h < 12 ? 'morning' : h < 18 ? 'afternoon' : 'evening' }
