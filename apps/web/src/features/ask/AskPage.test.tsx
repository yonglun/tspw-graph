import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'

import { ProjectProvider } from '../../app/ProjectContext'
import { AskPage } from './AskPage'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const response = {
  answer: '令狐沖的性别是男。',
  path: [],
  query_explanation: '属性证据',
  cypher_template: 'MATCH attribute',
  parameters: { project_id: 'xiaoao', property_id: 'gender' },
  evidence: [{
    id: 'e1', chapter_id: 'c1', chapter_number: 1, chapter_title: '开端',
    start_offset: 0, end_offset: 3, quote: '令狐冲是男',
  }],
}

it('shows relation and attribute sample questions', () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([]))))
  render(<MemoryRouter><ProjectProvider><AskPage /></ProjectProvider></MemoryRouter>)

  expect(screen.getByRole('button', { name: '令狐冲属于哪个门派？' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '令狐冲的性别是什么？' })).toBeInTheDocument()
})

it('submits an attribute question and renders evidence', async () => {
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    if (String(input).endsWith('/api/projects')) return new Response(JSON.stringify([]))
    return new Response(JSON.stringify(response))
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<MemoryRouter><ProjectProvider><AskPage /></ProjectProvider></MemoryRouter>)

  await user.click(screen.getByRole('button', { name: '令狐冲的性别是什么？' }))
  await user.click(screen.getByRole('button', { name: '查询图谱' }))

  expect(await screen.findByRole('heading', { name: '令狐沖的性别是男。' })).toBeVisible()
  expect(screen.getByText('令狐冲是男')).toBeVisible()
  expect(fetchMock).toHaveBeenCalledWith('/api/ask', expect.objectContaining({ method: 'POST' }))
})
