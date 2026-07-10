import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ProjectProvider } from '../../app/ProjectContext'
import { BuildPage } from './BuildPage'

class FakeEventSource { addEventListener() {} close() {} set onerror(_: unknown) {} }

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('uploads a novel and shows the persistent job stage', async () => {
  vi.stubGlobal('EventSource', FakeEventSource)
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url.includes('model-profiles')) return new Response(JSON.stringify([{ id: 'fixed:test', provider: 'fixed', base_url: '', model: 'test', timeout_seconds: 10, available: true }]))
    if (url.endsWith('/api/projects')) return new Response(JSON.stringify([]))
    return new Response(JSON.stringify({ project: { id: 'project-1', title: '测试小说', is_builtin: false, created_at: '', updated_at: '' }, job: { id: 'job-1', project_id: 'project-1', model_profile_id: 'fixed:test', status: 'QUEUED', completed_chunks: 0, total_chunks: 0 } }), { status: 201 })
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<MemoryRouter><ProjectProvider><BuildPage /></ProjectProvider></MemoryRouter>)
  await user.type(screen.getByLabelText('项目标题'), '测试小说')
  await user.upload(screen.getByLabelText('TXT 小说'), new File(['第一章'], 'book.txt', { type: 'text/plain' }))
  await waitFor(() => expect(screen.getByLabelText('模型配置')).toHaveValue('fixed:test'))
  await user.click(screen.getByRole('button', { name: '开始构建' }))
  await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/projects/upload'))).toBe(true))
  expect(await screen.findByText('等待 Worker')).toBeVisible()
})

it('restores a build job from URL state after refresh', async () => {
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url.includes('/api/jobs/job-1') && !url.includes('/quality')) return new Response(JSON.stringify({ id: 'job-1', project_id: 'project-1', model_profile_id: 'fixed:test', status: 'QUEUED', completed_chunks: 0, total_chunks: 0 }))
    if (url.includes('/api/projects/project-1')) return new Response(JSON.stringify({ id: 'project-1', title: '测试小说', is_builtin: false, created_at: '', updated_at: '' }))
    if (url.includes('model-profiles')) return new Response(JSON.stringify([]))
    return new Response(JSON.stringify([]))
  }))
  render(<MemoryRouter initialEntries={['/build?project=project-1&job=job-1']}><ProjectProvider><BuildPage /></ProjectProvider></MemoryRouter>)
  expect(await screen.findByText('等待 Worker')).toBeVisible()
  await waitFor(() => expect(fetch).toHaveBeenCalled())
})

it('creates an attribute backfill job for the current existing project', async () => {
  vi.stubGlobal('EventSource', FakeEventSource)
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('model-profiles')) return new Response(JSON.stringify([{ id: 'fixed:test', provider: 'fixed', base_url: '', model: 'test', timeout_seconds: 10, available: true }]))
    if (url.endsWith('/api/projects')) return new Response(JSON.stringify([{ id: 'project-1', title: '测试小说', is_builtin: false, source_encoding: 'utf-8', source_size: 12, created_at: '', updated_at: '' }]))
    if (url.includes('/api/projects/project-1/attribute-jobs')) {
      expect(init?.method).toBe('POST')
      expect(JSON.parse(String(init?.body))).toEqual({ model_profile_id: 'fixed:test' })
      return new Response(JSON.stringify({ id: 'job-attr', project_id: 'project-1', model_profile_id: 'fixed:test', kind: 'ATTRIBUTE_BACKFILL', status: 'QUEUED', completed_chunks: 0, total_chunks: 0 }), { status: 201 })
    }
    return new Response(JSON.stringify([]))
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/build?project=project-1']}><ProjectProvider><BuildPage /></ProjectProvider></MemoryRouter>)

  await waitFor(() => expect(screen.getByLabelText('属性补抽模型')).toHaveValue('fixed:test'))
  await user.click(screen.getByRole('button', { name: '重新抽取属性' }))

  expect(await screen.findByText('等待 Worker')).toBeVisible()
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining('/api/projects/project-1/attribute-jobs'),
    expect.objectContaining({ method: 'POST' }),
  )
})

it('disables attribute backfill when the current project has no source TXT', async () => {
  vi.stubGlobal('EventSource', FakeEventSource)
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url.includes('model-profiles')) return new Response(JSON.stringify([{ id: 'fixed:test', provider: 'fixed', base_url: '', model: 'test', timeout_seconds: 10, available: true }]))
    if (url.endsWith('/api/projects')) return new Response(JSON.stringify([{ id: 'project-1', title: '测试小说', is_builtin: false, created_at: '', updated_at: '' }]))
    return new Response(JSON.stringify([]))
  }))
  render(<MemoryRouter initialEntries={['/build?project=project-1']}><ProjectProvider><BuildPage /></ProjectProvider></MemoryRouter>)

  expect(await screen.findByText('原始 TXT 不可用')).toBeVisible()
  expect(screen.getByRole('button', { name: '重新抽取属性' })).toBeDisabled()
})
