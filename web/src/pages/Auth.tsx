import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type User } from '../lib/api'
import { Button, Input, Label } from '../components/ui'
import { Mark } from '../components/Brand'

export function AuthPage({ onDone }: { onDone: (u: User) => void }) {
  const status = useQuery({ queryKey: ['auth-status'], queryFn: () => api.get<{ needs_setup: boolean }>('/auth/status') })
  const [f, setF] = useState({ email: '', name: '', password: '' })
  const setup = status.data?.needs_setup
  const m = useMutation({ mutationFn: () => api.post<User>(setup ? '/auth/setup' : '/auth/login', setup ? f : { email: f.email, password: f.password }), onSuccess: onDone })
  return (
    <div className="min-h-full grid place-items-center p-6">
      <div className="w-full max-w-[380px]">
        <div className="flex flex-col items-center text-center mb-7">
          <Mark size={40} className="text-accent" />
          <div className="display text-[22px] mt-3">Tacit</div>
          <div className="muted text-[13px] mt-1">The verified work layer</div>
        </div>
        <form className="surface raised p-6 flex flex-col gap-3.5 shadow-[var(--shadow)]" onSubmit={e => { e.preventDefault(); m.mutate() }}>
          <h2 className="font-semibold text-[15px] tracking-[-0.015em]">{setup ? 'Create the first admin' : 'Sign in'}</h2>
          {setup && <p className="muted text-[13px]">No users exist yet. This account becomes the admin. Nothing leaves this machine.</p>}
          <div><Label>Email</Label><Input type="email" required value={f.email} onChange={e => setF({ ...f, email: e.target.value })} autoFocus /></div>
          {setup && <div><Label>Name</Label><Input required value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></div>}
          <div><Label>Password</Label><Input type="password" required minLength={setup ? 8 : 1} value={f.password} onChange={e => setF({ ...f, password: e.target.value })} /></div>
          {m.error && <div className="text-bad text-[13px]">{(m.error as Error).message}</div>}
          <Button variant="primary" type="submit" loading={m.isPending} className="mt-1 h-10">{setup ? 'Create admin' : 'Sign in'}</Button>
          {!setup && <p className="muted text-[12px] text-center pt-1">Demo install? <span className="mono">demo@northwind.dev</span> · <span className="mono">tacit-demo</span></p>}
        </form>
      </div>
    </div>
  )
}
