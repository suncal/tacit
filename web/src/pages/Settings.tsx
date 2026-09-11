import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { api, type Budget, type Integration, type Policy, type Tool } from '../lib/api'
import { Badge, Button, Card, Input, PageHeader, RiskPill, Select, Spinner, Table, Td, useToast } from '../components/ui'

export function SettingsPage() {
  const qc = useQueryClient(); const toast = useToast()
  const integ = useQuery({ queryKey: ['integrations'], queryFn: () => api.get<{ integrations: Integration[]; brain: { provider: string; model: string; llm: boolean } }>('/integrations') })
  const pol = useQuery({ queryKey: ['policies'], queryFn: () => api.get<{ policies: Policy[]; defaults: Record<string, string> }>('/policies') })
  const bud = useQuery({ queryKey: ['budgets'], queryFn: () => api.get<{ budgets: Budget[] }>('/budgets') })
  const tools = useQuery({ queryKey: ['tools'], queryFn: () => api.get<{ tools: Tool[] }>('/tools') })
  const keys = useQuery({ queryKey: ['keys'], queryFn: () => api.get<{ keys: { id: string; name: string; prefix: string; created_at: number; last_used_at: number | null }[] }>('/auth/keys') })
  const [p, setP] = useState({ principal: '', tool: '', decision: 'ask', note: '' })
  const [b, setB] = useState({ scope: '', max_writes_per_hour: 20, max_usd_per_day: 5 })
  const [kname, setKname] = useState(''); const [newKey, setNewKey] = useState<string | null>(null)
  const addP = useMutation({ mutationFn: () => api.post('/policies', { principal: p.principal || '*', tool: p.tool || '*', decision: p.decision, note: p.note }), onSuccess: () => { setP({ principal: '', tool: '', decision: 'ask', note: '' }); qc.invalidateQueries({ queryKey: ['policies'] }) }, onError: (e: Error) => toast(e.message, 'bad') })
  const delP = useMutation({ mutationFn: (id: string) => api.del(`/policies/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['policies'] }) })
  const addB = useMutation({ mutationFn: () => api.post('/budgets', b), onSuccess: () => { setB({ scope: '', max_writes_per_hour: 20, max_usd_per_day: 5 }); qc.invalidateQueries({ queryKey: ['budgets'] }) }, onError: (e: Error) => toast(e.message, 'bad') })
  const delB = useMutation({ mutationFn: (id: string) => api.del(`/budgets/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['budgets'] }) })
  const addK = useMutation({ mutationFn: () => api.post<{ key: string }>('/auth/keys', { name: kname }), onSuccess: r => { setNewKey(r.key); setKname(''); qc.invalidateQueries({ queryKey: ['keys'] }) } })
  const delK = useMutation({ mutationFn: (id: string) => api.del(`/auth/keys/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['keys'] }) })
  if (!integ.data || !pol.data || !bud.data || !tools.data) return <Spinner />
  return (
    <>
      <PageHeader title="Settings" subtitle="Integrations, the brain, permissions, budgets and API keys. Secrets live in the environment, never in the database." />
      <div className="grid grid-cols-2 gap-4 mb-4">
        <Card title="Integrations" subtitle="Polling needs no public URL. Webhooks are there when you want push.">
          <div className="flex flex-col divide-y divide-[var(--line)]">{integ.data.integrations.map(i => <div key={i.key} className="flex items-center justify-between py-2.5 gap-3"><div className="min-w-0"><div className="font-medium">{i.name} <span className="muted font-normal text-[12px]">· {i.mode}</span></div><div className="muted text-[12.5px] truncate">{i.connected ? i.detail : i.how}</div></div><Badge tone={i.connected ? 'ok' : 'neutral'}>{i.connected ? 'connected' : 'not set'}</Badge></div>)}</div>
        </Card>
        <Card title="Brain" subtitle="Which model thinks. The harness — permissions, shadow, audit, undo — is identical for all of them.">
          <div className="flex items-center gap-2 mb-2"><span className="font-semibold">{integ.data.brain.provider}</span>{integ.data.brain.llm ? <Badge tone="ok">LLM</Badge> : <Badge tone="warn">no model</Badge>}<span className="mono muted">{integ.data.brain.model}</span></div>
          <table className="text-[12.5px] w-full"><tbody>
            <tr><td className="mono py-1 pr-3">anthropic</td><td className="muted">TACIT_ANTHROPIC_API_KEY · official SDK · claude-opus-5 · native tool use</td></tr>
            <tr><td className="mono py-1 pr-3">claude-cli</td><td className="muted">TACIT_BRAIN_PROVIDER=claude-cli · uses your existing Claude subscription</td></tr>
            <tr><td className="mono py-1 pr-3">openai-compatible</td><td className="muted">TACIT_BRAIN_BASE_URL · any /chat/completions endpoint</td></tr>
            <tr><td className="mono py-1 pr-3">local</td><td className="muted">no model: drafts from your own past replies, deterministic planner</td></tr>
          </tbody></table>
        </Card>
      </div>
      <Card className="mb-4" title="Permission policies" subtitle={<>First matching rule wins. Otherwise the risk-class default applies: {Object.entries(pol.data.defaults).map(([k, v]) => <span key={k} className="mr-2"><Badge>{k}</Badge>→<Badge tone={v === 'allow' ? 'ok' : v === 'ask' ? 'warn' : 'bad'}>{v}</Badge></span>)}</>}>
        <form className="grid grid-cols-[1fr_1fr_120px_1fr_auto] gap-2 mb-3" onSubmit={e => { e.preventDefault(); addP.mutate() }}><Input placeholder="principal pattern (playbook:*, slack:U123, automation:*)" value={p.principal} onChange={e => setP({ ...p, principal: e.target.value })} /><Input placeholder="tool pattern (github_*, shell_run)" value={p.tool} onChange={e => setP({ ...p, tool: e.target.value })} /><Select value={p.decision} onChange={e => setP({ ...p, decision: e.target.value })}><option>allow</option><option>ask</option><option>deny</option></Select><Input placeholder="note" value={p.note} onChange={e => setP({ ...p, note: e.target.value })} /><Button variant="primary" type="submit">Add rule</Button></form>
        <Table head={['Principal', 'Tool', 'Decision', 'Note', '']}>{pol.data.policies.map(r => <tr key={r.id}><Td className="mono">{r.principal}</Td><Td className="mono">{r.tool}</Td><Td><Badge tone={r.decision === 'allow' ? 'ok' : r.decision === 'ask' ? 'warn' : 'bad'}>{r.decision}</Badge></Td><Td className="muted">{r.note}</Td><Td><button className="muted hover:text-bad" onClick={() => delP.mutate(r.id)}><Trash2 size={14} /></button></Td></tr>)}</Table>
      </Card>
      <Card className="mb-4" title="Budgets" subtitle="Hard caps no model can talk its way past. Scope matches principals.">
        <form className="grid grid-cols-[1fr_160px_160px_auto] gap-2 mb-3" onSubmit={e => { e.preventDefault(); addB.mutate() }}><Input placeholder="scope (playbook:*, automation:*)" value={b.scope} onChange={e => setB({ ...b, scope: e.target.value })} /><Input type="number" placeholder="writes / hour" value={b.max_writes_per_hour} onChange={e => setB({ ...b, max_writes_per_hour: +e.target.value })} /><Input type="number" step="0.5" placeholder="$ / day" value={b.max_usd_per_day} onChange={e => setB({ ...b, max_usd_per_day: +e.target.value })} /><Button variant="primary" type="submit">Add budget</Button></form>
        <Table head={['Scope', 'Writes / hour', '$ / day', 'Note', '']}>{bud.data.budgets.map(r => <tr key={r.id}><Td className="mono">{r.scope}</Td><Td className="tnum">{r.max_writes_per_hour}</Td><Td className="tnum">${r.max_usd_per_day.toFixed(2)}</Td><Td className="muted">{r.note}</Td><Td><button className="muted hover:text-bad" onClick={() => delB.mutate(r.id)}><Trash2 size={14} /></button></Td></tr>)}</Table>
      </Card>
      <Card className="mb-4" title="API keys" subtitle="For feeding events from your own systems (POST /api/v1/events) and for CI. Shown once.">
        <form className="flex gap-2 mb-3" onSubmit={e => { e.preventDefault(); if (kname) addK.mutate() }}><Input placeholder="key name (e.g. ci, data-pipeline)" value={kname} onChange={e => setKname(e.target.value)} className="max-w-sm" /><Button variant="primary" type="submit">Create key</Button></form>
        {newKey && <div className="rounded-lg bg-accent-soft p-3 mb-3 text-[13px]">New key (copy it now, it won't be shown again): <code className="mono select-all">{newKey}</code></div>}
        <Table head={['Name', 'Prefix', 'Created', 'Last used', '']}>{(keys.data?.keys || []).map(k => <tr key={k.id}><Td>{k.name}</Td><Td className="mono">{k.prefix}…</Td><Td className="muted">{new Date(k.created_at * 1000).toLocaleDateString()}</Td><Td className="muted">{k.last_used_at ? new Date(k.last_used_at * 1000).toLocaleString() : 'never'}</Td><Td><button className="muted hover:text-bad" onClick={() => delK.mutate(k.id)}><Trash2 size={14} /></button></Td></tr>)}</Table>
      </Card>
      <Card title={`Tools (${tools.data.tools.length})`} subtitle="Everything the brain can call. Writes carry an undo recipe; exec never does.">
        <Table head={['Risk', 'Tool', 'What it does', 'System', 'Reversible']}>{tools.data.tools.map(t => <tr key={t.name}><Td><RiskPill risk={t.risk} /></Td><Td className="mono font-medium">{t.name}</Td><Td className="muted">{t.description}</Td><Td className="muted">{t.system}</Td><Td>{t.risk === 'exec' ? <Badge tone="bad">no</Badge> : <Badge tone="ok">yes</Badge>}</Td></tr>)}</Table>
      </Card>
    </>
  )
}
