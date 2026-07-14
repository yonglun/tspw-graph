import { type FormEvent, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'

import { useAuth } from '../../app/AuthContext'
import { AuthShell } from './LoginPage'

export function ChangePasswordPage() {
  const auth = useAuth(); const navigate = useNavigate()
  const [current, setCurrent] = useState(''); const [next, setNext] = useState(''); const [confirm, setConfirm] = useState(''); const [error, setError] = useState('')
  if (auth.status === 'anonymous') return <Navigate to="/login" replace />
  async function submit(event: FormEvent) { event.preventDefault(); setError(''); if (next !== confirm) { setError('两次输入的新密码不一致。'); return } try { await auth.changePassword(current, next); navigate('/admin', { replace: true }) } catch { setError('密码修改失败，请检查当前密码和复杂度要求。') } }
  return <AuthShell eyebrow="SECURITY · 09" title="修改密码" description="密码至少 10 位，并包含大写字母、小写字母、数字和特殊字符。"><form className="auth-form" onSubmit={submit}><label>当前密码<input type="password" value={current} onChange={e => setCurrent(e.target.value)} required /></label><label>新密码<input type="password" value={next} onChange={e => setNext(e.target.value)} required /></label><label>确认新密码<input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} required /></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="primary" type="submit">保存新密码</button></form></AuthShell>
}
