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
