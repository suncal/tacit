import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Check, X } from 'lucide-react'
import { api, type Approval, type Run } from '../lib/api'
import { Badge, Button, Empty, PageHeader, Spinner, StagePill, useToast } from '../components/ui'
import { ChangePreview } from '../components/DiffView'
import { ago, pct } from '../lib/format'

export function InboxPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['approvals'], queryFn: () => api.get<{ approvals: Approval[] }>('/approvals'), refetchInterval: 6000 })
  const done = useQuery({ queryKey: ['approvals', 'all'], queryFn: () => api.get<{ approvals: Approval[] }>('/approvals?status=all') })
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
              <div className="flex items-center gap-2 mb-3 text-[13px]">
                {a.playbook ? <><Link to={`/playbooks/${a.playbook.id}`} className="font-semibold hover:text-accent">{a.playbook.name}</Link><StagePill stage={a.playbook.stage} /><Badge tone="accent" className="whitespace-nowrap">trust {pct(a.playbook.trust)}</Badge></> : <span className="font-semibold">{a.tool}</span>}
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
      {recent.length > 0 && (
        <div className="mt-8"><div className="font-semibold mb-2">Recent decisions</div>
          <div className="surface divide-y divide-[var(--line)]">{recent.map(a => <div key={a.id} className="flex items-center gap-3 px-4 py-2.5 text-[13px]"><Badge tone={a.status === 'approved' ? 'ok' : 'bad'}>{a.status}</Badge><span className="font-medium">{a.playbook?.name || a.tool}</span><span className="muted">{a.preview?.summary}</span><span className="muted ml-auto">by {a.decided_by} · {ago(a.decided_at)}</span></div>)}</div>
        </div>
      )}
    </>
  )
}
