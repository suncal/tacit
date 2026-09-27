import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, Check, X } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../lib/api'
import { Button, useToast } from './ui'

type Step = { id: string; title: string; detail: string; done: boolean; hint: string; to: string; action?: string }
type State = { steps: Step[]; done: number; total: number; complete: boolean; dismissed: boolean }

/** The shortest honest path from installed to useful. Every tick is checked against real state, never a cookie. */
export function Onboarding() {
  const qc = useQueryClient(); const toast = useToast()
  const q = useQuery({ queryKey: ['onboarding'], queryFn: () => api.get<State>('/onboarding') })
  const dismiss = useMutation({ mutationFn: () => api.post('/onboarding/dismiss'), onSuccess: () => qc.invalidateQueries({ queryKey: ['onboarding'] }) })
  const run = useMutation({
    mutationFn: (action: string) => action === 'mine' ? api.post<{ found: number; created: number }>('/playbooks/mine') : api.post('/playbooks/backtest', {}),
    onSuccess: () => { toast('Done — the checklist updated itself', 'ok'); qc.invalidateQueries() },
    onError: (e: Error) => toast(e.message, 'bad'),
  })
  if (!q.data || q.data.dismissed || q.data.complete) return null
  const s = q.data
  const next = s.steps.find(x => !x.done)
  return (
    <div className="surface raised mb-5 overflow-hidden">
      <div className="flex items-center gap-4 px-5 py-3.5 border-b line">
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          <div className="text-[14px] font-semibold tracking-[-0.015em]">Get to your first result</div>
          <div className="flex items-center gap-1.5">{s.steps.map(x => <span key={x.id} className={clsx('h-1 w-6 rounded-full', x.done ? 'bg-accent' : 'bg-[var(--surface-3)]')} />)}</div>
          <span className="muted text-[12.5px] tnum">{s.done}/{s.total}</span>
        </div>
        <button className="muted hover:text-[var(--ink)] p-1 -m-1" onClick={() => dismiss.mutate()} title="Hide this"><X size={15} /></button>
      </div>
      <div className="grid grid-cols-3 gap-px bg-[var(--line)]">
        {s.steps.map(x => (
          <div key={x.id} className={clsx('bg-[var(--surface)] p-4', !x.done && x.id === next?.id && 'bg-accent-soft')}>
            <div className="flex items-start gap-2.5">
              <span className={clsx('mt-[1px] w-[18px] h-[18px] rounded-full inline-flex items-center justify-center shrink-0 text-[10px] font-bold',
                x.done ? 'bg-accent text-white' : 'surface-3 muted ring-1 ring-inset ring-[var(--line-strong)]')}>{x.done ? <Check size={11} /> : ''}</span>
              <div className="min-w-0">
                <div className="text-[13.5px] font-medium leading-snug">{x.title}</div>
                <div className="muted text-[12px] mt-1 leading-relaxed">{x.detail}</div>
                <div className="mono text-[11px] mt-1.5 truncate" title={x.hint}>{x.hint}</div>
                {!x.done && (
                  <div className="mt-2.5 flex gap-2">
                    {x.action && <Button size="sm" variant="primary" loading={run.isPending && run.variables === x.action} onClick={() => run.mutate(x.action!)}>Do it now</Button>}
                    <Link to={x.to}><Button size="sm" variant={x.action ? 'ghost' : 'secondary'}>Open<ArrowRight size={13} /></Button></Link>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
