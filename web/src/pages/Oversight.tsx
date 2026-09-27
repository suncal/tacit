import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bot, Plus, ShieldCheck, ThumbsDown, ThumbsUp, Trash2 } from 'lucide-react'
import { clsx } from 'clsx'
import { api, type AgentCard, type Fleet } from '../lib/api'
import { Badge, Button, Card, Empty, Input, Modal, PageHeader, Spinner, Stat, Table, Td, useToast } from '../components/ui'
import { ago, pct } from '../lib/format'
import { Why } from '../components/Grade'

/** The page nobody else can build: an independent grade for every AI you already pay for. */
export function OversightPage() {
  const qc = useQueryClient(); const toast = useToast()
  const [days, setDays] = useState(30)
  const [open, setOpen] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [f, setF] = useState({ handle: '', name: '', vendor: '', systems: '', price_per_action_usd: 0, monthly_fee_usd: 0, owner: '' })
  const q = useQuery({ queryKey: ['oversight', days], queryFn: () => api.get<Fleet>(`/oversight?days=${days}`), refetchInterval: 20000 })
  const add = useMutation({
    mutationFn: () => api.post('/oversight', { ...f, systems: f.systems.split(',').map(s => s.trim()).filter(Boolean) }),
    onSuccess: () => { toast('Now supervising. Its past actions will be graded on the next mine.', 'ok'); setAdding(false); setF({ handle: '', name: '', vendor: '', systems: '', price_per_action_usd: 0, monthly_fee_usd: 0, owner: '' }); qc.invalidateQueries() },
    onError: (e: Error) => toast(e.message, 'bad'),
  })
  const drop = useMutation({ mutationFn: (id: string) => api.del(`/oversight/${id}`), onSuccess: () => { toast('Stopped supervising'); qc.invalidateQueries() } })
  if (!q.data) return <Spinner />
  const { agents, tacit, totals } = q.data
  const worstRework = agents.filter(a => a.rework_rate !== null).sort((x, y) => (y.rework_rate || 0) - (x.rework_rate || 0))[0]
  return (
    <>
      <PageHeader title="Oversight" subtitle="Every non-human worker in the company, graded against what your own people do. Vendors grade themselves; this doesn't."
        action={<><select className="h-9 rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-2.5 text-sm" value={days} onChange={e => setDays(+e.target.value)}>{[7, 30, 90].map(d => <option key={d} value={d}>last {d} days</option>)}</select><Button variant="primary" onClick={() => setAdding(true)}><Plus size={15} />Supervise an agent</Button></>} />

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3.5 mb-5">
        <Stat label="Agents supervised" value={totals.agents} hint={`${totals.actions.toLocaleString()} actions incl. this system`} />
        <Stat label="Paid to vendors" value={`$${totals.vendor_spend_usd.toLocaleString()}`} hint={`over ${days} days, from the rates you entered`} />
        <Stat label="Worst rework rate" value={worstRework?.rework_rate !== undefined && worstRework?.rework_rate !== null ? pct(worstRework.rework_rate) : '—'} hint={worstRework ? `${worstRework.agent.name} — a human stepped in afterwards` : 'nothing graded yet'} tone={(worstRework?.rework_rate || 0) > 0.25 ? 'bad' : undefined} />
        <Stat label="This system" value={tacit.rework_rate !== null ? pct(tacit.rework_rate) : '—'} hint={`${tacit.actions} actions · ${tacit.reworked} reversed by a human`} tone="accent" />
      </div>

      {agents.length === 0 ? (
        <Empty title="No third-party agents supervised yet" hint="Register the AI products you already pay for. Their actions arrive through the same event API as everything else — read-only, no write access needed — and Tacit grades them against the standard it learned from your team."
          action={<Button variant="primary" onClick={() => setAdding(true)}>Supervise an agent</Button>} />
      ) : (
        <div className="grid lg:grid-cols-2 gap-4">
          {agents.map(a => <AgentTile key={a.agent.id} c={a} onOpen={() => setOpen(a.agent.id)} onDrop={() => confirm(`Stop supervising ${a.agent.name}?`) && drop.mutate(a.agent.id)} />)}
          <div className="surface p-5 border-dashed">
            <div className="flex items-center gap-2 mb-2"><ShieldCheck size={18} className="text-accent" /><span className="font-semibold">{tacit.name}</span><Badge tone="accent">governed</Badge></div>
            <p className="muted text-[13px]">Held to the same standard, on the same page. {tacit.actions} actions, {tacit.reworked} reversed by a human{tacit.rework_rate !== null ? ` — ${pct(tacit.rework_rate)} rework.` : '.'} Every one of them had an approval or an earned autonomy level behind it, and an undo recipe after it.</p>
            <div className="mt-3"><Link to="/ledger" className="text-accent text-[13px] font-medium">See what that cost →</Link></div>
          </div>
        </div>
      )}

      <AgentDetail id={open} onClose={() => setOpen(null)} days={days} />

      <Modal open={adding} onClose={() => setAdding(false)} title="Supervise an agent">
        <div className="flex flex-col gap-3 text-[13.5px]">
          <p className="ink2">Any AI that acts in a system Tacit can see. Its actions come in as events with <code className="mono">actor_type: "agent"</code> — no write access to the vendor is needed, and nothing about your setup changes.</p>
          <div className="grid grid-cols-2 gap-2">
            <div><div className="muted text-[12px] mb-1">Handle (the actor its events arrive under)</div><Input placeholder="fin" value={f.handle} onChange={e => setF({ ...f, handle: e.target.value })} /></div>
            <div><div className="muted text-[12px] mb-1">Name</div><Input placeholder="Fin (support bot)" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>
            <div><div className="muted text-[12px] mb-1">Vendor</div><Input placeholder="Intercom" value={f.vendor} onChange={e => setF({ ...f, vendor: e.target.value })} /></div>
            <div><div className="muted text-[12px] mb-1">Systems</div><Input placeholder="slack, zendesk" value={f.systems} onChange={e => setF({ ...f, systems: e.target.value })} /></div>
            <div><div className="muted text-[12px] mb-1">What they charge per action ($)</div><Input type="number" step="0.01" value={f.price_per_action_usd} onChange={e => setF({ ...f, price_per_action_usd: +e.target.value })} /></div>
            <div><div className="muted text-[12px] mb-1">Monthly fee ($)</div><Input type="number" step="1" value={f.monthly_fee_usd} onChange={e => setF({ ...f, monthly_fee_usd: +e.target.value })} /></div>
          </div>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button><Button variant="primary" disabled={!f.handle || !f.name} loading={add.isPending} onClick={() => add.mutate()}>Start supervising</Button></div>
        </div>
      </Modal>
    </>
  )
}

