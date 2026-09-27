import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Bot, BookOpen, Brain, CornerDownLeft, FileCheck2, FlaskConical, ListChecks, PlayCircle, Receipt, Search, Sparkles, UserRound } from 'lucide-react'
import { clsx } from 'clsx'
import { api } from '../lib/api'
import { useToast } from './ui'

type Row = { kind: string; id: string; title: string; subtitle?: string; to?: string; badge?: string; run?: () => void }

const ICON: Record<string, typeof Search> = {
  playbook: BookOpen, agent: Bot, person: UserRound, run: PlayCircle, memory: Brain, task: ListChecks,
  page: Sparkles, action: FlaskConical, ledger: Receipt, evidence: FileCheck2,
}
const PAGES: Row[] = [
  { kind: 'page', id: 'p1', title: 'Overview', to: '/' },
  { kind: 'page', id: 'p2', title: 'What we found', subtitle: 'the Day-One report', to: '/report' },
  { kind: 'page', id: 'p3', title: 'Inbox', subtitle: 'approvals and corrections', to: '/inbox' },
  { kind: 'page', id: 'p4', title: 'Playbooks', to: '/playbooks' },
  { kind: 'page', id: 'p5', title: 'Shadow', subtitle: 'every draft, graded', to: '/shadow' },
  { kind: 'page', id: 'p6', title: 'People', subtitle: 'bus factor and cover', to: '/people' },
  { kind: 'page', id: 'p7', title: 'Oversight', subtitle: 'AI you already pay for', to: '/oversight' },
  { kind: 'ledger', id: 'p8', title: 'Verified work', subtitle: 'the ledger', to: '/ledger' },
  { kind: 'evidence', id: 'p9', title: 'Evidence', subtitle: 'EU AI Act art. 12 / 14', to: '/compliance' },
  { kind: 'page', id: 'p10', title: 'Runs', to: '/runs' },
  { kind: 'page', id: 'p11', title: 'Audit log', to: '/audit' },
  { kind: 'page', id: 'p12', title: 'Settings', to: '/settings' },
]

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const [hits, setHits] = useState<Row[]>([])
  const nav = useNavigate(); const qc = useQueryClient(); const toast = useToast()
  const input = useRef<HTMLInputElement>(null)

  const mine = useMutation({ mutationFn: () => api.post<{ found: number; created: number; named: number }>('/playbooks/mine'), onSuccess: r => { toast(`Mined ${r.found} jobs (${r.created} new)`, 'ok'); qc.invalidateQueries() } })
  const backtest = useMutation({ mutationFn: () => api.post<{ total: { n: number; hits: number } }>('/playbooks/backtest', {}), onSuccess: r => { toast(`Backtest: ${r.total.hits}/${r.total.n} would have matched`, 'ok'); qc.invalidateQueries() } })
  const report = useMutation({ mutationFn: () => api.post('/pilot/report'), onSuccess: () => { toast('Report regenerated', 'ok'); qc.invalidateQueries(); nav('/report') } })

  const ACTIONS: Row[] = useMemo(() => [
    { kind: 'action', id: 'a1', title: 'Mine patterns', subtitle: 'find repeating jobs in what has been observed', run: () => mine.mutate() },
    { kind: 'action', id: 'a2', title: 'Backtest every job', subtitle: 'what would it have done with history', run: () => backtest.mutate() },
    { kind: 'action', id: 'a3', title: 'Regenerate the Day-One report', run: () => report.mutate() },
  ], [mine, backtest, report])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setOpen(o => !o) }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  useEffect(() => { if (open) { setQ(''); setSel(0); setTimeout(() => input.current?.focus(), 10) } }, [open])
  useEffect(() => {
    if (!q.trim()) { setHits([]); return }
    let alive = true
    const t = setTimeout(async () => {
      try { const r = await api.get<{ results: Row[] }>(`/search?q=${encodeURIComponent(q)}`); if (alive) setHits(r.results) } catch { /* palette stays usable offline */ }
    }, 130)
    return () => { alive = false; clearTimeout(t) }
  }, [q])

  const local = useMemo(() => {
    const n = q.trim().toLowerCase()
    const match = (r: Row) => !n || r.title.toLowerCase().includes(n) || (r.subtitle || '').toLowerCase().includes(n)
    return [...ACTIONS.filter(match), ...PAGES.filter(match)]
  }, [q, ACTIONS])
  const rows = useMemo(() => [...local, ...hits].slice(0, 24), [local, hits])
  useEffect(() => { setSel(s => Math.min(s, Math.max(0, rows.length - 1))) }, [rows.length])

  if (!open) return null
  const go = (r?: Row) => { if (!r) return; setOpen(false); if (r.run) r.run(); else if (r.to) nav(r.to) }

  return (
    <div className="fixed inset-0 z-[60] bg-black/40 backdrop-blur-[3px] flex items-start justify-center p-6 no-print" onClick={() => setOpen(false)}>
      <div className="surface w-full max-w-[620px] mt-[12vh] shadow-[var(--shadow-lg)] overflow-hidden" onClick={e => e.stopPropagation()} role="dialog" aria-modal>
        <div className="flex items-center gap-3 px-4 h-12 border-b line">
          <Search size={16} className="muted shrink-0" />
          <input ref={input} value={q} onChange={e => setQ(e.target.value)} placeholder="Search jobs, people, agents, runs — or run something"
            className="flex-1 bg-transparent outline-none text-[14px] placeholder:text-[var(--muted)]"
            onKeyDown={e => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, rows.length - 1)) }
              if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(s - 1, 0)) }
              if (e.key === 'Enter') { e.preventDefault(); go(rows[sel]) }
            }} />
          <kbd className="mono text-[10.5px] muted border line rounded px-1.5 py-0.5">esc</kbd>
        </div>
        <div className="max-h-[52vh] overflow-y-auto py-1.5">
          {rows.length === 0 && <div className="px-4 py-8 text-center muted text-[13px]">Nothing matches “{q}”.</div>}
          {rows.map((r, i) => {
            const Icon = ICON[r.kind] || Search
            return (
              <button key={`${r.kind}-${r.id}`} onMouseEnter={() => setSel(i)} onClick={() => go(r)}
                className={clsx('w-full flex items-center gap-3 px-4 py-2 text-left', i === sel ? 'bg-accent-soft' : 'hover:bg-[var(--surface-2)]')}>
                <Icon size={15} className={clsx('shrink-0', i === sel ? 'text-accent' : 'muted')} />
                <div className="min-w-0 flex-1"><div className="text-[13.5px] font-medium truncate">{r.title}</div>{r.subtitle && <div className="muted text-[12px] truncate">{r.subtitle}</div>}</div>
                {r.badge && <span className="mono text-[10.5px] muted">{r.badge}</span>}
                {i === sel && <CornerDownLeft size={13} className="text-accent shrink-0" />}
              </button>
            )
          })}
        </div>
        <div className="flex items-center gap-4 px-4 h-9 border-t line text-[11.5px] muted">
          <span><kbd className="mono">↑↓</kbd> move</span><span><kbd className="mono">↵</kbd> open</span><span className="ml-auto">Tacit</span>
        </div>
      </div>
    </div>
  )
}
