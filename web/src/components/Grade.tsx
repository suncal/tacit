import { Sparkles, Ruler } from 'lucide-react'
import { clsx } from 'clsx'

/** A score is only useful if you can see why. When a model graded it, say so — and say what it decided on. */
export function Why({ why, gradedBy, similarity, className }: { why?: string; gradedBy?: string; similarity?: number; className?: string }) {
  if (!why && gradedBy !== 'model') return null
  const model = gradedBy === 'model'
  return (
    <div className={clsx('flex items-start gap-1.5 text-[12px] leading-snug', model ? 'text-[var(--ink-2)]' : 'muted', className)}>
      {model ? <Sparkles size={12} className="mt-[2px] shrink-0 text-accent" /> : <Ruler size={12} className="mt-[2px] shrink-0" />}
      <span>
        {why}
        {model && similarity !== undefined && <span className="muted"> · word overlap said {Math.round(similarity * 100)}</span>}
      </span>
    </div>
  )
}
