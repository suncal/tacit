import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type User } from '../lib/api'
import { Button, Input, Label } from '../components/ui'

export function AuthPage({ onDone }: { onDone: (u: User) => void }) {
  const status = useQuery({ queryKey: ['auth-status'], queryFn: () => api.get<{ needs_setup: boolean }>('/auth/status') })
  const [f, setF] = useState({ email: '', name: '', password: '' })
  const setup = status.data?.needs_setup
  const m = useMutation({ mutationFn: () => api.post<User>(setup ? '/auth/setup' : '/auth/login', setup ? f : { email: f.email, password: f.password }), onSuccess: onDone })
  return (
    <div className="min-h-full grid place-items-center p-6">
      <div className="w-full max-w-sm">
        <div className="flex items-center gap-2.5 mb-6"><img src="/favicon.svg" width={30} height={30} alt="" /><div><div className="font-semibold text-lg leading-tight">Tacit</div><div className="muted text-[12.5px]">The AI teammate that earns its job.</div></div></div>
        <form className="surface p-5 flex flex-col gap-3" onSubmit={e => { e.preventDefault(); m.mutate() }}>
          <h2 className="font-semibold text-[16px]">{setup ? 'Create the first admin' : 'Sign in'}</h2>
          {setup && <p className="muted text-[13px]">No users exist yet. This account becomes the admin. Nothing leaves this machine.</p>}
          <div><Label>Email</Label><Input type="email" required value={f.email} onChange={e => setF({ ...f, email: e.target.value })} autoFocus /></div>
          {setup && <div><Label>Name</Label><Input required value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>}
          <div><Label>Password</Label><Input type="password" required minLength={setup ? 8 : 1} value={f.password} onChange={e => setF({ ...f, password: e.target.value })} /></div>
          {m.error && <div className="text-bad text-[13px]">{(m.error as Error).message}</div>}
          <Button variant="primary" type="submit" loading={m.isPending}>{setup ? 'Create admin' : 'Sign in'}</Button>
          {!setup && <p className="muted text-[12px]">Demo install? <span className="mono">demo@northwind.dev</span> / <span className="mono">tacit-demo</span></p>}
        </form>
      </div>
    </div>
  )
}
