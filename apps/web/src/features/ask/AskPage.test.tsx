import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { ProjectProvider } from '../../app/ProjectContext'
import { ProjectSwitcher } from '../projects/ProjectSwitcher'
import { AskPage } from './AskPage'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const projects = [
  { id: 'project-xiaoao', title: '笑傲江湖', is_builtin: false, created_at: '', updated_at: '' },
  { id: 'project-shujian', title: '书剑恩仇录', is_builtin: false, created_at: '', updated_at: '' },
]

const shujianSuggestions = {
  project_id: 'project-shujian',
  project_title: '书剑恩仇录',
  representative_entity: { id: 'chen', name: '陈家洛', type: 'Person' },
  suggestions: [
    { id: 'relation:MEMBER_OF', question: '陈家洛属于哪个门派？', kind: 'relation', capability: 'MEMBER_OF' },
    { id: 'attribute:gender', question: '陈家洛的性别是什么？', kind: 'attribute', capability: 'gender' },
  ],
}

const xiaoaoSuggestions = {
  project_id: 'project-xiaoao',
  project_title: '笑傲江湖',
  representative_entity: { id: 'linghu', name: '令狐冲', type: 'Person' },
  suggestions: [
    { id: 'attribute:gender', question: '令狐冲的性别是什么？', kind: 'attribute', capability: 'gender' },
  ],
}

const answerResponse = {
  answer: '令狐沖的性别是男。',
  path: [],
  query_explanation: '属性证据',
  cypher_template: 'MATCH attribute',
  parameters: { project_id: 'project-xiaoao', property_id: 'gender' },
  evidence: [{
    id: 'e1', chapter_id: 'c1', chapter_number: 1, chapter_title: '开端',
    start_offset: 0, end_offset: 3, quote: '令狐冲是男',
  }],
}

it('uses the selected project title and dynamic suggestions', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url === '/api/projects') return new Response(JSON.stringify(projects))
    if (url.includes('/api/projects/project-shujian/qa-suggestions')) {
      return new Response(JSON.stringify(shujianSuggestions))
    }
    return new Response(JSON.stringify(xiaoaoSuggestions))
  }))

  render(
    <MemoryRouter initialEntries={['/ask?project=project-shujian']}>
      <ProjectProvider><AskPage /></ProjectProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('向《书剑恩仇录》图谱提问')).toBeVisible()
  expect(screen.getByRole('button', { name: '陈家洛属于哪个门派？' })).toBeVisible()
  expect(screen.queryByText(/令狐冲/)).not.toBeInTheDocument()
})

it('shows an empty recommendation state without hard-coded fallbacks', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url === '/api/projects') return new Response(JSON.stringify(projects))
    return new Response(JSON.stringify({
      project_id: 'project-shujian',
      project_title: '书剑恩仇录',
      representative_entity: null,
      suggestions: [],
    }))
  }))

  render(
    <MemoryRouter initialEntries={['/ask?project=project-shujian']}>
      <ProjectProvider><AskPage /></ProjectProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('当前项目暂无可推荐的问题')).toBeVisible()
  expect(screen.queryByText(/令狐冲/)).not.toBeInTheDocument()
})

it('clears the previous answer when the project changes', async () => {
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url === '/api/projects') return new Response(JSON.stringify(projects))
    if (url.includes('project-shujian/qa-suggestions')) {
      return new Response(JSON.stringify(shujianSuggestions))
    }
    if (url.includes('project-xiaoao/qa-suggestions')) {
      return new Response(JSON.stringify(xiaoaoSuggestions))
    }
    if (url === '/api/ask') return new Response(JSON.stringify(answerResponse))
    throw new Error(`unexpected request: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()

  render(
    <MemoryRouter initialEntries={['/ask?project=project-xiaoao']}>
      <ProjectProvider><ProjectSwitcher /><AskPage /></ProjectProvider>
    </MemoryRouter>,
  )

  await user.click(await screen.findByRole('button', { name: '令狐冲的性别是什么？' }))
  await user.click(screen.getByRole('button', { name: '查询图谱' }))
  expect(await screen.findByRole('heading', { name: '令狐沖的性别是男。' })).toBeVisible()

  await user.selectOptions(screen.getByRole('combobox', { name: '当前项目' }), 'project-shujian')

  expect(screen.queryByRole('heading', { name: '令狐沖的性别是男。' })).not.toBeInTheDocument()
  expect(await screen.findByText('向《书剑恩仇录》图谱提问')).toBeVisible()
  expect(await screen.findByRole('button', { name: '陈家洛属于哪个门派？' })).toBeVisible()
})

it('ignores an older suggestions response after a rapid project switch', async () => {
  let resolveOld!: (response: Response) => void
  const oldRequest = new Promise<Response>(resolve => { resolveOld = resolve })
  vi.stubGlobal('fetch', vi.fn((input: string | URL | Request) => {
    const url = String(input)
    if (url === '/api/projects') return Promise.resolve(new Response(JSON.stringify(projects)))
    if (url.includes('project-xiaoao/qa-suggestions')) return oldRequest
    if (url.includes('project-shujian/qa-suggestions')) {
      return Promise.resolve(new Response(JSON.stringify(shujianSuggestions)))
    }
    return Promise.reject(new Error(`unexpected request: ${url}`))
  }))
  const user = userEvent.setup()

  render(
    <MemoryRouter initialEntries={['/ask?project=project-xiaoao']}>
      <ProjectProvider><ProjectSwitcher /><AskPage /></ProjectProvider>
    </MemoryRouter>,
  )

  await screen.findByRole('option', { name: '书剑恩仇录' })
  await user.selectOptions(screen.getByRole('combobox', { name: '当前项目' }), 'project-shujian')
  expect(await screen.findByRole('button', { name: '陈家洛属于哪个门派？' })).toBeVisible()

  await act(async () => {
    resolveOld(new Response(JSON.stringify(xiaoaoSuggestions)))
  })

  await waitFor(() => expect(screen.queryByText('令狐冲的性别是什么？')).not.toBeInTheDocument())
  expect(screen.getByText('向《书剑恩仇录》图谱提问')).toBeVisible()
})

it('submits a dynamic attribute question and renders evidence', async () => {
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url === '/api/projects') return new Response(JSON.stringify(projects))
    if (url.includes('project-shujian/qa-suggestions')) {
      return new Response(JSON.stringify(shujianSuggestions))
    }
    if (url === '/api/ask') return new Response(JSON.stringify(answerResponse))
    throw new Error(`unexpected request: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(
    <MemoryRouter initialEntries={['/ask?project=project-shujian']}>
      <ProjectProvider><AskPage /></ProjectProvider>
    </MemoryRouter>,
  )

  await user.click(await screen.findByRole('button', { name: '陈家洛的性别是什么？' }))
  await user.click(screen.getByRole('button', { name: '查询图谱' }))

  expect(await screen.findByRole('heading', { name: '令狐沖的性别是男。' })).toBeVisible()
  expect(screen.getByText('令狐冲是男')).toBeVisible()
  expect(fetchMock).toHaveBeenCalledWith('/api/ask', expect.objectContaining({ method: 'POST' }))
})
