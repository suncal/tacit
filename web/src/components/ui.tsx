import { clsx } from 'clsx'
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { Loader2, X } from 'lucide-react'
import { STAGE_LABEL } from '../lib/format'
import type { Stage } from '../lib/api'

/* -------------------------------------------------------------------------- buttons */
type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'; size?: 'sm' | 'md'; loading?: boolean }
export function Button({ variant = 'secondary', size = 'md', loading, className, children, disabled, ...rest }: BtnProps) {
  const base = 'inline-flex items-center justify-center gap-1.5 rounded-[9px] font-medium tracking-[-0.01em] transition-[background,box-shadow,opacity] duration-150 disabled:opacity-45 disabled:pointer-events-none whitespace-nowrap select-none'
  const sizes = size === 'sm' ? 'h-8 px-2.5 text-[13px]' : 'h-9 px-3.5 text-[13.5px]'
  const variants = {
    primary: 'bg-accent text-white shadow-[inset_0_1px_0_rgba(255,255,255,.14)] hover:bg-accent-strong',
    secondary: 'bg-[var(--surface)] border border-[var(--line-strong)] hover:bg-[var(--surface-2)] shadow-[var(--shadow-sm)]',
    ghost: 'text-[var(--ink-2)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)]',
    danger: 'bg-bad text-white hover:opacity-90',
    success: 'bg-ok text-white hover:opacity-90',
  }[variant]
  return <button className={clsx(base, sizes, variants, className)} disabled={disabled || loading} {...rest}>{loading && <Loader2 size={14} className="animate-spin" />}{children}</button>
}

