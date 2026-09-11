import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { clsx } from 'clsx'
import { api, type Draft } from '../lib/api'
import { Avatar, Badge, Button, Empty, PageHeader, ScoreDot, Spinner, StagePill } from '../components/ui'
import { ago } from '../lib/format'

const TABS = [['all', 'All'], ['pending', 'Waiting for the human'], ['scored', 'Graded'], ['executed', 'Executed'], ['expired', 'Expired']] as const

export function ShadowPage() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<string>('all')
  const [mode, setMode] = useState<'live' | 'all'>('live')
  const q = useQuery({ queryKey: ['drafts', tab, mode], queryFn: () => api.get<{ drafts: Draft[] }>(`/drafts?mode=${mode}${tab !== 'all' ? `&status=${tab}` : ''}&limit=200`), refetchInterval: 8000 })
  const grade = useMutation({ mutationFn: ({ d, g }: { d: string; g: number }) => api.post(`/drafts/${d}/grade`, { grade: g }), onSuccess: () => qc.invalidateQueries() })
  return (
    <>
      <PageHeader title="Shadow" subtitle="Every draft Tacit wrote in the dark, next to what your teammate actually did. This is where trust comes from."
        action={<div className="flex rounded-lg border line overflow-hidden text-[13px]">{(['live', 'all'] as const).map(m => <button key={m} onClick={() => setMode(m)} className={clsx('px-3 py-1.5', mode === m ? 'bg-accent-soft text-accent font-medium' : 'ink-2')}>{m === 'live' ? 'Live' : 'Live + backtest'}</button>)}</div>} />
      <div className="flex gap-1 mb-4 border-b line">{TABS.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={clsx('px-3 py-2 text-[13.5px] -mb-px border-b-2', tab === k ? 'border-accent text-accent font-medium' : 'border-transparent ink-2')}>{l}</button>)}</div>
      {!q.data ? <Spinner /> : q.data.drafts.length === 0 ? <Empty title="No drafts here" hint="Drafts appear when a playbook in Shadow, Propose or Auto sees its trigger." /> : (
        <div className="flex flex-col gap-3">
          {q.data.drafts.map(d => (
            <div key={d.id} className="surface p-4">
              <div className="flex items-center gap-2 mb-3 text-[12.5px]">
                {d.playbook && <><Link to={`/playbooks/${d.playbook.id}`} className="font-medium hover:text-accent">{d.playbook.name}</Link><StagePill stage={d.playbook.stage} /></>}
                <Badge>{d.status}</Badge>{d.mode === 'backtest' && <Badge>backtest</Badge>}
                <span className="muted ml-auto">{ago(d.created_at)}</span>
                <ScoreDot score={d.score} hit={!!d.score_detail?.hit} />
                <div className="flex gap-0.5 ml-1"><button className={clsx('p-1 rounded hover:bg-[var(--surface-2)]', d.human_grade === 1 && 'text-ok')} onClick={() => grade.mutate({ d: d.id, g: 1 })} title="Good draft"><ThumbsUp size={14} /></button><button className={clsx('p-1 rounded hover:bg-[var(--surface-2)]', d.human_grade === -1 && 'text-bad')} onClick={() => grade.mutate({ d: d.id, g: -1 })} title="Bad draft"><ThumbsDown size={14} /></button></div>
              </div>
              <div className="grid grid-cols-3 gap-3 text-[13.5px]">
                <div><div className="muted text-[11.5px] uppercase tracking-wide mb-1 flex items-center gap-1.5">Trigger {d.trigger && <><Avatar name={d.trigger.actor} size={16} />{d.trigger.actor}</>}</div><div className="rounded-lg surface-2 p-2.5 whitespace-pre-wrap">{d.trigger?.text}</div></div>
                <div><div className="muted text-[11.5px] uppercase tracking-wide mb-1">Tacit drafted</div><div className="rounded-lg border border-accent/40 p-2.5 whitespace-pre-wrap">{d.content.text}</div></div>
                <div><div className="muted text-[11.5px] uppercase tracking-wide mb-1 flex items-center gap-1.5">{d.playbook?.actor || 'human'} actually did</div>{d.actual ? <div className="rounded-lg surface-2 p-2.5 whitespace-pre-wrap">{d.actual.text}</div> : <div className="rounded-lg border border-dashed line p-2.5 muted">{d.status === 'pending' ? 'waiting…' : d.status === 'executed' ? 'Tacit did it' : d.status === 'proposed' ? 'in the Inbox' : '—'}</div>}</div>
              </div>
              {d.run_id && <div className="mt-2 text-[12.5px]"><Link to={`/runs/${d.run_id}`} className="text-accent">View run →</Link></div>}
            </div>
          ))}
        </div>
      )}
      <div className="mt-6"><Button variant="ghost" onClick={() => qc.invalidateQueries()}>Refresh</Button></div>
    </>
  )
}
