import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { AlertTriangle, Gauge, Info, PenLine, ScanEye } from 'lucide-react'
import { api, type OversightQuality, type ReviewerQuality } from '../lib/api'
import { Badge, Card, PageHeader, Select, Spinner, Stat, Table, Td } from '../components/ui'
import { pct, when } from '../lib/format'

/** Everyone measures the model. This measures the person approving it.
 *  An approval granted in two seconds on a four-hundred-word change is a signature, not oversight —
 *  and because Tacit counts approvals as evidence for promotion, that distinction has teeth. */
export function OversightQualityPage() {
  const [days, setDays] = useState(90)
  const q = useQuery({ queryKey: ['oversight-quality', days], queryFn: () => api.get<OversightQuality>(`/oversight-quality?days=${days}`) })
  if (!q.data) return <Spinner />
  const r = q.data
  const stamped = r.recent.filter(d => d.attention === 'rubber-stamped').length
  const approved = r.recent.filter(d => d.status === 'approved').length

  return (
    <>
      <PageHeader title="Oversight quality" subtitle="Article 14 does not ask for oversight. It asks for oversight that is effective — so this page grades the reviewer, not the AI."
        action={<Select value={days} onChange={e => setDays(+e.target.value)}>{[30, 90, 365].map(d => <option key={d} value={d}>last {d} days</option>)}</Select>} />

      {r.decisions === 0 ? (
        <Card title="No decisions yet"><p className="muted text-[14px] max-w-2xl">Once people start approving and refusing work in the Inbox, this page measures how much attention each decision actually got, and whether the queue is turning into a signature line.</p></Card>
      ) : (
        <>
          <div className="grid lg:grid-cols-[minmax(0,320px)_1fr] gap-3.5 mb-5">
            <Dial score={r.index} band={r.band} decisions={r.decisions} days={r.period_days} capped={r.findings.some(f => f.severity === 'high')} />
            <Card title="What the number is made of" subtitle="Every part is shown with its weight, so you can argue with it.">
              <div className="flex flex-col gap-3">
                {r.components.map(c => (
                  <div key={c.name}>
                    <div className="flex items-baseline justify-between gap-3 mb-1">
                      <div className="text-[13.5px] font-medium">{c.name} <span className="muted font-normal">· {Math.round(c.weight * 100)}% of the score</span></div>
                      <div className="tnum text-[13.5px] font-semibold" style={{ color: bandColour(c.score) }}>{c.score}</div>
                    </div>
                    <div className="h-1.5 rounded-full bg-[var(--surface-2)] overflow-hidden">
                      <div className="h-full rounded-full transition-[width] duration-700" style={{ width: `${c.score}%`, background: bandColour(c.score) }} />
                    </div>
                    <div className="muted text-[12px] mt-1">{c.what}</div>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3.5 mb-5">
            <Stat label="Decisions examined" value={r.decisions} hint={`${r.reviewers.length} ${r.reviewers.length === 1 ? 'person' : 'people'} deciding`} />
            <Stat label="Signed, not read" value={stamped} hint={approved ? `${pct(stamped / approved)} of recent approvals` : 'no approvals yet'} tone={stamped ? 'bad' : 'ok'} />
            <Stat label="Waiting now" value={r.pending} hint={r.pending ? `oldest ${r.pending_oldest_hours}h` : 'queue clear'} tone={r.pending_oldest_hours > 24 ? 'warn' : undefined} />
            <Stat label="Refused" value={r.reviewers.reduce((n, v) => n + v.refused, 0)} hint="a gate that never says no proves nothing" tone="accent" />
          </div>

          {r.findings.length > 0 && (
            <Card className="mb-5" title={`What is wrong (${r.findings.length})`} subtitle="Named, attributed, and with the thing to do about it.">
              <div className="flex flex-col gap-2.5">
                {r.findings.map((f, i) => (
                  <div key={i} className={`rounded-xl border-l-4 surface-2 p-3.5 ${f.severity === 'high' ? 'border-l-bad' : f.severity === 'medium' ? 'border-l-warn' : 'border-l-[var(--line-strong)]'}`}>
                    <div className="flex items-center gap-2 mb-1">
                      <AlertTriangle size={14} className={f.severity === 'high' ? 'text-bad' : 'text-warn'} />
                      <div className="font-semibold text-[14px]">{f.title}</div>
                      <Badge tone={f.severity === 'high' ? 'bad' : f.severity === 'medium' ? 'warn' : 'neutral'}>{f.severity}</Badge>
                    </div>
                    <p className="ink2 text-[13.5px] leading-relaxed">{f.detail}</p>
                    <p className="text-[13px] mt-1.5 flex items-start gap-1.5"><PenLine size={13} className="mt-[3px] shrink-0 text-accent" /><span className="ink2"><span className="font-medium">Do this:</span> {f.do}</span></p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card className="mb-5" title="Reviewers" subtitle="Not a performance review. A control that rests on one tired person is a control with a single point of failure.">
            <Table head={['Reviewer', 'Decisions', 'Refusal rate', 'Median time', 'Signed unread', 'Reversed after', 'Calibration', 'Attention over time']}>
              {r.reviewers.map(v => <ReviewerRow key={v.reviewer} v={v} />)}
            </Table>
          </Card>

          <Card title="Recent decisions" subtitle="Time taken against the least time in which the preview could have been read." flush>
            <Table head={['When', 'Action', 'Decision', 'Took', 'Needed', 'Attention', 'Confidence']} className="px-4">
              {r.recent.slice(0, 40).map(d => (
                <tr key={d.id}>
                  <Td className="muted whitespace-nowrap">{when(d.decided_at)}</Td>
                  <Td className="mono text-[12.5px]">{d.tool}{d.escalated && <Badge className="ml-1.5" tone="warn">escalated</Badge>}</Td>
                  <Td>{d.status === 'approved' ? <Badge tone="ok">approved</Badge> : <Badge tone="bad">refused</Badge>}</Td>
                  <Td className="tnum">{d.seconds}s</Td>
                  <Td className="tnum muted">{d.needed_seconds}s</Td>
                  <Td>{d.attention === 'rubber-stamped' ? <span className="text-bad text-[13px] font-medium">signed, not read</span> : <span className="muted text-[13px]">considered</span>}</Td>
                  <Td className="tnum muted">{d.confidence === null ? '—' : pct(d.confidence)}</Td>
                </tr>
              ))}
            </Table>
          </Card>

          <p className="muted text-[12.5px] mt-4 flex items-start gap-1.5 max-w-3xl"><Info size={13} className="mt-[3px] shrink-0" />{r.method}</p>
        </>
      )}
    </>
  )
}

function ReviewerRow({ v }: { v: ReviewerQuality }) {
  const trend = v.fatigue_slope_seconds_per_day
  return (
    <tr>
      <Td className="font-medium whitespace-nowrap">{v.reviewer}</Td>
      <Td className="tnum">{v.decisions}<span className="muted"> ({v.approved}✓ {v.refused}✗)</span></Td>
      <Td className="tnum"><span style={{ color: v.refusal_rate === 0 ? 'var(--color-warn)' : undefined }}>{pct(v.refusal_rate)}</span></Td>
      <Td className="tnum">{v.median_seconds}s<span className="muted"> · p90 {v.p90_seconds}s</span></Td>
      <Td className="tnum"><span style={{ color: v.rubber_stamp_rate >= 0.2 ? 'var(--color-bad)' : undefined }}>{v.rubber_stamped} ({pct(v.rubber_stamp_rate)})</span></Td>
      <Td className="tnum">{v.reversed_after_approval}{v.miss_rate !== null && <span className="muted"> ({pct(v.miss_rate)})</span>}</Td>
      <Td className="tnum">{v.calibration === null ? <span className="muted">—</span> : <span style={{ color: v.calibration < 0 ? 'var(--color-bad)' : undefined }} title="how much more often confident actions are approved than shaky ones. Negative is backwards.">{v.calibration > 0 ? '+' : ''}{v.calibration}</span>}</Td>
      <Td className="tnum">
        {v.early_seconds && v.late_seconds !== null
          ? <span title="typical time per decision in the first third of the period, then the last third" style={{ color: v.late_seconds < v.early_seconds * 0.5 ? 'var(--color-bad)' : undefined }}>{v.early_seconds}s → {v.late_seconds}s</span>
          : <span className="muted">{trend === 0 ? '—' : `${trend > 0 ? '+' : ''}${trend}s/day`}</span>}
      </Td>
    </tr>
  )
}

function Dial({ score, band, decisions, days, capped }: { score: number; band: string; decisions: number; days: number; capped: boolean }) {
  const R = 54, C = 2 * Math.PI * R
  const colour = BAND[band]?.colour ?? 'var(--color-warn)'
  return (
    <Card>
      <div className="flex flex-col items-center text-center py-1">
        <div className="relative w-[136px] h-[136px]">
          <svg viewBox="0 0 136 136" className="w-full h-full -rotate-90">
            <circle cx="68" cy="68" r={R} fill="none" stroke="var(--surface-2)" strokeWidth="11" />
            <circle cx="68" cy="68" r={R} fill="none" stroke={colour} strokeWidth="11" strokeLinecap="round"
              strokeDasharray={C} strokeDashoffset={C * (1 - score / 100)} style={{ transition: 'stroke-dashoffset 1.1s cubic-bezier(.16,1,.3,1)' }} />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <div className="tnum text-[38px] font-semibold leading-none tracking-tight">{score}</div>
            <div className="muted text-[11px] uppercase tracking-wide mt-1">out of 100</div>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-1.5 font-semibold text-[15px] capitalize"><Gauge size={15} style={{ color: colour }} />{band}</div>
        <p className="muted text-[12.5px] mt-1 max-w-[260px]">{BAND[band]?.help}</p>
        {capped && score >= 60 && <p className="text-[12px] mt-2 max-w-[260px] text-warn">Held below its weighted score of {score} while a high-severity finding about the oversight itself is unresolved.</p>}
        <div className="muted text-[11.5px] mt-3 flex items-center gap-1.5"><ScanEye size={12} />{decisions} decisions over {days} days</div>
      </div>
    </Card>
  )
}

/** The words the backend uses, so the export and the console cannot disagree. */
const BAND: Record<string, { colour: string; help: string }> = {
  effective: { colour: 'var(--color-ok)', help: 'Decisions are getting real attention, and the record would survive someone asking.' },
  thin: { colour: 'var(--color-accent)', help: 'Oversight is happening, but parts of it would not stand up to a question.' },
  nominal: { colour: 'var(--color-warn)', help: 'The button is being pressed. Whether anyone is reading is another matter.' },
  decorative: { colour: 'var(--color-bad)', help: 'This is a signature line, not a control. These approvals are not counting towards autonomy.' },
}
const bandColour = (s: number) => (s >= 80 ? 'var(--color-ok)' : s >= 60 ? 'var(--color-accent)' : s >= 40 ? 'var(--color-warn)' : 'var(--color-bad)')
