import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ProjectProvider } from '../../app/ProjectContext'
import { ProjectSwitcher } from '../projects/ProjectSwitcher'
import { BuildPage } from './BuildPage'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  listeners = new Map<string, EventListener>()
  onerror: ((event: Event) => void) | null = null

  constructor() {
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: EventListener) {
    this.listeners.set(type, listener)
  }

  emit(job: object) {
    this.listeners.get('job')?.({
      data: JSON.stringify(job),
    } as MessageEvent)
  }

  close() {}
}

afterEach(() => {
  cleanup()
  FakeEventSource.instances = []
  vi.unstubAllGlobals()
})

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
  expect(screen.getByRole('status', { name: 'QUEUED' })).toBeVisible()
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

it('locks build operations and reports real progress until completion', async () => {
  vi.stubGlobal('EventSource', FakeEventSource)
  const project = {
    id: 'project-1',
    title: '测试小说',
    is_builtin: false,
    source_encoding: 'utf-8',
    source_size: 12,
    created_at: '',
    updated_at: '',
  }
  const queued = {
    id: 'job-1',
    project_id: project.id,
    model_profile_id: 'fixed:test',
    status: 'QUEUED',
    completed_chunks: 0,
    total_chunks: 0,
  }
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url.includes('model-profiles')) return new Response(JSON.stringify([{ id: 'fixed:test', provider: 'fixed', base_url: '', model: 'test', timeout_seconds: 10, available: true }]))
    if (url.endsWith('/api/projects')) return new Response(JSON.stringify([project]))
    if (url.includes('/api/projects/upload')) return new Response(JSON.stringify({ project, job: queued }), { status: 201 })
    if (url.includes('/quality')) return new Response(JSON.stringify({ total_chunks: 2, successful_chunks: 2, failed_chunks: 0, accepted_entities: 0, accepted_facts: 0, accepted_evidence: 0, ambiguous_entities: 0, rejected_by_code: {}, model_calls: 2, retry_count: 0 }))
    return new Response(JSON.stringify(queued))
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/build?project=project-1']}><ProjectProvider><ProjectSwitcher /><BuildPage /></ProjectProvider></MemoryRouter>)

  await user.type(screen.getByLabelText('项目标题'), '测试小说')
  await user.upload(screen.getByLabelText('TXT 小说'), new File(['第一章'], 'book.txt', { type: 'text/plain' }))
  await waitFor(() => expect(screen.getByLabelText('模型配置')).toHaveValue('fixed:test'))
  await user.click(screen.getByRole('button', { name: '开始构建' }))

  await waitFor(() => expect(screen.getByLabelText('当前项目')).toBeDisabled())
  expect(screen.getByLabelText('项目标题')).toBeDisabled()
  expect(screen.getByLabelText('TXT 小说')).toBeDisabled()
  expect(screen.getByLabelText('模型配置')).toBeDisabled()
  expect(screen.getByLabelText('属性补抽模型')).toBeDisabled()
  expect(screen.queryByRole('button', { name: '暂停' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '取消' })).toBeVisible()

  FakeEventSource.instances.at(-1)?.emit({
    ...queued,
    status: 'IMPORTING',
    completed_chunks: 0,
    total_chunks: 2,
  })
  expect(await screen.findByText('正在抽取第 1 / 2 个片段')).toBeVisible()
  expect((screen.getByRole('progressbar') as HTMLProgressElement).value).toBe(0)

  FakeEventSource.instances.at(-1)?.emit({
    ...queued,
    status: 'IMPORTING',
    completed_chunks: 1,
    total_chunks: 2,
  })
  expect(await screen.findByText('已完成 1 / 2 个片段')).toBeVisible()
  expect((screen.getByRole('progressbar') as HTMLProgressElement).value).toBe(50)

  FakeEventSource.instances.at(-1)?.emit({
    ...queued,
    status: 'IMPORTING',
    completed_chunks: 2,
    total_chunks: 2,
  })
  expect(await screen.findByText('正在汇总并写入 Neo4j')).toBeVisible()
  expect(screen.queryByRole('button', { name: '取消' })).not.toBeInTheDocument()
  expect(screen.getByRole('progressbar')).not.toHaveAttribute('value')

  FakeEventSource.instances.at(-1)?.emit({
    ...queued,
    status: 'COMPLETED',
    completed_chunks: 2,
    total_chunks: 2,
  })
  expect(await screen.findByText('构建完成')).toBeVisible()
  await waitFor(() => expect(screen.getByLabelText('当前项目')).toBeEnabled())
  expect(screen.getByLabelText('项目标题')).toBeEnabled()
})
