import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type AuditEvent } from '../lib/api'
import { Badge, Card, Input, PageHeader, Spinner, Table, Td } from '../components/ui'
import { when } from '../lib/format'

export function AuditPage() {
  const [actor, setActor] = useState(''); const [action, setAction] = useState('')
  const q = useQuery({ queryKey: ['audit', actor, action], queryFn: () => api.get<{ events: AuditEvent[] }>(`/audit?limit=300${actor ? `&actor=${encodeURIComponent(actor)}` : ''}${action ? `&action=${encodeURIComponent(action)}` : ''}`), refetchInterval: 10000 })
  return (
    <>
      <PageHeader title="Audit log" subtitle="Everything Tacit did, and who asked. Append-only. Export it, ship it to your SIEM, or read the table directly." action={<a className="text-accent text-[13px] font-medium self-center" href="/api/v1/audit/export">Export JSONL ↓</a>} />
      <div className="grid grid-cols-2 gap-2 mb-4"><Input placeholder="filter by actor (e.g. playbook:, slack:, user:)" value={actor} onChange={e => setActor(e.target.value)} /><Input placeholder="filter by action prefix (tool., run., approval., draft., playbook.)" value={action} onChange={e => setAction(e.target.value)} /></div>
      {!q.data ? <Spinner /> : (
        <Card><Table head={['When', 'Actor', 'Action', 'Target', 'Detail']}>{q.data.events.map(e => <tr key={e.id}><Td className="muted whitespace-nowrap">{when(e.ts)}</Td><Td className="mono">{e.actor}</Td><Td><Badge tone={e.ok ? 'neutral' : 'bad'}>{e.action}</Badge></Td><Td className="mono">{e.target}</Td><Td className="mono muted max-w-md break-all">{JSON.stringify(e.detail).slice(0, 220)}</Td></tr>)}</Table></Card>
      )}
    </>
  )
}
