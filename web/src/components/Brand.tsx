/** The mark: a ghosted square — the draft nobody saw — behind the verified one. */
export function Mark({ size = 26, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect x="2.5" y="2.5" width="19" height="19" rx="5.5" fill="currentColor" opacity=".26" />
      <rect x="10" y="10" width="19.5" height="19.5" rx="5.5" fill="currentColor" />
      <path d="M15.2 20.1l2.9 2.9 6.2-7.2" fill="none" stroke="var(--surface)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function Wordmark({ size = 26, sub }: { size?: number; sub?: string }) {
  return (
    <div className="flex items-center gap-2.5 min-w-0">
      <Mark size={size} className="text-accent shrink-0" />
      <div className="leading-tight min-w-0">
        <div className="display text-[16px]">Tacit</div>
        {sub && <div className="muted text-[11.5px] truncate">{sub}</div>}
      </div>
    </div>
  )
}
