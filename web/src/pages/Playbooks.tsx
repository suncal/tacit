import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { FlaskConical, Pickaxe } from 'lucide-react'
import { useState } from 'react'
import { api, type Backtest, type Playbook, type Stage } from '../lib/api'
import { Avatar, Badge, Button, Empty, Modal, PageHeader, Spinner, TrustBar, useToast } from '../components/ui'
import { STAGE_HELP, STAGE_LABEL, SYSTEM_LABEL, pct } from '../lib/format'

const LADDER: Stage[] = ['candidate', 'shadow', 'propose', 'auto']

export function PlaybooksPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const [bt, setBt] = useState<Backtest | null>(null)
  const q = useQuery({ queryKey: ['playbooks'], queryFn: () => api.get<{ playbooks: Playbook[] }>('/playbooks'), refetchInterval: 15000 })
  const mine = useMutation({ mutationFn: () => api.post<{ found: number; created: number; updated: number; events: number }>('/playbooks/mine'), onSuccess: r => { toast(`Mined ${r.events} events → ${r.found} patterns (${r.created} new)`, 'ok'); qc.invalidateQueries() }, onError: (e: Error) => toast(e.message, 'bad') })
  const backtest = useMutation({ mutationFn: () => api.post<Backtest>('/playbooks/backtest', {}), onSuccess: r => { setBt(r); qc.invalidateQueries() }, onError: (e: Error) => toast(e.message, 'bad') })
  if (!q.data) return <Spinner />
  const pbs = q.data.playbooks
  const retired = pbs.filter(p => p.stage === 'retired')
  return (
    <>
      <PageHeader title="Playbooks" subtitle="Recurring jobs Tacit found by watching your team. Each one climbs the ladder only as fast as it earns trust."
        action={<><Button onClick={() => mine.mutate()} loading={mine.isPending}><Pickaxe size={15} />Mine patterns</Button><Button variant="primary" onClick={() => backtest.mutate()} loading={backtest.isPending}><FlaskConical size={15} />Backtest all</Button></>} />
      {pbs.length === 0 ? <Empty title="No patterns yet" hint="Tacit needs to see your team work. Connect GitHub, Slack or Linear in Settings — or POST events to /api/v1/events — then mine." action={<Button variant="primary" onClick={() => mine.mutate()}>Mine patterns</Button>} /> : (
        <div className="grid grid-cols-4 gap-4 items-start">
          {LADDER.map(stage => {
            const items = pbs.filter(p => p.stage === stage)
            return (
              <div key={stage} className="min-w-0">
                <div className="flex items-baseline justify-between mb-2 px-1"><div className="font-semibold">{STAGE_LABEL[stage]} <span className="muted font-normal tnum">{items.length}</span></div></div>
                <p className="muted text-[12px] px-1 mb-3 leading-snug">{STAGE_HELP[stage]}</p>
                <div className="flex flex-col gap-3">
                  {items.map(p => <PlaybookCard key={p.id} p={p} />)}
                  {items.length === 0 && <div className="rounded-xl border border-dashed line h-20" />}
                </div>
              </div>
            )
          })}
        </div>
      )}
      {retired.length > 0 && <div className="mt-8"><div className="font-semibold mb-2">Retired <span className="muted font-normal">{retired.length}</span></div><div className="grid grid-cols-4 gap-3">{retired.map(p => <PlaybookCard key={p.id} p={p} />)}</div></div>}
      <Modal open={!!bt} onClose={() => setBt(null)} title="Backtest — what Tacit would have done" wide>
        {bt && (
          <>
            <div className="flex items-baseline gap-6 mb-4">
              <div><div className="muted text-[12px] uppercase tracking-wide">Would have handled</div><div className="text-[30px] font-semibold tnum text-accent">{pct(bt.total.hit_rate)}</div></div>
              <div className="muted text-[13px]">{bt.total.hits} of {bt.total.n} historical triggers, drafted blind and compared with the real reply · {bt.seconds}s</div>
            </div>
            <div className="flex flex-col gap-2">
              {bt.playbooks.map(p => (
                <div key={p.id} className="rounded-lg border line px-3 py-2.5">
                  <div className="flex items-center gap-3"><Link to={`/playbooks/${p.id}`} className="font-medium hover:text-accent">{p.name}</Link><span className="muted text-[12.5px] tnum">{p.hits}/{p.n} hits · mean {(p.mean_score * 100).toFixed(0)}</span><div className="flex-1" /><TrustBar value={p.hit_rate} className="w-44" /></div>
                </div>
              ))}
            </div>
          </>
        )}
      </Modal>
    </>
  )
}

function PlaybookCard({ p }: { p: Playbook }) {
  const rec = p.recommendation
  return (
    <Link to={`/playbooks/${p.id}`} className="surface raised block p-4 hover:border-[var(--line-strong)] hover:shadow-[var(--shadow)] transition-[box-shadow,border-color]">
      <div className="flex items-center gap-2 mb-1.5"><Avatar name={p.actor} size={20} /><span className="text-[12.5px] muted truncate">{p.actor} · {SYSTEM_LABEL[p.system] || p.system}</span></div>
      <div className="font-semibold tracking-[-0.015em] leading-snug mb-2.5">{p.name}</div>
      <div className="flex flex-wrap gap-1 mb-2.5">
        <Badge>{p.evidence_count}× seen</Badge>
        {p.trigger.mode === 'schedule' ? <Badge tone="neutral">{p.trigger.cadence?.human}</Badge> : (p.trigger.keywords || []).slice(0, 2).map(k => <Badge key={k} tone="accent">“{k}”</Badge>)}
      </div>
      <TrustBar value={p.trust.trust} scored={p.trust.scored} />
      {rec && <div className="mt-2.5 text-[12px] rounded-md bg-[rgba(199,150,28,.10)] text-warn px-2 py-1 font-medium">→ {STAGE_LABEL[rec.to]}: {rec.why}</div>}
    </Link>
  )
}
