import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ProjectProvider } from '../../app/ProjectContext'
import { ReviewPage } from './ReviewPage'

const fetchMock = vi.fn()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function json(data: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(data) } as Response)
}

function renderPage() {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>
        <ProjectProvider>
          <ReviewPage />
        </ProjectProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('ReviewPage', () => {
  it('shows quality summary, queue and applies a fact decision', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/summary')) {
        return json({
          open_review_items: 1,
          accepted_facts: 2,
          rejected_facts: 0,
          pending_facts: 1,
          merged_entities: 0,
          split_aliases: 0,
          evidence_coverage: 0.8,
          review_completion_rate: 0.5,
          graph_fact_delta_before_after_review: 0,
        })
      }
      if (url.includes('/items/') && url.includes('/actions')) {
        return json({ item: { id: 'review-1', status: 'RESOLVED' }, action: { id: 'action-1' } })
      }
      if (url.includes('/items')) {
        return json({
          items: [
            {
              id: 'review-1',
              item_type: 'FACT',
              status: 'OPEN',
              reason_code: 'LOW_CONFIDENCE_FACT',
              target: { fact_id: 'fact-1' },
              evidence_ids: ['ev-1'],
              severity: 40,
              source: 'rule',
            },
          ],
        })
      }
      if (url.includes('/audit')) return json({ actions: [] })
      return json({})
    })
    renderPage()

    expect(await screen.findByText('审核工作台')).toBeInTheDocument()
    expect(screen.getByText('待审核项')).toBeInTheDocument()
    expect(screen.getByText('LOW_CONFIDENCE_FACT')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '接受事实' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/review/items/review-1/actions'),
        expect.objectContaining({ method: 'POST' }),
      ),
    )
  })

  it('searches entities and submits a manual merge', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/summary')) {
        return json({
          open_review_items: 0,
          accepted_facts: 0,
          rejected_facts: 0,
          pending_facts: 0,
          merged_entities: 0,
          split_aliases: 0,
          evidence_coverage: 0,
          review_completion_rate: 0,
          graph_fact_delta_before_after_review: 0,
        })
      }
      if (url.includes('/graph/search') && url.includes('%E4%BB%A4%E7%8B%90%E4%B8%AD')) {
        return json([
          { id: 'entity-typo', project_id: 'xiaoao', type: 'Person', name: '令狐中', aliases: [], description: '' },
        ])
      }
      if (url.includes('/graph/search') && url.includes('%E4%BB%A4%E7%8B%90%E5%86%B2')) {
        return json([
          { id: 'entity-canonical', project_id: 'xiaoao', type: 'Person', name: '令狐冲', aliases: [], description: '' },
        ])
      }
      if (url.includes('/entities/merge') && init?.method === 'POST') {
        return json({ item: { id: 'review-merge', status: 'RESOLVED' }, action: { id: 'action-merge' } })
      }
      if (url.includes('/items')) return json({ items: [] })
      if (url.includes('/audit')) return json({ actions: [] })
      return json({})
    })
    renderPage()

    await userEvent.type(await screen.findByLabelText('源实体'), '令狐中')
    await userEvent.click(await screen.findByRole('button', { name: '选择源实体 令狐中' }))
    await userEvent.type(screen.getByLabelText('目标实体'), '令狐冲')
    await userEvent.click(await screen.findByRole('button', { name: '选择目标实体 令狐冲' }))
    await userEvent.click(screen.getByRole('button', { name: '合并实体' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/review/entities/merge'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            source_entity_id: 'entity-typo',
            target_entity_id: 'entity-canonical',
          }),
        }),
      ),
    )
  })

  it('shows the human-readable fact triple and source evidence', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/summary')) return json({ open_review_items: 1, accepted_facts: 0, rejected_facts: 0, pending_facts: 1, merged_entities: 0, split_aliases: 0, evidence_coverage: 0, review_completion_rate: 0, graph_fact_delta_before_after_review: 0 })
      if (url.includes('/review/items?')) return json({ items: [{ id: 'review-fact', item_type: 'FACT', status: 'OPEN', reason_code: 'LOW_CONFIDENCE_FACT', target: { fact_id: 'fact-master' }, evidence_ids: ['ev-1'], severity: 40, source: 'rule' }] })
      if (url.includes('/api/graph/relations/fact-master')) return json({ id: 'fact-master', type: 'MASTER_OF', label: '师父', source_id: 'yue', target_id: 'linghu', source: { id: 'yue', project_id: 'xiaoao', type: 'Person', name: '岳不群', aliases: [], description: '' }, target: { id: 'linghu', project_id: 'xiaoao', type: 'Person', name: '令狐冲', aliases: [], description: '' }, evidence: [{ id: 'ev-1', chapter_id: 'c1', chapter_number: 1, chapter_title: '第一章', start_offset: 10, end_offset: 20, quote: '岳不群传授令狐冲剑法' }] })
      if (url.includes('/audit')) return json({ actions: [] })
      return json({})
    })
    renderPage()

    expect(await screen.findByText('岳不群')).toBeVisible()
    expect(screen.getByText('师父')).toBeVisible()
    expect(screen.getByText('令狐冲')).toBeVisible()
    expect(screen.getByText('岳不群传授令狐冲剑法')).toBeVisible()
    expect(screen.getAllByText('低置信度事实').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/模型对这条关系/)).toBeVisible()
    expect(screen.getByRole('status', { name: '严重度 40' })).toBeVisible()
  })
})