function AgentTile({ c, onOpen, onDrop }: { c: AgentCard; onOpen: () => void; onDrop: () => void }) {
  const rr = c.rework_rate
  return (
    <div className="surface p-5">
      <div className="flex items-start gap-3 mb-3">
        <span className="w-9 h-9 rounded-lg bg-[var(--surface-2)] inline-flex items-center justify-center shrink-0"><Bot size={18} className="muted" /></span>
        <div className="min-w-0 flex-1"><div className="font-semibold">{c.agent.name}</div><div className="muted text-[12.5px]">{c.agent.vendor || 'in-house'} · {c.agent.systems.join(', ') || 'any system'} · {c.actions} actions</div></div>
        <button className="muted hover:text-bad" onClick={onDrop} title="Stop supervising"><Trash2 size={14} /></button>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div><div className="muted text-[11px] uppercase tracking-wide">Rework</div><div className={clsx('text-[22px] font-semibold tnum', (rr || 0) > 0.25 ? 'text-bad' : (rr || 0) > 0.1 ? 'text-warn' : 'text-ok')}>{rr === null ? '—' : pct(rr)}</div><div className="muted text-[11.5px]">{c.reworked} needed a human after</div></div>
        <div><div className="muted text-[11px] uppercase tracking-wide">Matches your team</div><div className="text-[22px] font-semibold tnum">{c.conformance === null ? '—' : pct(c.conformance)}</div><div className="muted text-[11.5px]">{c.graded} of {c.actions} comparable</div></div>
        <div><div className="muted text-[11px] uppercase tracking-wide">Cost per landed</div><div className="text-[22px] font-semibold tnum">{c.cost_per_landed_action_usd === null ? '—' : `$${c.cost_per_landed_action_usd.toFixed(2)}`}</div><div className="muted text-[11.5px]">billed ${c.vendor_spend_usd.toFixed(2)}</div></div>
      </div>
      {c.cost_per_landed_action_usd !== null && c.agent.price_per_action_usd > 0 && (
        <div className="rounded-lg surface-2 px-3 py-2 text-[12.5px] ink2 mb-3">You are billed <b>${c.agent.price_per_action_usd.toFixed(2)}</b> per action. Because {pct(rr)} needed a human afterwards, each action that actually landed cost <b>${c.cost_per_landed_action_usd.toFixed(2)}</b>.</div>
      )}
      <Button size="sm" onClick={onOpen}>See what it got wrong</Button>
    </div>
  )
}

