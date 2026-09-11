import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Play, Trash2 } from 'lucide-react'
import { api, type Automation, type Meeting, type Memory, type Run, type Task } from '../lib/api'
import { Badge, Button, Card, Empty, Input, PageHeader, Spinner, Table, Td, Textarea, useToast } from '../components/ui'
import { ago, when } from '../lib/format'

// ---------------------------------------------------------------- memory
export function MemoryPage() {
  const qc = useQueryClient()
  const [q, setQ] = useState('')
  const [add, setAdd] = useState('')
  const list = useQuery({ queryKey: ['memories', q], queryFn: () => api.get<{ memories: Memory[] }>(`/memories${q ? `?q=${encodeURIComponent(q)}` : ''}`) })
  const create = useMutation({ mutationFn: () => api.post('/memories', { text: add }), onSuccess: () => { setAdd(''); qc.invalidateQueries({ queryKey: ['memories'] }) } })
  const del = useMutation({ mutationFn: (id: string) => api.del(`/memories/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['memories'] }) })
  return (
    <>
      <PageHeader title="Memory" subtitle="What the team knows. Facts, decisions and preferences — in a database you own and can export in one click." />
      <div className="grid grid-cols-2 gap-3 mb-4"><Input placeholder="Search memory…" value={q} onChange={e => setQ(e.target.value)} /><form className="flex gap-2" onSubmit={e => { e.preventDefault(); if (add.trim()) create.mutate() }}><Input placeholder="Add a fact, decision or preference" value={add} onChange={e => setAdd(e.target.value)} /><Button variant="primary" type="submit" loading={create.isPending}>Remember</Button></form></div>
      {!list.data ? <Spinner /> : list.data.memories.length === 0 ? <Empty title="Nothing here yet" /> : (
        <Card><Table head={['Memory', 'Tags', 'Source', 'When', '']}>{list.data.memories.map(m => <tr key={m.id}><Td>{m.text}</Td><Td>{m.tags.map(t => <Badge key={t} className="mr-1">{t}</Badge>)}</Td><Td className="mono muted">{m.source}</Td><Td className="muted whitespace-nowrap">{ago(m.created_at)}</Td><Td><button className="muted hover:text-bad" onClick={() => del.mutate(m.id)}><Trash2 size={14} /></button></Td></tr>)}</Table></Card>
      )}
    </>
  )
}

// ---------------------------------------------------------------- tasks
export function TasksPage() {
  const qc = useQueryClient()
  const [title, setTitle] = useState(''); const [who, setWho] = useState(''); const [due, setDue] = useState('')
  const list = useQuery({ queryKey: ['tasks'], queryFn: () => api.get<{ tasks: Task[] }>('/tasks') })
  const create = useMutation({ mutationFn: () => api.post('/tasks', { title, assignee: who, due }), onSuccess: () => { setTitle(''); setWho(''); setDue(''); qc.invalidateQueries({ queryKey: ['tasks'] }) } })
  const set = useMutation({ mutationFn: ({ id, s }: { id: string; s: string }) => api.post(`/tasks/${id}/status?status=${s}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['tasks'] }) })
  const open = (list.data?.tasks || []).filter(t => t.status === 'open'), done = (list.data?.tasks || []).filter(t => t.status !== 'open')
  const row = (t: Task) => <tr key={t.id}><Td className="w-10">{t.status === 'open' ? <button className="w-6 h-6 rounded-md border line hover:border-ok hover:text-ok inline-flex items-center justify-center" onClick={() => set.mutate({ id: t.id, s: 'done' })}><Check size={13} /></button> : <Badge>{t.status}</Badge>}</Td><Td>{t.title}<div className="muted text-[12px]">{t.detail}</div></Td><Td>{t.assignee || '—'}</Td><Td>{t.due || '—'}</Td><Td className="mono muted">{t.source}</Td></tr>
  return (
    <>
      <PageHeader title="Tasks" />
      <form className="grid grid-cols-[2fr_1fr_1fr_auto] gap-2 mb-4" onSubmit={e => { e.preventDefault(); if (title.trim()) create.mutate() }}><Input placeholder="New task" value={title} onChange={e => setTitle(e.target.value)} /><Input placeholder="Owner" value={who} onChange={e => setWho(e.target.value)} /><Input placeholder="Due" value={due} onChange={e => setDue(e.target.value)} /><Button variant="primary" type="submit">Add</Button></form>
      {!list.data ? <Spinner /> : <><Card><Table head={['', 'Task', 'Owner', 'Due', 'Source']}>{open.length ? open.map(row) : <tr><Td className="muted">no open tasks</Td></tr>}</Table></Card>{done.length > 0 && <Card className="mt-4" title="Done"><Table head={['', 'Task', 'Owner', 'Due', 'Source']}>{done.map(row)}</Table></Card>}</>}
    </>
  )
}

