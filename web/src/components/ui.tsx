import { clsx } from 'clsx'
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { Loader2, X } from 'lucide-react'
import { STAGE_LABEL } from '../lib/format'
import type { Stage } from '../lib/api'

// ---------------------------------------------------------------- buttons
type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'; size?: 'sm' | 'md'; loading?: boolean }
export function Button({ variant = 'secondary', size = 'md', loading, className, children, disabled, ...rest }: BtnProps) {
  const base = 'inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap'
  const sizes = size === 'sm' ? 'h-8 px-3 text-[13px]' : 'h-9 px-3.5 text-sm'
  const variants = {
    primary: 'bg-accent text-white hover:bg-accent-strong',
    secondary: 'bg-[var(--surface)] border border-[var(--line-strong)] hover:bg-[var(--surface-2)]',
    ghost: 'hover:bg-[var(--surface-2)]',
    danger: 'bg-bad text-white hover:opacity-90',
    success: 'bg-ok text-white hover:opacity-90',
  }[variant]
  return <button className={clsx(base, sizes, variants, className)} disabled={disabled || loading} {...rest}>{loading && <Loader2 size={14} className="animate-spin" />}{children}</button>
}

// ---------------------------------------------------------------- surfaces
export function Card({ className, children, title, action, subtitle }: { className?: string; children: ReactNode; title?: ReactNode; action?: ReactNode; subtitle?: ReactNode }) {
  return (
    <section className={clsx('surface', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4 pb-2">
          <div><h3 className="text-[15px] font-semibold leading-6">{title}</h3>{subtitle && <p className="muted text-[13px] mt-0.5">{subtitle}</p>}</div>
          {action}
        </header>
      )}
      <div className={clsx(title ? 'px-5 pb-5' : 'p-5')}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'accent' | 'ok' | 'warn' | 'bad' }) {
  const color = tone === 'accent' ? 'text-accent' : tone === 'ok' ? 'text-ok' : tone === 'warn' ? 'text-warn' : tone === 'bad' ? 'text-bad' : ''
  return (
    <div className="surface px-5 py-4">
      <div className="muted text-[12px] font-medium uppercase tracking-wide">{label}</div>
      <div className={clsx('tnum text-[28px] font-semibold leading-tight mt-1', color)}>{value}</div>
      {hint && <div className="muted text-[12.5px] mt-1">{hint}</div>}
    </div>
  )
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return <div className="text-center py-12 px-6 border border-dashed rounded-xl line"><div className="font-medium">{title}</div>{hint && <div className="muted text-[13px] mt-1 max-w-md mx-auto">{hint}</div>}{action && <div className="mt-4">{action}</div>}</div>
}

// ---------------------------------------------------------------- badges
export function Badge({ children, tone = 'neutral', className }: { children: ReactNode; tone?: 'neutral' | 'ok' | 'warn' | 'bad' | 'accent' | 'violet'; className?: string }) {
  const t = {
    neutral: 'bg-[var(--surface-2)] ink-2', ok: 'bg-[rgba(31,138,76,.12)] text-ok', warn: 'bg-[rgba(183,121,31,.14)] text-warn',
    bad: 'bg-[rgba(192,57,43,.12)] text-bad', accent: 'bg-accent-soft text-accent', violet: 'bg-[rgba(124,92,191,.14)] text-stage-shadow',
  }[tone]
  return <span className={clsx('inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11.5px] font-semibold tracking-wide', t, className)}>{children}</span>
}

export const STAGE_TONE: Record<Stage, 'neutral' | 'violet' | 'warn' | 'accent' | 'neutral'> = { candidate: 'neutral', shadow: 'violet', propose: 'warn', auto: 'accent', retired: 'neutral' }
export function StagePill({ stage, className }: { stage: Stage; className?: string }) {
  return <Badge tone={STAGE_TONE[stage]} className={className}><span className={clsx('w-1.5 h-1.5 rounded-full', { 'bg-stage-candidate': stage === 'candidate', 'bg-stage-shadow': stage === 'shadow', 'bg-stage-propose': stage === 'propose', 'bg-stage-auto': stage === 'auto', 'bg-stage-retired': stage === 'retired' })} />{STAGE_LABEL[stage]}</Badge>
}

export function RiskPill({ risk }: { risk: 'read' | 'write' | 'exec' }) {
  return <Badge tone={risk === 'read' ? 'ok' : risk === 'write' ? 'warn' : 'bad'}>{risk}</Badge>
}

export function Avatar({ name, size = 22 }: { name: string; size?: number }) {
  const hue = [...name].reduce((a, c) => a + c.charCodeAt(0), 0) % 360
  return <span className="inline-flex items-center justify-center rounded-full text-white font-semibold shrink-0" style={{ width: size, height: size, fontSize: size * 0.45, background: `hsl(${hue} 45% 45%)` }} title={name}>{name.slice(0, 1).toUpperCase()}</span>
}

