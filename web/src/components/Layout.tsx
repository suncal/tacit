import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Activity, BookOpen, Brain, ClipboardList, Eye, Inbox, LayoutDashboard, ListChecks, LogOut, MessageSquare, Moon, PlayCircle, Settings, Sun, Timer, UserRound, Users } from 'lucide-react'
import { clsx } from 'clsx'
import { useEffect, useState } from 'react'
import { api, type Overview, type User } from '../lib/api'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/playbooks', label: 'Playbooks', icon: BookOpen },
  { to: '/shadow', label: 'Shadow', icon: Eye },
  { to: '/people', label: 'People', icon: UserRound },
  { to: '/inbox', label: 'Inbox', icon: Inbox, badge: 'approvals' },
  { to: '/runs', label: 'Runs', icon: PlayCircle },
  { to: '/chat', label: 'Chat', icon: MessageSquare },
  { divider: true },
  { to: '/memory', label: 'Memory', icon: Brain },
  { to: '/tasks', label: 'Tasks', icon: ListChecks },
  { to: '/automations', label: 'Automations', icon: Timer },
  { to: '/meetings', label: 'Meetings', icon: Users },
  { divider: true },
  { to: '/audit', label: 'Audit log', icon: Activity },
  { to: '/settings', label: 'Settings', icon: Settings },
] as const

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
  return (
    <div className="grid grid-cols-[232px_1fr] min-h-full">
      <aside className="sticky top-0 h-screen flex flex-col border-r line bg-[var(--surface)] px-3 py-4">
        <div className="flex items-center gap-2.5 px-2 pb-4">
          <img src="/favicon.svg" width={26} height={26} alt="" />
          <div className="leading-tight"><div className="font-semibold text-[15px]">Tacit</div><div className="muted text-[11.5px]">{ov.data?.org || '…'}</div></div>
        </div>
        <nav className="flex flex-col gap-0.5">
          {NAV.map((n, i) => 'divider' in n ? <div key={i} className="h-px my-2 bg-[var(--line)]" /> : (
            <NavLink key={n.to} to={n.to} end={'end' in n && n.end} className={({ isActive }) => clsx('flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13.5px] font-medium', isActive ? 'bg-accent-soft text-accent' : 'ink-2 hover:bg-[var(--surface-2)]')}>
              <n.icon size={16} strokeWidth={1.9} /><span>{n.label}</span>
              {'badge' in n && counts && counts[n.badge] > 0 && <span className="ml-auto rounded-full bg-gold text-white text-[11px] font-semibold px-1.5 leading-5 min-w-5 text-center tnum">{counts[n.badge]}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto pt-3 border-t line text-[12px] muted">
          {ov.data && <div className="flex items-center gap-1.5 mb-2"><ClipboardList size={13} /><span className="mono">{ov.data.brain.llm ? ov.data.brain.model : 'local brain — no LLM'}</span></div>}
          <div className="flex items-center justify-between">
            <span className="truncate" title={user.email}>{user.name}</span>
            <div className="flex items-center gap-1">
              <button className="p-1 rounded hover:bg-[var(--surface-2)]" title="Theme" onClick={() => setTheme(theme === 'dark' ? 'light' : theme === 'light' ? 'system' : 'dark')}>{theme === 'dark' ? <Moon size={14} /> : <Sun size={14} />}</button>
              <button className="p-1 rounded hover:bg-[var(--surface-2)]" title="Sign out" onClick={async () => { await api.post('/auth/logout'); nav('/login'); location.reload() }}><LogOut size={14} /></button>
            </div>
          </div>
        </div>
      </aside>
      <main className="min-w-0 px-8 py-6 max-w-[1320px] w-full"><Outlet /></main>
    </div>
  )
}
