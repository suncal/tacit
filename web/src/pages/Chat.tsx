import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Send } from 'lucide-react'
import { clsx } from 'clsx'
import { api, type Run } from '../lib/api'
import { Badge, Button, Input, PageHeader } from '../components/ui'

type Msg = { who: 'you' | 'tacit'; text: string; run?: Run }
const CHIPS = ['what do we know about invoices?', 'remember that the Neon password rotates quarterly', 'create task: draft the Starter migration email for @priya', 'list open tasks', 'daily 09:00: post a digest of open tasks', 'run: git status', 'what did you do recently?']

export function ChatPage() {
  const qc = useQueryClient()
  const [msgs, setMsgs] = useState<Msg[]>([{ who: 'tacit', text: "Hi — I'm @tacit. Ask me about the company, hand me a task, or tell me something worth remembering. Anything that writes to your tools waits for your approval." }])
  const [text, setText] = useState('')
  const end = useRef<HTMLDivElement>(null)
  const send = useMutation({
    mutationFn: (t: string) => api.post<{ run: Run }>('/chat', { text: t }),
    onSuccess: ({ run }) => { setMsgs(m => [...m, { who: 'tacit', text: run.output || (run.status === 'waiting' ? 'That needs an approval — it’s in the Inbox.' : ''), run }]); qc.invalidateQueries({ queryKey: ['overview'] }) },
    onError: (e: Error) => setMsgs(m => [...m, { who: 'tacit', text: `Error: ${e.message}` }]),
  })
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])
  const go = (t: string) => { if (!t.trim()) return; setMsgs(m => [...m, { who: 'you', text: t }]); setText(''); send.mutate(t) }
  return (
    <div className="flex flex-col h-[calc(100vh-48px)]">
      <PageHeader title="Chat" subtitle="Talk to @tacit directly. Every tool call shows in the trace." />
      <div className="surface flex-1 min-h-0 flex flex-col">
        <div className="flex-1 overflow-auto p-5 flex flex-col gap-4">
          {msgs.map((m, i) => (
            <div key={i} className={clsx('max-w-[78%]', m.who === 'you' ? 'self-end' : 'self-start')}>
              <div className={clsx('rounded-2xl px-4 py-2.5 text-[14px] whitespace-pre-wrap leading-relaxed', m.who === 'you' ? 'bg-accent text-white' : 'surface-2')}>{m.text}</div>
              {m.run && m.run.steps.filter(s => s.type !== 'say').length > 0 && (
                <div className="mt-1.5 flex flex-col gap-1 px-1">
                  {m.run.steps.filter(s => s.type !== 'say').map((s, j) => (
                    <div key={j} className="text-[12px] mono flex items-center gap-1.5 muted">
                      <span className={clsx('w-1.5 h-1.5 rounded-full', s.type === 'approval' ? 'bg-stage-propose' : s.ok ? 'bg-ok' : 'bg-bad')} />
                      {s.type === 'approval' ? <>{s.name} → waiting for approval · <Link to="/inbox" className="text-accent">Inbox</Link></> : s.type === 'error' ? s.text : <>{s.name}({JSON.stringify(s.args).slice(0, 80)}) {s.ok ? '✓' : `✗ ${s.text}`}</>}
                    </div>
                  ))}
                  <Link to={`/runs/${m.run.id}`} className="text-[12px] text-accent">run {m.run.id.slice(0, 12)}… {m.run.actions.length > 0 && <Badge tone="ok">{m.run.actions.length} reversible</Badge>}</Link>
                </div>
              )}
            </div>
          ))}
          <div ref={end} />
        </div>
        <div className="border-t line p-3">
          <div className="flex flex-wrap gap-1.5 mb-2">{CHIPS.map(c => <button key={c} onClick={() => setText(c)} className="text-[12px] rounded-full border line px-2.5 py-1 ink-2 hover:border-accent hover:text-accent">{c}</button>)}</div>
          <form className="flex gap-2" onSubmit={e => { e.preventDefault(); go(text) }}><Input value={text} onChange={e => setText(e.target.value)} placeholder="Ask @tacit…" autoFocus /><Button variant="primary" type="submit" loading={send.isPending}><Send size={14} />Send</Button></form>
        </div>
      </div>
    </div>
  )
}
