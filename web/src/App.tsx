import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { api, ApiError, type User } from './lib/api'
import { Layout } from './components/Layout'
import { Spinner, ToastProvider } from './components/ui'
import { AuthPage } from './pages/Auth'
import { OverviewPage } from './pages/Overview'
import { PlaybooksPage } from './pages/Playbooks'
import { PlaybookDetailPage } from './pages/PlaybookDetail'
import { ShadowPage } from './pages/Shadow'
import { PeoplePage } from './pages/People'
import { InboxPage } from './pages/Inbox'
import { RunDetailPage, RunsPage } from './pages/Runs'
import { ChatPage } from './pages/Chat'
import { AutomationsPage, MeetingsPage, MemoryPage, TasksPage } from './pages/Work'
import { AuditPage } from './pages/Audit'
import { SettingsPage } from './pages/Settings'

const qc = new QueryClient({ defaultOptions: { queries: { retry: (n, e) => !(e instanceof ApiError && e.status === 401) && n < 2, staleTime: 3000 } } })

function Gate() {
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.get<User>('/auth/me'), retry: false })
  if (me.isLoading) return <Spinner />
  if (!me.data || me.data.id === 'setup') return <AuthPage onDone={() => { qc.invalidateQueries(); me.refetch() }} />
  return (
    <Routes>
      <Route element={<Layout user={me.data} />}>
        <Route index element={<OverviewPage />} />
        <Route path="playbooks" element={<PlaybooksPage />} />
        <Route path="playbooks/:id" element={<PlaybookDetailPage />} />
        <Route path="shadow" element={<ShadowPage />} />
        <Route path="people" element={<PeoplePage />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:id" element={<RunDetailPage />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="memory" element={<MemoryPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="automations" element={<AutomationsPage />} />
        <Route path="meetings" element={<MeetingsPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return <QueryClientProvider client={qc}><ToastProvider><BrowserRouter><Gate /></BrowserRouter></ToastProvider></QueryClientProvider>
}
