import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, BookOpen, Bot, Brain, Eye, FileCheck2, Inbox, LayoutDashboard, ListChecks, LogOut, MessageSquare, Monitor, Moon, PanelLeft, PlayCircle, Receipt, ScanEye, Search, Settings, Sparkles, Sun, Timer, UserRound, Users } from 'lucide-react'
import { clsx } from 'clsx'
import { useEffect, useState } from 'react'
import { api, type Overview, type User } from '../lib/api'
import { Wordmark, Mark } from './Brand'
import { CommandPalette } from './CommandPalette'
import { useLive, SAY } from '../lib/live'
import { useToast, Kbd } from './ui'

type Item = { to: string; label: string; icon: typeof Inbox; end?: boolean; badge?: 'approvals' | 'drafts_pending' }
const GROUPS: { label: string; items: Item[] }[] = [
  { label: 'Command', items: [
    { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
    { to: '/report', label: 'What we found', icon: Sparkles },
    { to: '/inbox', label: 'Inbox', icon: Inbox, badge: 'approvals' },
  ] },
  { label: 'The work', items: [
    { to: '/playbooks', label: 'Playbooks', icon: BookOpen },
    { to: '/shadow', label: 'Shadow', icon: Eye },
    { to: '/people', label: 'People', icon: UserRound },
    { to: '/runs', label: 'Runs', icon: PlayCircle },
    { to: '/chat', label: 'Chat', icon: MessageSquare },
  ] },
  { label: 'Accountability', items: [
    { to: '/oversight', label: 'Oversight', icon: Bot },
    { to: '/oversight-quality', label: 'Oversight quality', icon: ScanEye },
    { to: '/ledger', label: 'Verified work', icon: Receipt },
    { to: '/compliance', label: 'Evidence', icon: FileCheck2 },
    { to: '/audit', label: 'Audit log', icon: Activity },
  ] },
  { label: 'Workspace', items: [
    { to: '/memory', label: 'Memory', icon: Brain },
    { to: '/tasks', label: 'Tasks', icon: ListChecks },
    { to: '/automations', label: 'Automations', icon: Timer },
    { to: '/meetings', label: 'Meetings', icon: Users },
    { to: '/settings', label: 'Settings', icon: Settings },
  ] },
]

function useTheme() {
  const [theme, setTheme] = useState<string>(() => { try { return localStorage.getItem('tacit.theme') || 'system' } catch { return 'system' } })
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', theme)
    try { localStorage.setItem('tacit.theme', theme) } catch { /* private mode */ }
  }, [theme])
  return [theme, setTheme] as const
}