function AgentDetail({ id, onClose, days }: { id: string | null; onClose: () => void; days: number }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['oversight', id, days], queryFn: () => api.get<AgentCard>(`/oversight/${id}?days=${days}`), enabled: !!id })
  const grade = useMutation({ mutationFn: ({ a, g }: { a: string; g: number }) => api.post(`/oversight/actions/${a}/grade`, { grade: g }), onSuccess: () => qc.invalidateQueries() })
  return (
    <Modal open={!!id} onClose={onClose} title={q.data ? `${q.data.agent.name} — graded against your team` : 'Loading'} wide>
      {!q.data ? <Spinner /> : (
        <>
          <div className="grid grid-cols-4 gap-3 mb-4 text-[13px]">
            <div><div className="muted text-[11px] uppercase tracking-wide">Actions</div><div className="text-lg font-semibold tnum">{q.data.actions}</div></div>
            <div><div className="muted text-[11px] uppercase tracking-wide">Reworked</div><div className="text-lg font-semibold tnum text-bad">{q.data.reworked}</div></div>
            <div><div className="muted text-[11px] uppercase tracking-wide">Off-standard</div><div className="text-lg font-semibold tnum text-warn">{q.data.off_standard}</div></div>
            <div><div className="muted text-[11px] uppercase tracking-wide">Not comparable</div><div className="text-lg font-semibold tnum muted">{q.data.unmatched}</div></div>
          </div>
          <Card title="Where it went off standard" subtitle="Left: what your team says in this situation. Right: what the agent said.">
            <Table head={['Score', 'Your team’s answer', 'What the agent said', 'Outcome', '']}>
              {(q.data.actions_detail || []).filter(a => a.conformance !== null).sort((a, b) => (a.reworked === b.reworked ? (a.conformance || 0) - (b.conformance || 0) : a.reworked ? -1 : 1)).slice(0, 25).map(a => (
                <tr key={a.id}>
                  <Td><span className={clsx('tnum font-semibold', (a.conformance || 0) >= 0.5 ? 'text-ok' : 'text-bad')}>{Math.round((a.conformance || 0) * 100)}</span></Td>
                  <Td className="w-[32%] whitespace-pre-wrap muted">{a.expected.slice(0, 260)}</Td>
                  <Td className="w-[32%] whitespace-pre-wrap">{a.actual.slice(0, 260)}<Why className="mt-1.5" why={a.detail?.why} gradedBy={a.detail?.graded_by} similarity={a.detail?.similarity} /></Td>
                  <Td>{a.reworked ? <Badge tone="bad">{a.rework_by} stepped in</Badge> : <Badge tone={a.verdict === 'conformant' ? 'ok' : 'warn'}>{a.verdict}</Badge>}<div className="muted text-[11.5px] mt-1">{ago(a.ts)}</div></Td>
                  <Td><div className="flex gap-1"><button className={clsx('p-1 rounded hover:bg-[var(--surface-2)]', a.human_grade === 1 && 'text-ok')} title="This was fine" onClick={() => grade.mutate({ a: a.id, g: 1 })}><ThumbsUp size={14} /></button><button className={clsx('p-1 rounded hover:bg-[var(--surface-2)]', a.human_grade === -1 && 'text-bad')} title="This was wrong" onClick={() => grade.mutate({ a: a.id, g: -1 })}><ThumbsDown size={14} /></button></div></Td>
                </tr>
              ))}
            </Table>
          </Card>
        </>
      )}
    </Modal>
  )
}