/* -------------------------------------------------------------------------- surfaces */
export function Card({ className, children, title, action, subtitle, flush }: { className?: string; children: ReactNode; title?: ReactNode; action?: ReactNode; subtitle?: ReactNode; flush?: boolean }) {
  return (
    <section className={clsx('surface raised overflow-hidden', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-4 px-5 py-4 border-b line">
          <div className="min-w-0"><h3 className="text-[14.5px] font-semibold tracking-[-0.015em] leading-5">{title}</h3>{subtitle && <p className="muted text-[12.5px] mt-1 leading-relaxed">{subtitle}</p>}</div>
          {action && <div className="shrink-0 flex items-center gap-2">{action}</div>}
        </header>
      )}
      <div className={clsx(flush ? '' : 'p-5')}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'accent' | 'ok' | 'warn' | 'bad' }) {
  const color = tone === 'accent' ? 'text-accent' : tone === 'ok' ? 'text-ok' : tone === 'warn' ? 'text-warn' : tone === 'bad' ? 'text-bad' : ''
  return (
    <div className="surface raised px-5 py-4">
      <div className="eyebrow">{label}</div>
      <div className={clsx('tnum text-[29px] font-semibold leading-none tracking-[-0.035em] mt-2.5', color)}>{value}</div>
      {hint && <div className="muted text-[12.5px] mt-2 leading-snug">{hint}</div>}
    </div>
  )
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="text-center py-14 px-6 rounded-xl border border-dashed line">
      <div className="font-semibold tracking-[-0.015em]">{title}</div>
      {hint && <div className="muted text-[13px] mt-1.5 max-w-lg mx-auto leading-relaxed">{hint}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/* -------------------------------------------------------------------------- badges */
export function Badge({ children, tone = 'neutral', className }: { children: ReactNode; tone?: 'neutral' | 'ok' | 'warn' | 'bad' | 'accent' | 'violet'; className?: string }) {
  const t = {
    neutral: 'bg-[var(--surface-2)] text-[var(--ink-2)] ring-[var(--line)]',
    ok: 'bg-[color-mix(in_srgb,var(--color-ok)_12%,transparent)] text-ok ring-[color-mix(in_srgb,var(--color-ok)_22%,transparent)]',
    warn: 'bg-[color-mix(in_srgb,var(--color-warn)_13%,transparent)] text-warn ring-[color-mix(in_srgb,var(--color-warn)_24%,transparent)]',
    bad: 'bg-[color-mix(in_srgb,var(--color-bad)_11%,transparent)] text-bad ring-[color-mix(in_srgb,var(--color-bad)_22%,transparent)]',
    accent: 'bg-accent-soft text-accent ring-[color-mix(in_srgb,var(--color-accent)_22%,transparent)]',
    violet: 'bg-[color-mix(in_srgb,var(--color-stage-shadow)_13%,transparent)] text-stage-shadow ring-[color-mix(in_srgb,var(--color-stage-shadow)_24%,transparent)]',
  }[tone]
  return <span className={clsx('inline-flex items-center gap-1.5 rounded-md px-1.5 py-[2px] text-[11px] font-medium tracking-[.01em] ring-1 ring-inset whitespace-nowrap', t, className)}>{children}</span>
}

const STAGE_TONE: Record<Stage, 'neutral' | 'violet' | 'warn' | 'accent'> = { candidate: 'neutral', shadow: 'violet', propose: 'warn', auto: 'accent', retired: 'neutral' }
export function StagePill({ stage, className }: { stage: Stage; className?: string }) {
  return (
    <Badge tone={STAGE_TONE[stage]} className={className}>
      <span className={clsx('w-[5px] h-[5px] rounded-full', { 'bg-stage-candidate': stage === 'candidate', 'bg-stage-shadow': stage === 'shadow', 'bg-stage-propose': stage === 'propose', 'bg-stage-auto': stage === 'auto', 'bg-stage-retired': stage === 'retired' })} />
      {STAGE_LABEL[stage]}
    </Badge>
  )
}

export function RiskPill({ risk }: { risk: 'read' | 'write' | 'exec' }) {
  return <Badge tone={risk === 'read' ? 'ok' : risk === 'write' ? 'warn' : 'bad'}>{risk}</Badge>
}

export function Avatar({ name, size = 22 }: { name: string; size?: number }) {
  const hue = [...name].reduce((a, c) => a + c.charCodeAt(0), 0) % 360
  return (
    <span className="inline-flex items-center justify-center rounded-full font-semibold shrink-0 ring-1 ring-inset ring-black/5"
      style={{ width: size, height: size, fontSize: Math.max(9, size * 0.42), background: `hsl(${hue} 32% 88%)`, color: `hsl(${hue} 45% 28%)` }} title={name}>
      {name.slice(0, 1).toUpperCase()}
    </span>
  )
}

/* -------------------------------------------------------------------------- measures */
export function TrustBar({ value, scored, className }: { value: number; scored?: number; className?: string }) {
  const tone = value >= 0.6 ? 'bg-ok' : value >= 0.3 ? 'bg-warn' : 'bg-[var(--line-strong)]'
  return (
    <div className={clsx('flex items-center gap-2.5', className)}>
      <div className="h-1 flex-1 rounded-full bg-[var(--surface-3)] overflow-hidden"><div className={clsx('h-full rounded-full', tone)} style={{ width: `${Math.max(2, value * 100)}%` }} /></div>
      <span className="tnum text-[12.5px] font-medium w-9 text-right">{(value * 100).toFixed(0)}%</span>
      {scored !== undefined && <span className="muted text-[11.5px] w-12 tnum">n={scored}</span>}
    </div>
  )
}

export function ScoreDot({ score, hit }: { score: number | null; hit?: boolean }) {
  if (score === null || score === undefined) return <span className="muted">—</span>
  return <span className={clsx('inline-flex items-center gap-1.5 tnum font-medium text-[12.5px]', hit ? 'text-ok' : 'text-bad')}><span className={clsx('w-[6px] h-[6px] rounded-full', hit ? 'bg-ok' : 'bg-bad')} />{(score * 100).toFixed(0)}</span>
}

/* -------------------------------------------------------------------------- inputs */
const field = 'w-full rounded-[9px] border border-[var(--line-strong)] bg-[var(--surface)] text-[13.5px] placeholder:text-[var(--muted)] shadow-[var(--shadow-sm)] transition-shadow focus:border-accent focus:shadow-[0_0_0_3px_var(--ring)] focus:outline-none'
export const Input = (p: React.InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={clsx(field, 'h-9 px-3', p.className)} />
export const Textarea = (p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={clsx(field, 'px-3 py-2 min-h-24 leading-relaxed', p.className)} />
export const Select = (p: React.SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={clsx(field, 'h-9 px-2.5 pr-8 w-auto', p.className)} />
export const Label = ({ children }: { children: ReactNode }) => <label className="block text-[12.5px] font-medium ink-2 mb-1.5">{children}</label>

/* -------------------------------------------------------------------------- toast */
type Toast = { id: number; text: string; tone?: 'ok' | 'bad' }
const ToastCtx = createContext<(text: string, tone?: 'ok' | 'bad') => void>(() => {})
export const useToast = () => useContext(ToastCtx)
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((text: string, tone?: 'ok' | 'bad') => {
    const id = Date.now() + Math.random()
    setItems(i => [...i, { id, text, tone }])
    setTimeout(() => setItems(i => i.filter(t => t.id !== id)), 3400)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 no-print">
        {items.map(t => (
          <div key={t.id} className="surface px-4 py-2.5 text-[13.5px] shadow-[var(--shadow-lg)] flex items-center gap-2.5 min-w-56">
            <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', t.tone === 'bad' ? 'bg-bad' : t.tone === 'ok' ? 'bg-ok' : 'bg-accent')} />{t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}

/* -------------------------------------------------------------------------- modal */
export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose(); if (open) window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 bg-black/45 backdrop-blur-[2px] flex items-start justify-center p-6 overflow-auto no-print" onClick={onClose}>
      <div className={clsx('surface w-full shadow-[var(--shadow-lg)] mt-8 mb-8', wide ? 'max-w-5xl' : 'max-w-xl')} onClick={e => e.stopPropagation()} role="dialog" aria-modal>
        <header className="flex items-center justify-between gap-4 px-5 py-3.5 border-b line"><h3 className="font-semibold tracking-[-0.015em]">{title}</h3><button onClick={onClose} className="muted hover:text-[var(--ink)] p-1 -m-1 rounded" aria-label="Close"><X size={16} /></button></header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export const Spinner = () => <div className="flex justify-center py-16"><Loader2 className="animate-spin text-[var(--line-strong)]" size={22} /></div>

export function Kbd({ children }: { children: ReactNode }) { return <kbd className="mono rounded border line px-1.5 py-0.5 text-[11px] surface-2">{children}</kbd> }

/* -------------------------------------------------------------------------- page chrome */
export function PageHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-6 mb-6">
      <div className="min-w-0">
        <h1 className="display text-[24px] leading-tight">{title}</h1>
        {subtitle && <p className="muted mt-1.5 max-w-3xl text-[13.5px] leading-relaxed">{subtitle}</p>}
      </div>
      {action && <div className="flex gap-2 shrink-0 no-print">{action}</div>}
    </div>
  )
}

export function Table({ head, children, className }: { head: ReactNode[]; children: ReactNode; className?: string }) {
  return (
    <div className={clsx('scroll-x -mx-5 px-5', className)}>
      <table className="w-full text-[13.5px] border-collapse">
        <thead><tr>{head.map((h, i) => <th key={i} className="text-left eyebrow font-medium px-3 py-2.5 border-b line whitespace-nowrap first:pl-0 last:pr-0">{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}
export const Td = ({ children, className }: { children?: ReactNode; className?: string }) => <td className={clsx('px-3 py-3 border-b line align-top leading-relaxed first:pl-0 last:pr-0', className)}>{children}</td>
