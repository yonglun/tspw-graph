import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError, apiFetch, setApiAuthHooks } from '../api/client'

export type AuthStatus = 'loading' | 'anonymous' | 'password-change-required' | 'ready'
export type AdminSummary = { id: string; username: string; is_enabled: boolean; must_change_password: boolean; created_at: string; updated_at: string }
type SessionPayload = { admin: AdminSummary; must_change_password: boolean; csrf_token: string }
export type AuthValue = {
  status: AuthStatus
  admin?: AdminSummary
  mustChangePassword: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
  refreshSession: () => Promise<void>
}

export const AuthContext = createContext<AuthValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [admin, setAdmin] = useState<AdminSummary>()
  const csrf = useRef<string | undefined>(undefined)
  const channel = useRef<BroadcastChannel | undefined>(undefined)

  const applySession = useCallback((session: SessionPayload) => {
    csrf.current = session.csrf_token
    setAdmin(session.admin)
    setStatus(session.must_change_password ? 'password-change-required' : 'ready')
  }, [])
  const becomeAnonymous = useCallback(() => {
    csrf.current = undefined
    setAdmin(undefined)
    setStatus('anonymous')
  }, [])
  const refreshSession = useCallback(async () => {
    try { applySession(await apiFetch<SessionPayload>('/api/auth/session')) }
    catch (error) { if (error instanceof ApiError && error.status === 401) becomeAnonymous(); else throw error }
  }, [applySession, becomeAnonymous])

  useEffect(() => {
    setApiAuthHooks({
      getCsrfToken: () => csrf.current,
      onAuthenticationRequired: becomeAnonymous,
      onPasswordChangeRequired: () => setStatus('password-change-required'),
    })
    if ('BroadcastChannel' in window) {
      channel.current = new BroadcastChannel('tspw-auth')
      channel.current.onmessage = () => { void refreshSession() }
    }
    void refreshSession()
    return () => { channel.current?.close(); setApiAuthHooks({}) }
  }, [becomeAnonymous, refreshSession])

  const login = useCallback(async (username: string, password: string) => {
    applySession(await apiFetch<SessionPayload>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }))
    channel.current?.postMessage('login')
  }, [applySession])
  const logout = useCallback(async () => {
    await apiFetch('/api/auth/logout', { method: 'POST' })
    becomeAnonymous()
    channel.current?.postMessage('logout')
  }, [becomeAnonymous])
  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    applySession(await apiFetch<SessionPayload>('/api/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }))
    channel.current?.postMessage('password-changed')
  }, [applySession])

  const value = useMemo(() => ({ status, admin, mustChangePassword: status === 'password-change-required', login, logout, changePassword, refreshSession }), [status, admin, login, logout, changePassword, refreshSession])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