// ---------------------------------------------------------------- automations
export function AutomationsPage() {
  const qc = useQueryClient(); const toast = useToast()
  const [name, setName] = useState(''); const [sched, setSched] = useState(''); const [prompt, setPrompt] = useState('')
  const list = useQuery({ queryKey: ['automations'], queryFn: () => api.get<{ automations: Automation[] }>('/automations'), refetchInterval: 10000 })
  const create = useMutation({ mutationFn: () => api.post('/automations', { name, schedule: sched, prompt }), onSuccess: () => { setName(''); setSched(''); setPrompt(''); toast('Automation created', 'ok'); qc.invalidateQueries({ queryKey: ['automations'] }) }, onError: (e: Error) => toast(e.message, 'bad') })
  const act = useMutation({ mutationFn: ({ id, a }: { id: string; a: string }) => api.post<{ run?: Run }>(`/automations/${id}/${a}`), onSuccess: (r, v) => { if (v.a === 'run') toast(`Ran: ${r.run?.status}`, 'ok'); qc.invalidateQueries() } })
  return (
    <>
      <PageHeader title="Automations" subtitle="Describe a job once. Tacit runs it on a schedule or on an event — under the same permissions, budgets and audit as everything else." />
      <Card className="mb-4"><form onSubmit={e => { e.preventDefault(); create.mutate() }} className="flex flex-col gap-2"><div className="grid grid-cols-[1fr_2fr_auto] gap-2"><Input placeholder="name" value={name} onChange={e => setName(e.target.value)} /><Input placeholder="every 30m · daily 09:00 · weekly mon 09:00 · on github.pr.opened · on webhook:deploy" value={sched} onChange={e => setSched(e.target.value)} /><Button variant="primary" type="submit" loading={create.isPending}>Create</Button></div><Textarea placeholder="What should Tacit do each time?" value={prompt} onChange={e => setPrompt(e.target.value)} /></form></Card>
      {!list.data ? <Spinner /> : list.data.automations.length === 0 ? <Empty title="No automations yet" /> : (
        <div className="flex flex-col gap-3">{list.data.automations.map(a => (
          <div key={a.id} className="surface p-4 flex items-start gap-4">
            <div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="font-semibold">{a.name}</span><Badge tone="accent">{a.trigger.human}</Badge>{!a.enabled && <Badge tone="bad">paused</Badge>}</div><div className="ink-2 mt-1">{a.prompt}</div><div className="muted text-[12px] mono mt-1">last: {a.last_run_at ? `${ago(a.last_run_at)} (${a.last_status})` : 'never'} · next: {a.next_run_at ? when(a.next_run_at) : 'on event'}</div></div>
            <div className="flex gap-1.5"><Button size="sm" onClick={() => act.mutate({ id: a.id, a: 'run' })}><Play size={13} />Run now</Button><Button size="sm" variant="ghost" onClick={() => act.mutate({ id: a.id, a: 'toggle' })}>{a.enabled ? 'Pause' : 'Resume'}</Button><Button size="sm" variant="ghost" onClick={() => act.mutate({ id: a.id, a: 'delete' })}><Trash2 size={13} /></Button></div>
          </div>))}</div>
      )}
    </>
  )
}

// ---------------------------------------------------------------- meetings
export function MeetingsPage() {
  const qc = useQueryClient(); const toast = useToast()
  const [title, setTitle] = useState(''); const [text, setText] = useState('')
  const list = useQuery({ queryKey: ['meetings'], queryFn: () => api.get<{ meetings: Meeting[] }>('/meetings') })
  const create = useMutation({ mutationFn: () => api.post('/meetings', { title: title || 'Meeting', transcript: text }), onSuccess: () => { setTitle(''); setText(''); qc.invalidateQueries({ queryKey: ['meetings'] }) }, onError: (e: Error) => toast(e.message, 'bad') })
  const accept = useMutation({ mutationFn: ({ id, index }: { id: string; index: number }) => api.post<{ created: string[] }>(`/meetings/${id}/accept`, { index }), onSuccess: r => { toast(`${r.created.length} task(s) created`, 'ok'); qc.invalidateQueries() } })
  return (
    <>
      <PageHeader title="Meetings" subtitle="Paste a transcript. Tacit writes the notes and pulls out action items you accept with one tap. Transcripts stay on this machine unless you connect a cloud model." />
      <Card className="mb-4"><form onSubmit={e => { e.preventDefault(); if (text.trim()) create.mutate() }} className="flex flex-col gap-2"><Input placeholder="Meeting title" value={title} onChange={e => setTitle(e.target.value)} /><Textarea placeholder={"Speaker: what they said\nSpeaker: …"} value={text} onChange={e => setText(e.target.value)} className="min-h-32" /><div><Button variant="primary" type="submit" loading={create.isPending}>Make notes</Button></div></form></Card>
      {!list.data ? <Spinner /> : list.data.meetings.length === 0 ? <Empty title="No meetings yet" /> : list.data.meetings.map(m => {
        const pending = m.action_items.filter(i => !i.accepted).length
        return (
          <Card key={m.id} className="mb-4" title={m.title} subtitle={ago(m.created_at)} action={pending > 0 && <Button size="sm" variant="primary" onClick={() => accept.mutate({ id: m.id, index: -1 })}>Accept all ({pending})</Button>}>
            <div className="text-[13.5px] whitespace-pre-wrap rounded-lg surface-2 p-3 mb-3 leading-relaxed">{m.notes}</div>
            <Table head={['Action item', 'Owner', 'Due', '']}>{m.action_items.map((i, ix) => <tr key={ix}><Td>{i.title}</Td><Td>{i.owner || '—'}</Td><Td>{i.due || '—'}</Td><Td className="text-right">{i.accepted ? <Badge tone="ok">task <Link to="/tasks" className="underline">{i.task_id?.slice(0, 10)}</Link></Badge> : <Button size="sm" onClick={() => accept.mutate({ id: m.id, index: ix })}>Accept</Button>}</Td></tr>)}</Table>
          </Card>
        )
      })}
    </>
  )
}
