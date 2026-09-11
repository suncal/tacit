import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { useState } from 'react'
import { History, RotateCcw, Undo2 } from 'lucide-react'
import { clsx } from 'clsx'
import { api, type Run } from '../lib/api'
import { Badge, Button, Card, Empty, PageHeader, Spinner, Table, Td, useToast } from '../components/ui'
import { ChangePreview } from '../components/DiffView'
import { ago, when } from '../lib/format'

const TX: Record<string, { tone: 'ok' | 'warn' | 'bad' | 'neutral'; label: string }> = { open: { tone: 'warn', label: 'open' }, committed: { tone: 'ok', label: 'committed' }, undone: { tone: 'neutral', label: 'undone' }, partial: { tone: 'bad', label: 'partially undone' } }
const ST: Record<string, 'ok' | 'warn' | 'bad' | 'neutral'> = { done: 'ok', waiting: 'warn', error: 'bad', running: 'neutral' }

export function RunsPage() {
  const q = useQuery({ queryKey: ['runs'], queryFn: () => api.get<{ runs: Run[] }>('/runs?limit=100'), refetchInterval: 8000 })
  if (!q.data) return <Spinner />
  return (
    <>
      <PageHeader title="Runs" subtitle="Every time Tacit acted, as a transaction: what it was asked, what it did, and the recipe to reverse it." />
      {q.data.runs.length === 0 ? <Empty title="No runs yet" /> : (
        <Card>
          <Table head={['When', 'Requested by', 'Input', 'Actions', 'Status', 'Transaction']}>
            {q.data.runs.map(r => (
              <tr key={r.id} className="hover:bg-[var(--surface-2)]">
                <Td className="muted whitespace-nowrap">{ago(r.created_at)}</Td>
                <Td className="mono">{r.principal}{r.replay_of && <Badge className="ml-1">replay</Badge>}</Td>
                <Td className="max-w-md"><Link to={`/runs/${r.id}`} className="hover:text-accent line-clamp-2">{r.input}</Link></Td>
                <Td className="tnum">{r.actions.length}{r.actions.some(a => a.status === 'undone') && <span className="muted"> ({r.actions.filter(a => a.status === 'undone').length} undone)</span>}</Td>
                <Td><Badge tone={ST[r.status]}>{r.status}</Badge></Td>
                <Td><Badge tone={TX[r.tx_status].tone}>{TX[r.tx_status].label}</Badge></Td>
              </tr>
            ))}
          </Table>
        </Card>
      )}
    </>
  )
}

