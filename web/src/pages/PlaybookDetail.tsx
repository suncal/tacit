import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ArrowRight, Check, FlaskConical, Pencil, ThumbsDown, ThumbsUp, Trash2 } from 'lucide-react'
import { clsx } from 'clsx'
import { api, type Backtest, type Draft, type Playbook, type Stage } from '../lib/api'
import { useState } from 'react'
import { Avatar, Badge, Button, Card, Empty, Input, Label, Modal, PageHeader, ScoreDot, Spinner, StagePill, Stat, Table, Td, Textarea, useToast } from '../components/ui'
import { STAGE_HELP, STAGE_LABEL, SYSTEM_LABEL, ago, dur, pct, when } from '../lib/format'

const LADDER: Stage[] = ['candidate', 'shadow', 'propose', 'auto']

export function PlaybookDetailPage() {
  const { id = '' } = useParams()
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['playbook', id], queryFn: () => api.get<Playbook & { drafts: Draft[] }>(`/playbooks/${id}`), refetchInterval: 10000 })
  const stage = useMutation({ mutationFn: (to: Stage) => api.post<Playbook>(`/playbooks/${id}/stage`, { stage: to, why: 'set from console' }), onSuccess: pb => { toast(`Now in ${STAGE_LABEL[pb.stage]}`, 'ok'); qc.invalidateQueries() }, onError: (e: Error) => toast(e.message, 'bad') })
  const backtest = useMutation({ mutationFn: () => api.post<Backtest>('/playbooks/backtest', { playbook_ids: [id] }), onSuccess: r => { toast(`Backtest: ${r.total.hits}/${r.total.n} would have matched`, 'ok'); qc.invalidateQueries() } })
  const grade = useMutation({ mutationFn: ({ d, g }: { d: string; g: number }) => api.post(`/drafts/${d}/grade`, { grade: g }), onSuccess: () => qc.invalidateQueries() })
  const del = useMutation({ mutationFn: () => api.del(`/playbooks/${id}`), onSuccess: () => { toast('Deleted'); location.assign('/playbooks') } })
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ name: '', summary: '', keywords: '', target: '', template: '' })
  const save = useMutation({
    mutationFn: () => api.patch<Playbook & { trust_reset: boolean }>(`/playbooks/${id}`, {
      name: form.name, summary: form.summary, template: form.template,
      ...(p.trigger.mode === 'reply' ? { keywords: form.keywords.split(',').map(k => k.trim()).filter(Boolean), target: form.target } : {}),
    }),
    onSuccess: r => { toast(r.trust_reset ? 'Saved — it has to earn its trust again' : 'Saved', 'ok'); setEditing(false); qc.invalidateQueries() },
    onError: (e: Error) => toast(e.message, 'bad'),
  })
  const openEdit = () => { setForm({ name: p.name, summary: p.summary || '', keywords: (p.trigger.keywords || []).join(', '), target: p.trigger.target || '', template: p.response.template }); setEditing(true) }
  if (!q.data) return <Spinner />
  const p = q.data
  const t = p.trust
  const cur = LADDER.indexOf(p.stage)
  const next = p.recommendation
  return (
    <>
      <div className="text-[12.5px] muted mb-2"><Link to="/playbooks" className="hover:text-accent">Playbooks</Link> / {p.actor}</div>
      <PageHeader title={<span className="flex items-center gap-3">{p.name}<StagePill stage={p.stage} /></span>}
        subtitle={<span className="flex items-center gap-2 flex-wrap">{p.summary && <span className="w-full mb-1 text-[14px] ink-2">{p.summary}</span>}<Avatar name={p.actor} size={18} /> {p.actor}'s job in {SYSTEM_LABEL[p.system] || p.system}{p.trigger.target ? ` · ${p.trigger.target}` : ''} · seen {p.evidence_count}× · usually answered within {dur(p.median_latency_s || 0)}</span>}
        action={<><Button onClick={openEdit}><Pencil size={15} />Edit</Button><Button onClick={() => backtest.mutate()} loading={backtest.isPending}><FlaskConical size={15} />Backtest</Button><Button variant="ghost" onClick={() => confirm('Delete this playbook and its drafts?') && del.mutate()} title="Delete"><Trash2 size={15} /></Button></>} />

      {/* ladder */}
      <div className="surface p-4 mb-4">
        <div className="grid grid-cols-4 gap-2">
          {LADDER.map((s, i) => {
            const active = i === cur, done = i < cur
            return (
              <div key={s} className={clsx('rounded-lg border px-3 py-2.5', active ? 'border-accent bg-accent-soft' : 'line')}>
                <div className="flex items-center gap-2 mb-0.5"><span className={clsx('w-5 h-5 rounded-full text-[11px] font-bold inline-flex items-center justify-center', done ? 'bg-ok text-white' : active ? 'bg-accent text-white' : 'surface-2 muted')}>{done ? <Check size={12} /> : i + 1}</span><span className="font-semibold">{STAGE_LABEL[s]}</span></div>
                <div className="muted text-[12px] leading-snug">{STAGE_HELP[s]}</div>
                {!active && (
                  <Button size="sm" variant={next?.to === s ? 'primary' : 'ghost'} className="mt-2" loading={stage.isPending && stage.variables === s} onClick={() => stage.mutate(s)}>
                    {next?.to === s && <ArrowRight size={13} />}{i > cur ? 'Move here' : 'Move back'}
                  </Button>
                )}
              </div>
            )
          })}
        </div>
        {next && <div className="mt-3 text-[13px] rounded-lg bg-[rgba(199,150,28,.10)] text-warn px-3 py-2"><b>Recommendation → {STAGE_LABEL[next.to]}.</b> {next.why}</div>}
        {p.stage !== 'retired' && <div className="mt-2 text-right"><button className="muted text-[12px] hover:text-bad" onClick={() => stage.mutate('retired')}>Retire this playbook</button></div>}
      </div>

      <div className="grid grid-cols-5 gap-3.5 mb-5">
        <Stat label="Trust" value={pct(t.trust)} hint="Wilson lower bound of hit rate" tone="accent" />
        <Stat label="Shadow hits" value={`${t.hits}/${t.scored}`} hint={`mean score ${(t.mean_score * 100).toFixed(0)}`} />
        <Stat label="Approvals" value={t.approvals + t.rejections ? `${t.approvals}/${t.approvals + t.rejections}` : '—'} hint={t.approval_rate !== null ? `${pct(t.approval_rate)} approved` : 'none proposed yet'} />
        <Stat label="Executed" value={t.executions} hint="actions taken for real" />
        <Stat label="Undone" value={t.undos} hint="reversed by a human" tone={t.undos ? 'bad' : undefined} />
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <Card title="Trigger" subtitle="What Tacit recognises as this job starting.">
          {p.trigger.mode === 'reply' ? (
            <div className="text-[13.5px] flex flex-col gap-1.5">
              <div><span className="muted">When someone else posts a</span> <Badge>{p.trigger.kind}</Badge> {p.trigger.target && <><span className="muted">in</span> <Badge>{p.trigger.target}</Badge></>}</div>
              <div><span className="muted">containing {p.trigger.match === 'all' ? 'all of' : 'most of'}</span> {(p.trigger.keywords || []).map(k => <Badge key={k} tone="accent" className="mr-1">“{k}”</Badge>)}</div>
              <div className="muted text-[12.5px]">Then {p.actor} normally replies within {dur(p.median_latency_s || 0)}.</div>
            </div>
          ) : <div className="text-[13.5px]"><span className="muted">On a schedule:</span> <Badge tone="accent">{p.trigger.cadence?.human}</Badge> {p.trigger.target && <><span className="muted">in</span> <Badge>{p.trigger.target}</Badge></>}</div>}
        </Card>
        <Card title="Response" subtitle={`What ${p.actor} usually does — the medoid of ${p.evidence_count} real replies.`}>
          <div className="rounded-lg surface-2 p-3 text-[13.5px] whitespace-pre-wrap leading-relaxed max-h-40 overflow-auto">{p.response.template}</div>
          <div className="muted text-[12px] mt-2">Posted via <span className="mono">{p.response.tool}</span> · consistency {pct(p.consistency)}</div>
        </Card>
      </div>

      <Card title="Evidence" subtitle="Real occurrences this pattern was learned from." className="mb-4">
        <Table head={['Trigger', 'What ' + p.actor + ' did', 'When']}>
          {p.examples.map((e, i) => <tr key={i}><Td className="w-[38%] whitespace-pre-wrap">{e.trigger || <span className="muted">(scheduled)</span>}</Td><Td className="whitespace-pre-wrap">{e.response}</Td><Td className="muted whitespace-nowrap">{ago(e.ts)}</Td></tr>)}
        </Table>
      </Card>

      <Card title="Drafts" subtitle="Every time Tacit drafted this job, and how close it came to the real thing. Override a grade if the similarity metric got it wrong.">
        {p.drafts.length === 0 ? <Empty title="No drafts yet" hint="Move to Shadow to start drafting, or run a backtest over history." /> : (
          <Table head={['Trigger', 'Tacit drafted', 'Human actually did', 'Score', 'Status', '']}>
            {p.drafts.map(d => (
              <tr key={d.id} className={clsx(d.mode === 'backtest' && 'opacity-90')}>
                <Td className="w-[22%] whitespace-pre-wrap"><span className="muted text-[12px]">{d.trigger?.actor} · {ago(d.trigger?.ts)}</span><br />{d.trigger?.text?.slice(0, 160)}</Td>
                <Td className="w-[28%] whitespace-pre-wrap">{d.content.text?.slice(0, 240)}</Td>
                <Td className="w-[28%] whitespace-pre-wrap">{d.actual ? d.actual.text.slice(0, 240) : <span className="muted">—</span>}</Td>
                <Td><ScoreDot score={d.score} hit={!!d.score_detail?.hit} /></Td>
                <Td><Badge tone={d.status === 'executed' ? 'accent' : d.status === 'scored' ? 'neutral' : d.status === 'pending' ? 'warn' : 'neutral'}>{d.status}{d.mode === 'backtest' ? ' · backtest' : ''}</Badge>{d.run_id && <div className="mt-1"><Link to={`/runs/${d.run_id}`} className="text-accent text-[12px]">run →</Link></div>}</Td>
                <Td><div className="flex gap-1"><button title="Good draft" className={clsx('p-1 rounded hover:bg-[var(--surface-2)]', d.human_grade === 1 && 'text-ok')} onClick={() => grade.mutate({ d: d.id, g: 1 })}><ThumbsUp size={14} /></button><button title="Bad draft" className={clsx('p-1 rounded hover:bg-[var(--surface-2)]', d.human_grade === -1 && 'text-bad')} onClick={() => grade.mutate({ d: d.id, g: -1 })}><ThumbsDown size={14} /></button></div></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Modal open={editing} onClose={() => setEditing(false)} title="Correct this job" wide>
        <p className="ink2 text-[13.5px] mb-4">A mined job is a hypothesis. Fix what Tacit got wrong — but note that changing <b>how the job is recognised or answered</b> resets the evidence, because the trust score belonged to the old definition.</p>
        <div className="flex flex-col gap-3.5">
          <div><Label>Name</Label><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></div>
          <div><Label>Summary</Label><Input value={form.summary} onChange={e => setForm({ ...form, summary: e.target.value })} placeholder="One line: who does it and what triggers it" /></div>
          {p.trigger.mode === 'reply' && (
            <div className="grid grid-cols-[2fr_1fr] gap-3">
              <div><Label>Trigger keywords <span className="muted font-normal">· comma separated · resets trust</span></Label><Input value={form.keywords} onChange={e => setForm({ ...form, keywords: e.target.value })} /></div>
              <div><Label>Where <span className="muted font-normal">· resets trust</span></Label><Input value={form.target} onChange={e => setForm({ ...form, target: e.target.value })} placeholder="#billing" /></div>
            </div>
          )}
          <div><Label>The usual answer <span className="muted font-normal">· what drafts are modelled on · resets trust</span></Label><Textarea className="min-h-32" value={form.template} onChange={e => setForm({ ...form, template: e.target.value })} /></div>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button><Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Save</Button></div>
        </div>
      </Modal>

      {p.stage_history.length > 0 && <div className="muted text-[12px] mt-4">History: {p.stage_history.map((h, i) => <span key={i}>{i > 0 && ' · '}{h.from} → {h.to} by {h.by} ({when(h.ts)}){h.why ? ` — ${h.why}` : ''}</span>)}</div>}
    </>
  )
}
