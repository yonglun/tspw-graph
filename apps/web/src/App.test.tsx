import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.pushState({}, '', '/')
})

describe('App', () => {
  it('hides protected navigation when there is no administrator session', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path === '/api/auth/session') {
          return new Response(JSON.stringify({ detail: { code: 'AUTH_REQUIRED' } }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        return new Response(JSON.stringify([]), { headers: { 'Content-Type': 'application/json' } })
      }),
    )

    render(<App />)

    await waitFor(() => expect(screen.getByRole('link', { name: '管理员登录' })).toBeVisible())
    expect(screen.queryByRole('link', { name: '构建' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '审核' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '管理员' })).not.toBeInTheDocument()
  })

  it('shows protected navigation for a ready administrator session', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path === '/api/auth/session') {
          return new Response(
            JSON.stringify({
              admin: {
                id: 'admin-1',
                username: 'admin',
                is_enabled: true,
                must_change_password: false,
                created_at: '',
                updated_at: '',
              },
              must_change_password: false,
              csrf_token: 'csrf-token',
            }),
            { headers: { 'Content-Type': 'application/json' } },
          )
        }
        return new Response(JSON.stringify([]), { headers: { 'Content-Type': 'application/json' } })
      }),
    )

    render(<App />)

    await waitFor(() => expect(screen.getByRole('link', { name: '管理员' })).toBeVisible())
    expect(screen.getByRole('link', { name: '构建' })).toBeVisible()
    expect(screen.getByRole('link', { name: '审核' })).toBeVisible()
    expect(screen.getByText('admin')).toBeVisible()
  })

  it('renders the monochrome product header with primary navigation', () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([]))))
    render(<App />)

    const header = screen.getByRole('banner')
    expect(header).toHaveClass('site-header')
    expect(screen.getByRole('link', { name: '江湖图谱' })).toHaveClass('brand')
    expect(screen.getByRole('navigation', { name: '主导航' })).toBeVisible()
    expect(screen.getByLabelText('当前项目')).toBeVisible()
  })

  it('shows the product brand and page heading', () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([]))))
    render(<App />)
    expect(screen.getByRole('link', { name: /江湖.*图谱/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /看懂《笑傲江湖》.*也看懂知识图谱/ })).toBeInTheDocument()
  })

  it('keeps the selected project when switching pages from the top navigation', async () => {
    window.history.pushState({}, '', '/graph?project=project-16')
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify([
            {
              id: 'project-16',
              title: '笑傲江湖16',
              is_builtin: false,
              created_at: '',
              updated_at: '',
            },
          ]),
        ),
      ),
    )
    const user = userEvent.setup()

    render(<App />)
    await waitFor(() => expect(screen.getByLabelText('当前项目')).toHaveValue('project-16'))
    await user.click(screen.getByRole('link', { name: '问答' }))

    expect(window.location.pathname).toBe('/ask')
    expect(window.location.search).toBe('?project=project-16')
    expect(screen.getByLabelText('当前项目')).toHaveValue('project-16')
  })
})
