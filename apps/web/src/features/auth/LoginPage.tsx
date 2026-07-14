import { type FormEvent, useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'

import { useAuth } from '../../app/AuthContext'

export function LoginPage() {
  const auth = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  if (auth.status === 'ready') return <Navigate to="/admin" replace />
  if (auth.status === 'password-change-required') return <Navigate to="/change-password" replace />
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('')
    try {
      await auth.login(username, password)
      const requested = params.get('returnTo')
      navigate(requested?.startsWith('/') && !requested.startsWith('//') ? requested : '/admin', { replace: true })
    } catch { setError('用户名或密码错误，请重试。') }
  }
  return <AuthShell eyebrow="ADMIN ACCESS · 08" title="管理员登录" description="登录后可管理构建、审核与管理员账户。"><form className="auth-form" onSubmit={submit}><label>用户名<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required /></label><label>密码<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="primary" type="submit">登录</button></form></AuthShell>
}

export function AuthShell({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children: React.ReactNode }) {
  return <section className="auth-page"><div className="auth-card"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p>{children}</div></section>
}
