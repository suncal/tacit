import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { Plane, ShieldAlert, Undo2 } from 'lucide-react'
import { api, type Person } from '../lib/api'
import { Avatar, Badge, Button, Empty, Input, Modal, PageHeader, Spinner, StagePill, TrustBar, useToast } from '../components/ui'
import { pct, when } from '../lib/format'

export function PeoplePage() {
  const qc = useQueryClient(); const toast = useToast()
  const q = useQuery({ queryKey: ['people'], queryFn: () => api.get<{ people: Person[]; cover_min_trust: number }>('/people'), refetchInterval: 15000 })
  const [covering, setCovering] = useState<Person | null>(null)
  const [backup, setBackup] = useState(''); const [days, setDays] = useState(7)
  const cover = useMutation({ mutationFn: (actor: string) => api.post<{ promoted: unknown[] }>(`/people/${actor}/cover`, { backup, days }), onSuccess: r => { toast(`${r.promoted.length} job(s) promoted to Propose while they're out`, 'ok'); setCovering(null); qc.invalidateQueries() }, onError: (e: Error) => toast(e.message, 'bad') })
  const uncover = useMutation({ mutationFn: (actor: string) => api.del(`/people/${actor}/cover`), onSuccess: () => { toast('Cover ended — jobs restored', 'ok'); qc.invalidateQueries() } })
  if (!q.data) return <Spinner />
  const ppl = q.data.people
  return (
    <>
      <PageHeader title="People" subtitle="Whose head each job lives in — and what Tacit can cover when they're out. Bus factor, made visible." />
      {ppl.length === 0 ? <Empty title="No jobs mined yet" /> : (
        <div className="grid grid-cols-2 gap-4">
          {ppl.map(p => (
            <div key={p.actor} className="surface p-5">
              <div className="flex items-center gap-3 mb-3">
                <Avatar name={p.actor} size={34} />
                <div className="min-w-0 flex-1"><div className="font-semibold text-[15px]">{p.actor}</div><div className="muted text-[12.5px]">{p.jobs} recurring job{p.jobs === 1 ? '' : 's'} · ~{Math.round(p.weekly_minutes)} min/week · {p.events} observed actions</div></div>
                {p.cover ? <Button size="sm" variant="secondary" onClick={() => uncover.mutate(p.actor)}><Undo2 size={13} />End cover</Button> : <Button size="sm" variant="primary" disabled={!p.coverable} title={p.coverable ? '' : 'No job has enough trust to cover yet'} onClick={() => { setCovering(p); setBackup('') }}><Plane size={13} />Cover while out</Button>}
              </div>
              {p.cover && <div className="rounded-lg bg-accent-soft text-accent text-[12.5px] px-3 py-2 mb-3">Covered until {when(p.cover.until)}{p.cover.backup ? ` · approvals go to ${p.cover.backup}` : ''}</div>}
              {p.bus_factor_risk > 0 && <div className="flex items-center gap-1.5 text-[12.5px] text-warn mb-3"><ShieldAlert size={14} />{p.bus_factor_risk} job{p.bus_factor_risk === 1 ? '' : 's'} only {p.actor} can do today</div>}
              <div className="flex flex-col divide-y divide-[var(--line)]">
                {p.playbooks.map(pb => (
                  <div key={pb.id} className="grid grid-cols-[1fr_92px_150px] items-center gap-3 py-2">
                    <Link to={`/playbooks/${pb.id}`} className="min-w-0 hover:text-accent"><div className="truncate text-[13.5px] font-medium">{pb.name}</div><div className="muted text-[12px]">{pb.evidence}× · ~{pb.minutes_each} min each</div></Link>
                    <StagePill stage={pb.stage} />
                    <TrustBar value={pb.trust} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      <Modal open={!!covering} onClose={() => setCovering(null)} title={`Cover for ${covering?.actor}`}>
        {covering && (
          <div className="flex flex-col gap-3 text-[13.5px]">
            <p className="ink2">While {covering.actor} is out, their jobs with trust ≥ {pct(q.data.cover_min_trust)} move from Shadow to <b>Propose</b>: Tacit drafts the reply and someone approves it. Everything moves back when the cover ends.</p>
            <div className="flex gap-2"><Input placeholder="who approves in the meantime (optional)" value={backup} onChange={e => setBackup(e.target.value)} /><Input type="number" min={1} max={90} value={days} onChange={e => setDays(+e.target.value)} className="w-24" /><span className="self-center muted">days</span></div>
            <div className="rounded-lg surface-2 p-3">{covering.playbooks.filter(pb => pb.stage === 'auto' || pb.trust >= q.data.cover_min_trust).map(pb => <div key={pb.id} className="flex items-center justify-between py-1"><span>{pb.name}</span><Badge tone={pb.stage === 'auto' ? 'accent' : 'warn'}>{pb.stage === 'auto' ? 'stays auto' : `${pb.stage} → propose`}</Badge></div>)}</div>
            <div className="flex gap-2 justify-end"><Button variant="ghost" onClick={() => setCovering(null)}>Cancel</Button><Button variant="primary" loading={cover.isPending} onClick={() => cover.mutate(covering.actor)}>Start cover</Button></div>
          </div>
        )}
      </Modal>
    </>
  )
}
