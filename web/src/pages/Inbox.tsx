import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Check, X } from 'lucide-react'
import { useState } from 'react'
import { api, type Approval, type Lesson, type Run } from '../lib/api'
import { Badge, Button, Empty, PageHeader, Spinner, StagePill, Textarea, useToast } from '../components/ui'
import { ChangePreview } from '../components/DiffView'
import { ago, pct } from '../lib/format'

export function InboxPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['approvals'], queryFn: () => api.get<{ approvals: Approval[] }>('/approvals'), refetchInterval: 6000 })
  const done = useQuery({ queryKey: ['approvals', 'all'], queryFn: () => api.get<{ approvals: Approval[] }>('/approvals?status=all') })
  const lessons = useQuery({ queryKey: ['lessons'], queryFn: () => api.get<{ lessons: Lesson[] }>('/lessons'), refetchInterval: 8000 })
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const answer = useMutation({ mutationFn: ({ id, text }: { id: string; text: string }) => api.post(`/lessons/${id}/answer`, { answer: text }), onSuccess: () => { toast('Rule saved — future drafts will follow it', 'ok'); qc.invalidateQueries() } })
  const dismiss = useMutation({ mutationFn: (id: string) => api.post(`/lessons/${id}/dismiss`), onSuccess: () => qc.invalidateQueries({ queryKey: ['lessons'] }) })
  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) => api.post<{ run: Run }>(`/approvals/${id}/decide`, { approve }),
    onSuccess: (r, v) => { toast(v.approve ? (r.run.status === 'done' ? 'Approved and executed' : 'Approved') : 'Denied — nothing happened', 'ok'); qc.invalidateQueries() },
    onError: (e: Error) => toast(e.message, 'bad'),
  })
  if (!q.data) return <Spinner />
  const items = q.data.approvals
  const recent = (done.data?.approvals || []).filter(a => a.status !== 'pending').slice(0, 8)
  return (
    <>
      <PageHeader title="Inbox" subtitle="Actions waiting for a human. You see exactly what will change before it changes. Approve executes it — reversibly." />
      {items.length === 0 ? <Empty title="Nothing waiting" hint="Write and exec actions pause here. Playbooks in Propose land here every time they trigger." /> : (
        <div className="flex flex-col gap-4">
          {items.map(a => (
            <div key={a.id} className="surface p-4 border-l-4 border-l-stage-propose">
              <div className="flex items-center gap-2 mb-3 text-[13px] flex-wrap">
                {a.playbook ? <><Link to={`/playbooks/${a.playbook.id}`} className="font-semibold hover:text-accent">{a.playbook.name}</Link><StagePill stage={a.playbook.stage} /><Badge tone="accent" className="whitespace-nowrap">trust {pct(a.playbook.trust)}</Badge></> : <span className="font-semibold">{a.tool}</span>}
                {a.escalated && <Badge tone="bad" className="whitespace-nowrap">escalated · looks unlike anything seen ({pct(a.confidence)} confidence)</Badge>}
                {!a.escalated && a.confidence !== null && a.confidence !== undefined && <Badge tone={a.confidence >= 0.7 ? 'ok' : 'warn'} className="whitespace-nowrap">confidence {pct(a.confidence)}</Badge>}
                <span className="muted">requested by <span className="mono">{a.principal}</span> · {ago(a.created_at)} · {a.reason}</span>
                <div className="ml-auto flex gap-2">
                  <Button variant="success" size="sm" loading={decide.isPending && decide.variables?.id === a.id && decide.variables.approve} onClick={() => decide.mutate({ id: a.id, approve: true })}><Check size={14} />Approve</Button>
                  <Button variant="secondary" size="sm" onClick={() => decide.mutate({ id: a.id, approve: false })}><X size={14} />Deny</Button>
                </div>
              </div>
              <ChangePreview preview={a.preview} tool={a.tool} args={a.args} />
              <div className="mt-2 text-[12.5px] muted"><Link to={`/runs/${a.run_id}`} className="hover:text-accent">Run {a.run_id.slice(0, 12)}… →</Link></div>
            </div>
          ))}
        </div>
      )}
      {(lessons.data?.lessons.length || 0) > 0 && (
        <div className="mt-8">
          <div className="font-semibold mb-1">Teach</div>
          <p className="muted text-[13px] mb-3">Tacit's draft missed what the owner actually did. One sentence from you becomes a rule every future draft follows.</p>
          <div className="flex flex-col gap-3">
            {lessons.data!.lessons.map(l => (
              <div key={l.id} className="surface p-4 border-l-4 border-l-stage-shadow">
                <div className="flex items-center gap-2 text-[13px] mb-3">{l.playbook && <><Link to={`/playbooks/${l.playbook.id}`} className="font-semibold hover:text-accent">{l.playbook.name}</Link><StagePill stage={l.playbook.stage} /></>}<span className="muted">{ago(l.created_at)}</span></div>
                <div className="grid grid-cols-3 gap-3 text-[13px] mb-3">
                  <div><div className="muted text-[11px] uppercase tracking-wide mb-1">Trigger</div><div className="rounded-lg surface-2 p-2.5 whitespace-pre-wrap">{l.trigger_text}</div></div>
                  <div><div className="muted text-[11px] uppercase tracking-wide mb-1">Tacit drafted</div><div className="rounded-lg border border-bad/40 p-2.5 whitespace-pre-wrap">{l.draft_text}</div></div>
                  <div><div className="muted text-[11px] uppercase tracking-wide mb-1">{l.playbook?.actor} actually did</div><div className="rounded-lg surface-2 p-2.5 whitespace-pre-wrap">{l.actual_text}</div></div>
                </div>
                <div className="font-medium text-[13.5px] mb-1.5">{l.question}</div>
                {l.suggestion && !(l.id in answers) && (
                  <div className="rounded-lg surface-2 p-3 mb-2 text-[13px]">
                    <div className="eyebrow mb-1.5">Proposed rule</div>
                    <div className="ink-2 leading-relaxed">{l.suggestion}</div>
                    <div className="flex gap-2 mt-2.5">
                      <Button size="sm" variant="primary" loading={answer.isPending} onClick={() => answer.mutate({ id: l.id, text: l.suggestion! })}>That's right</Button>
                      <Button size="sm" variant="ghost" onClick={() => setAnswers({ ...answers, [l.id]: l.suggestion! })}>Edit it</Button>
                      <Button size="sm" variant="ghost" onClick={() => dismiss.mutate(l.id)}>Just this once</Button>
                    </div>
                  </div>
                )}
                {(!l.suggestion || l.id in answers) && (<>
                  <Textarea className="min-h-16" placeholder="e.g. Dependency bumps don't get a first-pass review — just merge on green." value={answers[l.id] || ''} onChange={e => setAnswers({ ...answers, [l.id]: e.target.value })} />
                  <div className="flex gap-2 mt-2"><Button variant="primary" size="sm" disabled={!answers[l.id]?.trim()} loading={answer.isPending} onClick={() => answer.mutate({ id: l.id, text: answers[l.id] })}>Save rule</Button><Button variant="ghost" size="sm" onClick={() => dismiss.mutate(l.id)}>Not a rule, just this once</Button></div>
                </>)}
              </div>
            ))}
          </div>
        </div>
      )}
      {recent.length > 0 && (
        <div className="mt-8"><div className="font-semibold mb-2">Recent decisions</div>
          <div className="surface divide-y divide-[var(--line)]">{recent.map(a => <div key={a.id} className="flex items-center gap-3 px-4 py-2.5 text-[13px]"><Badge tone={a.status === 'approved' ? 'ok' : 'bad'}>{a.status}</Badge><span className="font-medium">{a.playbook?.name || a.tool}</span><span className="muted">{a.preview?.summary}</span><span className="muted ml-auto">by {a.decided_by} · {ago(a.decided_at)}</span></div>)}</div>
        </div>
      )}
    </>
  )
}
