import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, BookOpen, Bot, Brain, Eye, FileCheck2, Inbox, LayoutDashboard, ListChecks, LogOut, MessageSquare, Monitor, Moon, PlayCircle, Receipt, Settings, Sparkles, Sun, Timer, UserRound, Users } from 'lucide-react'
import { clsx } from 'clsx'
import { useEffect, useState } from 'react'
import { api, type Overview, type User } from '../lib/api'
import { Wordmark } from './Brand'

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
  const ov = useQuery({ queryKey: ['overview'], queryFn: () => api.get<Overview>('/overview'), refetchInterval: 15000 })
  const counts = ov.data?.counts
  const ThemeIcon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor
  return (
    <div className="grid grid-cols-[236px_1fr] min-h-full">
      <aside className="sticky top-0 h-screen flex flex-col border-r line bg-[var(--surface)] no-print">
        <div className="px-4 pt-4 pb-3"><Wordmark sub={ov.data?.org} /></div>
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
          {ov.data && (
            <div className="flex items-center gap-2 px-1.5 mb-2.5 text-[11.5px] muted">
              <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', ov.data.brain.llm ? 'bg-ok' : 'bg-[var(--line-strong)]')} />
              <span className="mono truncate" title={ov.data.brain.llm ? ov.data.brain.model : 'deterministic local brain — no model connected'}>{ov.data.brain.llm ? ov.data.brain.model : 'local brain'}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <div className="min-w-0 flex-1"><div className="text-[12.5px] font-medium truncate">{user.name}</div><div className="muted text-[11px] truncate" title={user.email}>{user.email}</div></div>
            <button className="p-1.5 rounded-md muted hover:bg-[var(--surface-2)] hover:text-[var(--ink)]" title={`Theme: ${theme}`} onClick={() => setTheme(theme === 'dark' ? 'light' : theme === 'light' ? 'system' : 'dark')}><ThemeIcon size={14} /></button>
            <button className="p-1.5 rounded-md muted hover:bg-[var(--surface-2)] hover:text-[var(--ink)]" title="Sign out" onClick={async () => { await api.post('/auth/logout'); nav('/login'); location.reload() }}><LogOut size={14} /></button>
          </div>
        </div>
      </aside>
      <main className="min-w-0"><div className="px-9 py-7 max-w-[1380px] w-full"><Outlet /></div></main>
    </div>
  )
}
