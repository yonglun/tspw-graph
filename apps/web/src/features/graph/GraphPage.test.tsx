import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { GraphPage } from './GraphPage'

const entity = {
  id: 'xiaoao:person:linghuchong', project_id: 'xiaoao', type: 'Person',
  name: '令狐沖', aliases: ['令狐冲'], description: '华山派大弟子。',
}
const yue = { id: 'yue', project_id: 'xiaoao', type: 'Person', name: '岳不群', aliases: [], description: '' }

function deferredResponse<T>() {
  let resolve!: (value: Response) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<Response>((res, rej) => { resolve = res; reject = rej })
  return {
    promise,
    resolve: (value: T) => resolve(new Response(JSON.stringify(value))),
    reject,
  }
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

  it('shows entity attributes, relation summaries and both evidence sections', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/graph/search')) return new Response(JSON.stringify([entity]))
      if (url.includes('/api/graph/neighborhood')) return new Response(JSON.stringify({ nodes: [entity], edges: [] }))
      if (url.includes('/api/entities/')) return new Response(JSON.stringify({
        ...entity,
        attributes: [{
          id: 'attr-identity',
          property_id: 'identity',
          label: '身份',
          value_type: 'TEXT',
          value: '华山派大弟子',
          confidence: 0.96,
          evidence: [{ id: 'attr-ev', chapter_id: 'c1', chapter_number: 1, chapter_title: '第一章', start_offset: 10, end_offset: 16, quote: '华山派大弟子' }],
        }],
        relations: [{ fact_id: 'fact-1', type: 'MASTER_OF', label: '师父', direction: 'INCOMING', other: { id: 'yue', type: 'Person', name: '岳不群' } }],
        facts: [{ id: 'fact-1', type: 'MASTER_OF', source_id: 'yue', target_id: entity.id,
          evidence: [{ id: 'fact-ev', chapter_id: 'c1', chapter_number: 1, chapter_title: '第一章', start_offset: 20, end_offset: 26, quote: '岳不群传剑' }] }],
      }))
      return new Response(JSON.stringify({}))
    }))
    const user = userEvent.setup()
    render(<GraphPage />)

    await user.type(screen.getByRole('searchbox'), '令狐冲')
    await user.click(await screen.findByRole('button', { name: /令狐沖/ }))

    expect(await screen.findByRole('heading', { name: '本体属性' })).toBeVisible()
    expect(screen.getByText('身份')).toBeVisible()
    expect(screen.getAllByText('华山派大弟子').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('heading', { name: '关系摘要' })).toBeVisible()
    expect(screen.getByText('岳不群')).toBeVisible()
    expect(screen.getByText('属性证据')).toBeVisible()
    expect(screen.getByText('关系证据')).toBeVisible()
    expect(screen.getByRole('button', { name: '加入审核' })).toBeVisible()
  })

  it('shows an empty attribute state when no attributes were extracted', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/graph/search')) return new Response(JSON.stringify([entity]))
      if (url.includes('/api/graph/neighborhood')) return new Response(JSON.stringify({ nodes: [entity], edges: [] }))
      if (url.includes('/api/entities/')) return new Response(JSON.stringify({ ...entity, attributes: [], relations: [], facts: [] }))
      return new Response(JSON.stringify({}))
    }))
    const user = userEvent.setup()
    render(<GraphPage />)

    await user.type(screen.getByRole('searchbox'), '令狐冲')
    await user.click(await screen.findByRole('button', { name: /令狐沖/ }))

    expect(await screen.findByText('尚未抽取到有证据支持的属性')).toBeVisible()
  })

  it('renders the selected center before graph and detail requests finish', async () => {
    const neighborhood = deferredResponse()
    const detail = deferredResponse()
    vi.stubGlobal('fetch', vi.fn((input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/graph/search')) return Promise.resolve(new Response(JSON.stringify([entity])))
      if (url.includes('/api/entities/')) return detail.promise
      if (url.includes('/api/graph/neighborhood')) return neighborhood.promise
      return Promise.resolve(new Response(JSON.stringify({})))
    }))
    const user = userEvent.setup()
    render(<GraphPage />)

    await user.type(screen.getByRole('searchbox'), '令狐冲')
    await user.click(await screen.findByRole('button', { name: /令狐沖/ }))

    expect(screen.getByLabelText('知识图谱画布')).toHaveTextContent('令狐沖')
    expect(screen.queryByText('岳不群')).not.toBeInTheDocument()

    neighborhood.resolve({ nodes: [entity, yue], edges: [{ id: 'e1', source_id: entity.id, target_id: yue.id, type: 'MASTER_OF', confidence: 1 }] })
    expect(await screen.findByText('岳不群')).toBeVisible()
  })

  it('requests one hop first and expands to two hops only on demand', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/graph/search')) return new Response(JSON.stringify([entity]))
      if (url.includes('/api/entities/')) return new Response(JSON.stringify({ ...entity, facts: [] }))
      if (url.includes('depth=1')) return new Response(JSON.stringify({ nodes: [entity, yue], edges: [] }))
      if (url.includes('depth=2')) return new Response(JSON.stringify({ nodes: [entity, yue, { id: 'feng', project_id: 'xiaoao', type: 'Person', name: '风清扬', aliases: [], description: '' }], edges: [] }))
      return new Response(JSON.stringify({}))
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<GraphPage />)

    await user.type(screen.getByRole('searchbox'), '令狐冲')
    await user.click(await screen.findByRole('button', { name: /令狐沖/ }))

    expect(await screen.findByText('岳不群')).toBeVisible()
    expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('depth=2'), expect.anything())

    await user.click(await screen.findByRole('button', { name: '展开二度关系' }))
    expect(await screen.findByText('风清扬')).toBeVisible()
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('depth=2'), expect.anything())
  })

  it('keeps the one-hop graph visible when two-hop expansion fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/graph/search')) return new Response(JSON.stringify([entity]))
      if (url.includes('/api/entities/')) return new Response(JSON.stringify({ ...entity, facts: [] }))
      if (url.includes('depth=1')) return new Response(JSON.stringify({ nodes: [entity, yue], edges: [] }))
      if (url.includes('depth=2')) return new Response('{}', { status: 503 })
      return new Response(JSON.stringify({}))
    }))
    const user = userEvent.setup()
    render(<GraphPage />)

    await user.type(screen.getByRole('searchbox'), '令狐冲')
    await user.click(await screen.findByRole('button', { name: /令狐沖/ }))
    expect(await screen.findByText('岳不群')).toBeVisible()

    await user.click(await screen.findByRole('button', { name: '展开二度关系' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('请求失败（503）')
    expect(screen.getByText('岳不群')).toBeVisible()
  })

  it('aborts stale entity requests when selecting a new result', async () => {
    const signals: AbortSignal[] = []
    vi.stubGlobal('fetch', vi.fn((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/graph/search')) return Promise.resolve(new Response(JSON.stringify([entity, yue])))
      if (url.includes('/api/entities/') || url.includes('/api/graph/neighborhood')) {
        if (init?.signal) signals.push(init.signal)
        return new Promise<Response>(() => undefined)
      }
      return Promise.resolve(new Response(JSON.stringify({})))
    }))
    const user = userEvent.setup()
    render(<GraphPage />)

    await user.type(screen.getByRole('searchbox'), '令狐')
    await user.click(await screen.findByRole('button', { name: /令狐沖/ }))
    await user.clear(screen.getByRole('searchbox'))
    await user.type(screen.getByRole('searchbox'), '岳')
    await user.click(await screen.findByRole('button', { name: /岳不群/ }))

    expect(signals.slice(0, 2).every(signal => signal.aborted)).toBe(true)
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

  it('shows graph legend entries for the visible entity types', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.includes('/api/graph/search')) return new Response(JSON.stringify([entity]))
      if (url.includes('/api/entities/')) return new Response(JSON.stringify({ ...entity, facts: [] }))
      if (url.includes('/api/graph/neighborhood')) {
        return new Response(JSON.stringify({
          nodes: [
            entity,
            { id: 'huashan', project_id: 'xiaoao', type: 'Sect', name: '华山派', aliases: [], description: '' },
            { id: 'dugu', project_id: 'xiaoao', type: 'Swordplay', name: '独孤九剑', aliases: [], description: '' },
          ],
          edges: [],
        }))
      }
      return new Response(JSON.stringify({}))
    }))
    const user = userEvent.setup()
    render(<GraphPage />)

    await user.type(screen.getByRole('searchbox'), '令狐冲')
    await user.click(await screen.findByRole('button', { name: /令狐沖/ }))

    expect(await screen.findByText('人物')).toBeVisible()
    expect(screen.getByText('门派')).toBeVisible()
    expect(screen.getByText('剑法')).toBeVisible()
    expect(screen.queryByText('其他实体')).not.toBeInTheDocument()
  })
})