export function RunDetailPage() {
  const { id = '' } = useParams()
  const qc = useQueryClient()
  const toast = useToast()
  const [replay, setReplay] = useState<{ diff: { kind?: string; identical: boolean; overlap: number; original: { tool: string; args: unknown }[]; replayed: { tool: string; args: unknown }[]; original_text?: string; replayed_text?: string; similarity?: number }; output: string; replay_run_id: string } | null>(null)
  const q = useQuery({ queryKey: ['run', id], queryFn: () => api.get<Run & { messages: unknown[] }>(`/runs/${id}`), refetchInterval: 6000 })
  const undo = useMutation({ mutationFn: () => api.post<{ tx_status: string; results: { undone: boolean; why?: string }[] }>(`/runs/${id}/undo`), onSuccess: r => { toast(`${r.results.filter(x => x.undone).length} action(s) reversed`, 'ok'); qc.invalidateQueries() }, onError: (e: Error) => toast(e.message, 'bad') })
  const rep = useMutation({ mutationFn: () => api.post<typeof replay>(`/runs/${id}/replay`), onSuccess: r => { setReplay(r); qc.invalidateQueries() }, onError: (e: Error) => toast(e.message, 'bad') })
  if (!q.data) return <Spinner />
  const r = q.data
  const reversible = r.actions.filter(a => a.status === 'done' && a.undo).length
  return (
    <>
      <div className="text-[12.5px] muted mb-2"><Link to="/runs" className="hover:text-accent">Runs</Link> / {r.id}</div>
      <PageHeader title={<span className="flex items-center gap-2">Run <Badge tone={ST[r.status]}>{r.status}</Badge><Badge tone={TX[r.tx_status].tone}>{TX[r.tx_status].label}</Badge></span>}
        subtitle={<span><span className="mono">{r.principal}</span> in <span className="mono">{r.channel}</span> · {when(r.created_at)}{r.usage?.model && <> · {r.usage.model}{r.usage.usd ? ` · $${r.usage.usd.toFixed(4)}` : ''}</>}{r.playbook_id && <> · <Link to={`/playbooks/${r.playbook_id}`} className="text-accent">playbook →</Link></>}{r.replay_of && <> · replay of <Link to={`/runs/${r.replay_of}`} className="text-accent">{r.replay_of.slice(0, 12)}…</Link></>}</span>}
        action={<><Button onClick={() => rep.mutate()} loading={rep.isPending} title="Re-run the recorded transcript against the current brain, with no side effects"><History size={15} />Replay</Button><Button variant={reversible ? 'danger' : 'secondary'} disabled={!reversible} onClick={() => confirm(`Reverse ${reversible} action(s)?`) && undo.mutate()} loading={undo.isPending}><Undo2 size={15} />Undo {reversible ? `(${reversible})` : ''}</Button></>} />

      <div className="grid grid-cols-[1fr_1fr] gap-4">
        <Card title="Transcript">
          <div className="rounded-lg surface-2 p-3 text-[13.5px] whitespace-pre-wrap mb-3"><span className="muted text-[11.5px] uppercase tracking-wide block mb-1">Input</span>{r.input}</div>
          <ol className="flex flex-col gap-2">
            {r.steps.map((s, i) => (
              <li key={i} className="flex gap-2.5 text-[13.5px]">
                <span className={clsx('mt-1.5 w-2 h-2 rounded-full shrink-0', s.type === 'say' ? 'bg-[var(--line-strong)]' : s.type === 'approval' ? 'bg-stage-propose' : s.type === 'error' ? 'bg-bad' : s.ok ? 'bg-ok' : 'bg-bad')} />
                <div className="min-w-0 flex-1">
                  {s.type === 'say' && <div className="whitespace-pre-wrap">{s.text}</div>}
                  {s.type === 'tool' && <div><span className="mono font-medium">{s.name}</span> <span className="mono muted">{JSON.stringify(s.args).slice(0, 140)}</span> {s.ok ? <Badge tone="ok">ok</Badge> : <Badge tone="bad">{s.text}</Badge>}{s.reversible === false && <Badge tone="warn" className="ml-1">irreversible</Badge>}{s.replayed && <Badge className="ml-1">replayed</Badge>}</div>}
                  {s.type === 'approval' && <div><span className="mono font-medium">{s.name}</span> <Badge tone="warn">waiting for approval</Badge> <Link to="/inbox" className="text-accent text-[12.5px]">Inbox →</Link></div>}
                  {s.type === 'error' && <div className="text-bad">{s.text}</div>}
                </div>
              </li>
            ))}
          </ol>
          {r.output && <div className="rounded-lg border line p-3 text-[13.5px] whitespace-pre-wrap mt-3"><span className="muted text-[11.5px] uppercase tracking-wide block mb-1">Output</span>{r.output}</div>}
        </Card>
        <div className="flex flex-col gap-4">
          <Card title={`Actions (${r.actions.length})`} subtitle="Writes that happened, with their undo recipe.">
            {r.actions.length === 0 ? <div className="muted text-[13px]">No writes — this run only read.</div> : (
              <div className="flex flex-col gap-3">
                {r.actions.map(a => (
                  <div key={a.id} className={clsx(a.status === 'undone' && 'opacity-60')}>
                    <div className="flex items-center gap-2 mb-1.5 text-[12.5px]"><Badge tone={a.status === 'done' ? 'ok' : a.status === 'undone' ? 'neutral' : 'bad'}>{a.status}</Badge><span className="muted">{when(a.ts)}</span>{a.undo ? <span className="muted ml-auto">undo: <span className="mono">{a.undo.tool}</span></span> : <Badge tone="warn" className="ml-auto">irreversible</Badge>}</div>
                    <ChangePreview preview={a.preview} tool={a.tool} args={a.args} />
                  </div>
                ))}
              </div>
            )}
          </Card>
          {replay && (
            <Card title={<span className="flex items-center gap-2"><RotateCcw size={15} />Replay result</span>} subtitle={replay.diff.kind === 'draft' ? (replay.diff.identical ? 'The current brain drafts exactly the same text.' : `The current brain drafts differently — ${((replay.diff.similarity || 0) * 100).toFixed(0)}% similar to what ran.`) : replay.diff.identical ? 'The current brain made exactly the same decisions.' : `Decisions differ — ${(replay.diff.overlap * 100).toFixed(0)}% of the original actions were repeated.`}>
              {replay.diff.kind === 'draft' ? (
                <div className="grid grid-cols-2 gap-3 text-[13px]"><div><div className="muted uppercase text-[11px] tracking-wide mb-1">What ran</div><div className="rounded-lg surface-2 p-2.5 whitespace-pre-wrap">{replay.diff.original_text}</div></div><div><div className="muted uppercase text-[11px] tracking-wide mb-1">Replayed now</div><div className="rounded-lg border border-accent/40 p-2.5 whitespace-pre-wrap">{replay.diff.replayed_text}</div></div></div>
              ) : (
              <div className="grid grid-cols-2 gap-3 text-[12.5px]">
                <div><div className="muted uppercase text-[11px] tracking-wide mb-1">Original</div>{replay.diff.original.map((c, i) => <div key={i} className="mono truncate">{c.tool}({JSON.stringify(c.args).slice(0, 60)})</div>)}</div>
                <div><div className="muted uppercase text-[11px] tracking-wide mb-1">Replayed</div>{replay.diff.replayed.map((c, i) => <div key={i} className={clsx('mono truncate', !replay.diff.original.some(o => o.tool === c.tool && JSON.stringify(o.args) === JSON.stringify(c.args)) && 'text-warn')}>{c.tool}({JSON.stringify(c.args).slice(0, 60)})</div>)}</div>
              </div>)}
              <div className="mt-2 text-[12.5px]"><Link to={`/runs/${replay.replay_run_id}`} className="text-accent">Open replay run →</Link></div>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