export function Layout({ user }: { user: User }) {
  const nav = useNavigate()
  const [theme, setTheme] = useTheme()
  const toast = useToast()
  const [openNav, setOpenNav] = useState(false)
  // the stream carries the refetches, so polling drops to a slow safety net
  const { connected, feed } = useLive((text, kind) => toast(text, kind === 'run.error' || kind === 'agent.reworked' ? 'bad' : undefined))
  const ov = useQuery({ queryKey: ['overview'], queryFn: () => api.get<Overview>('/overview'), refetchInterval: connected ? 120000 : 15000 })
  const counts = ov.data?.counts
  const ThemeIcon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor
  const latest = feed[0]
  return (
    <div className="lg:grid lg:grid-cols-[236px_1fr] min-h-full">
      <CommandPalette />
      {ov.data?.demo && (
        <div className="lg:col-span-2 flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-[12.5px] border-b line bg-accent-soft text-accent no-print">
          <b className="font-semibold">Public demo</b>
          <span className="text-[var(--ink-2)]">Real product, seeded organisation. Shell, file and network tools are removed, no model is connected, and everything resets when the instance restarts.</span>
          <a className="underline underline-offset-2 ml-auto" href="https://github.com/suncal/tacit" target="_blank" rel="noopener">Run it yourself →</a>
        </div>
      )}
      <div className="lg:hidden sticky top-0 z-30 flex items-center gap-3 h-14 px-4 border-b line bg-[var(--surface)] no-print">
        <button className="p-1.5 -ml-1.5 rounded-md muted hover:bg-[var(--surface-2)]" onClick={() => setOpenNav(o => !o)} aria-label="Menu"><PanelLeft size={18} /></button>
        <Mark size={22} className="text-accent" /><span className="display text-[15px]">Tacit</span>
        {counts && counts.approvals > 0 && <span className="ml-auto tnum rounded-full bg-gold text-white text-[11px] font-semibold px-2 leading-5">{counts.approvals}</span>}
      </div>
      {openNav && <div className="lg:hidden fixed inset-0 z-30 bg-black/40" onClick={() => setOpenNav(false)} />}
      <aside className={clsx('flex flex-col border-r line bg-[var(--surface)] no-print',
        'lg:sticky lg:top-0 lg:h-screen lg:translate-x-0',
        'fixed inset-y-0 left-0 z-40 w-[236px] transition-transform lg:transition-none',
        openNav ? 'translate-x-0' : '-translate-x-full')} onClick={() => setOpenNav(false)}>
        <div className="px-4 pt-4 pb-3"><Wordmark sub={ov.data?.org} /></div>
        <button onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
          className="mx-2.5 mb-3 flex items-center gap-2 h-8 px-2.5 rounded-lg border line text-[12.5px] muted hover:border-[var(--line-strong)] hover:text-[var(--ink-2)] transition-colors">
          <Search size={13} /><span>Search</span><Kbd>⌘K</Kbd>
        </button>
        <nav className="flex-1 overflow-y-auto px-2.5 pb-3 flex flex-col gap-4">
          {GROUPS.map(g => (
            <div key={g.label}>
              <div className="eyebrow px-2.5 mb-1.5 opacity-70">{g.label}</div>
              <div className="flex flex-col gap-px">
                {g.items.map(n => (
                  <NavLink key={n.to} to={n.to} end={n.end}
                    className={({ isActive }) => clsx('group flex items-center gap-2.5 rounded-lg px-2.5 h-[30px] text-[13px] font-medium transition-colors',
                      isActive ? 'bg-accent-soft text-accent' : 'text-[var(--ink-2)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)]')}>
                    {({ isActive }) => (<>
                      <n.icon size={15} strokeWidth={isActive ? 2.2 : 1.9} className="shrink-0" />
                      <span className="truncate">{n.label}</span>
                      {n.badge && counts && counts[n.badge] > 0 && (
                        <span className="ml-auto tnum rounded-full bg-gold text-white text-[10.5px] font-semibold px-1.5 leading-[17px] min-w-[19px] text-center">{counts[n.badge]}</span>
                      )}
                    </>)}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="px-3 py-3 border-t line">
          <div className="px-1.5 mb-2.5 flex flex-col gap-1.5">
            {ov.data && (
              <div className="flex items-center gap-2 text-[11.5px] muted">
                <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', ov.data.brain.llm ? 'bg-ok' : 'bg-[var(--line-strong)]')} />
                <span className="mono truncate" title={ov.data.brain.llm ? ov.data.brain.model : 'deterministic local brain — no model connected'}>{ov.data.brain.llm ? ov.data.brain.model : 'local brain'}</span>
              </div>
            )}
            <div className="flex items-center gap-2 text-[11.5px] muted" title={connected ? 'streaming live from the server' : 'not streaming — falling back to polling'}>
              <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', connected ? 'bg-accent animate-pulse' : 'bg-[var(--line-strong)]')} />
              <span className="truncate">{latest ? (SAY[latest.kind]?.(latest) || latest.kind) : connected ? 'live' : 'offline'}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="min-w-0 flex-1"><div className="text-[12.5px] font-medium truncate">{user.name}</div><div className="muted text-[11px] truncate" title={user.email}>{user.email}</div></div>
            <button className="p-1.5 rounded-md muted hover:bg-[var(--surface-2)] hover:text-[var(--ink)]" title={`Theme: ${theme}`} onClick={() => setTheme(theme === 'dark' ? 'light' : theme === 'light' ? 'system' : 'dark')}><ThemeIcon size={14} /></button>
            <button className="p-1.5 rounded-md muted hover:bg-[var(--surface-2)] hover:text-[var(--ink)]" title="Sign out" onClick={async () => { await api.post('/auth/logout'); nav('/login'); location.reload() }}><LogOut size={14} /></button>
          </div>
        </div>
      </aside>
      <main className="min-w-0"><div className="px-5 py-6 lg:px-9 lg:py-7 max-w-[1380px] w-full"><Outlet /></div></main>
    </div>
  )
}
