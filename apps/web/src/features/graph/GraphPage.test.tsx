import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { GraphPage } from './GraphPage'

const entity = {
  id: 'xiaoao:person:linghuchong', project_id: 'xiaoao', type: 'Person',
  name: '令狐沖', aliases: ['令狐冲'], description: '华山派大弟子。',
}

describe('GraphPage', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('searches and opens an entity with evidence', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/search')) return new Response(JSON.stringify([entity]))
      if (url.includes('/entities/')) return new Response(JSON.stringify({
        ...entity,
        facts: [{ id: 'f1', type: 'MASTER_OF', source_id: 'yue', target_id: entity.id,
          evidence: [{ id: 'e1', chapter_id: 'c5', chapter_number: 5, chapter_title: '治傷', start_offset: 1, end_offset: 2, quote: '嫡派傳人' }] }],
      }))
      return new Response(JSON.stringify({ nodes: [entity], edges: [] }))
    }))
    const user = userEvent.setup()
    render(<GraphPage />)

    await user.type(screen.getByRole('searchbox'), '令狐冲')
    await user.click(await screen.findByRole('button', { name: /令狐沖/ }))

    expect(await screen.findByText('第五章 · 治傷')).toBeVisible()
    expect(screen.getByText('嫡派傳人')).toBeVisible()
  })

  it('clears a stale request error after a successful retry', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 500 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([entity])))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<GraphPage />)

    await user.type(screen.getByRole('searchbox'), '令')
    expect(await screen.findByRole('alert')).toHaveTextContent('请求失败（500）')

    await user.type(screen.getByRole('searchbox'), '狐')
    expect(await screen.findByRole('button', { name: /令狐沖/ })).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('adds a visible fact to the review queue', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/entities/linghu')) {
        return new Response(JSON.stringify({
          id: 'linghu',
          project_id: 'xiaoao',
          type: 'Person',
          name: '令狐冲',
          aliases: [],
          description: '华山弟子',
          facts: [{
            id: 'fact-1',
            type: 'MASTER_OF',
            source_id: 'yue',
            target_id: 'linghu',
            evidence: [{
              id: 'ev-1',
              chapter_id: 'c1',
              chapter_number: 1,
              chapter_title: '第一章',
              start_offset: 0,
              end_offset: 4,
              quote: '岳不群传剑',
            }],
          }],
        }))
      }
      if (url.includes('/api/graph/neighborhood')) return new Response(JSON.stringify({ nodes: [], edges: [] }))
      if (url.includes('/api/projects/xiaoao/review/items') && init?.method === 'POST') {
        return new Response(JSON.stringify({ id: 'review-1' }))
      }
      if (url.includes('/api/graph/search')) {
        return new Response(JSON.stringify([{
          id: 'linghu',
          project_id: 'xiaoao',
          type: 'Person',
          name: '令狐冲',
          aliases: [],
          description: '华山弟子',
        }]))
      }
      return new Response(JSON.stringify({}))
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<GraphPage />)

    await user.type(screen.getByRole('searchbox'), '令狐冲')
    await user.click(await screen.findByText('令狐冲'))
    await user.click(await screen.findByRole('button', { name: '加入审核' }))

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/projects/xiaoao/review/items'),
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