// ---------------------------------------------------------------- trust
export function TrustBar({ value, scored, className }: { value: number; scored?: number; className?: string }) {
  const tone = value >= 0.6 ? 'bg-ok' : value >= 0.3 ? 'bg-warn' : 'bg-stage-candidate'
  return (
    <div className={clsx('flex items-center gap-2', className)}>
      <div className="h-1.5 flex-1 rounded-full bg-[var(--surface-2)] overflow-hidden"><div className={clsx('h-full rounded-full', tone)} style={{ width: `${Math.max(2, value * 100)}%` }} /></div>
      <span className="tnum text-[12.5px] font-semibold w-10 text-right">{(value * 100).toFixed(0)}%</span>
      {scored !== undefined && <span className="muted text-[11.5px] w-14">n={scored}</span>}
    </div>
  )
}

export function ScoreDot({ score, hit }: { score: number | null; hit?: boolean }) {
  if (score === null || score === undefined) return <span className="muted">—</span>
  return <span className={clsx('inline-flex items-center gap-1.5 tnum font-semibold text-[12.5px]', hit ? 'text-ok' : 'text-bad')}><span className={clsx('w-2 h-2 rounded-full', hit ? 'bg-ok' : 'bg-bad')} />{(score * 100).toFixed(0)}</span>
}

// ---------------------------------------------------------------- inputs
export const Input = (p: React.InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={clsx('h-9 w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-sm placeholder:text-[var(--muted)] focus:border-accent', p.className)} />
export const Textarea = (p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...p} className={clsx('w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm placeholder:text-[var(--muted)] focus:border-accent min-h-24', p.className)} />
export const Select = (p: React.SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={clsx('h-9 rounded-lg border border-[var(--line-strong)] bg-[var(--surface)] px-2.5 text-sm', p.className)} />
export const Label = ({ children }: { children: ReactNode }) => <label className="block text-[12.5px] font-medium ink-2 mb-1">{children}</label>

// ---------------------------------------------------------------- toast
type Toast = { id: number; text: string; tone?: 'ok' | 'bad' }
const ToastCtx = createContext<(text: string, tone?: 'ok' | 'bad') => void>(() => {})
export const useToast = () => useContext(ToastCtx)
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((text: string, tone?: 'ok' | 'bad') => {
    const id = Date.now() + Math.random()
    setItems(i => [...i, { id, text, tone }])
    setTimeout(() => setItems(i => i.filter(t => t.id !== id)), 3200)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2">
        {items.map(t => <div key={t.id} className={clsx('surface px-4 py-2.5 text-sm shadow-[var(--shadow)]', t.tone === 'bad' && 'border-bad text-bad', t.tone === 'ok' && 'border-ok')}>{t.text}</div>)}
      </div>
    </ToastCtx.Provider>
  )
}

// ---------------------------------------------------------------- modal
export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose(); if (open) window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 bg-black/40 flex items-start justify-center p-6 overflow-auto" onClick={onClose}>
      <div className={clsx('surface w-full shadow-[var(--shadow)] mt-6', wide ? 'max-w-4xl' : 'max-w-xl')} onClick={e => e.stopPropagation()} role="dialog" aria-modal>
        <header className="flex items-center justify-between px-5 py-3 border-b line"><h3 className="font-semibold">{title}</h3><button onClick={onClose} className="muted hover:ink-2" aria-label="Close"><X size={16} /></button></header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export const Spinner = () => <div className="flex justify-center py-10"><Loader2 className="animate-spin muted" /></div>

export function Kbd({ children }: { children: ReactNode }) { return <kbd className="mono rounded border line px-1 py-0.5 text-[11px] bg-[var(--surface-2)]">{children}</kbd> }

export function PageHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return <div className="flex items-end justify-between gap-4 mb-5"><div><h1 className="text-[22px] font-semibold leading-tight">{title}</h1>{subtitle && <p className="muted mt-1 max-w-2xl">{subtitle}</p>}</div>{action && <div className="flex gap-2 shrink-0">{action}</div>}</div>
}

export function Table({ head, children, className }: { head: ReactNode[]; children: ReactNode; className?: string }) {
  return (
    <div className={clsx('scroll-x', className)}>
      <table className="w-full text-[13.5px]">
        <thead><tr className="text-left muted text-[12px] uppercase tracking-wide">{head.map((h, i) => <th key={i} className="font-medium px-3 py-2 border-b line">{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}
export const Td = ({ children, className }: { children?: ReactNode; className?: string }) => <td className={clsx('px-3 py-2.5 border-b line align-top', className)}>{children}</td>
