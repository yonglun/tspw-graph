import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthContext, type AuthValue } from '../../app/AuthContext'
import { AdminPage } from './AdminPage'

const currentAdmin = {
  id: 'admin-1',
  username: 'admin',
  is_enabled: true,
  must_change_password: false,
  created_at: '2026-07-14T00:00:00Z',
  updated_at: '2026-07-14T00:00:00Z',
}

const auth: AuthValue = {
  status: 'ready',
  admin: currentAdmin,
  mustChangePassword: false,
  login: vi.fn(),
  logout: vi.fn(),
  changePassword: vi.fn(),
  refreshSession: vi.fn(),
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('AdminPage', () => {
  it('shows why the current administrator cannot be disabled', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const body = String(input).startsWith('/api/admins')
          ? [currentAdmin]
          : { items: [] }
        return new Response(JSON.stringify(body), {
          headers: { 'Content-Type': 'application/json' },
        })
      }),
    )

    render(
      <AuthContext.Provider value={auth}>
        <AdminPage />
      </AuthContext.Provider>,
    )

    const disable = await screen.findByRole('button', { name: '停用 admin' })
    expect(disable).toBeDisabled()
    expect(disable).toHaveAttribute('title', '不能停用当前登录账号')
    await waitFor(() => expect(screen.getByText(/更新于/)).toBeVisible())
  })
})
