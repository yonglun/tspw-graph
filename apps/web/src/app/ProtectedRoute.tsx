import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from './AuthContext'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const auth = useAuth()
  const location = useLocation()
  if (auth.status === 'loading') return <div className="auth-loading" role="status">正在验证管理员会话…</div>
  if (auth.status === 'anonymous') return <Navigate to={`/login?returnTo=${encodeURIComponent(location.pathname + location.search)}`} replace />
  if (auth.status === 'password-change-required') return <Navigate to="/change-password" replace />
  return children
}
