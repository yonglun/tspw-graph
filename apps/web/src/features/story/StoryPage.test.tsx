import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'

import { StoryPage } from './StoryPage'

const people = [
  { id: 'linghu', project_id: 'xiaoao', type: 'Person', name: '令狐沖', aliases: ['令狐冲'], description: '' },
]

const events = [
  { event: { id: 'teaching', project_id: 'xiaoao', type: 'TeachingEvent', name: '思過崖傳劍', aliases: ['思过崖传剑'], description: '风清扬指点令狐冲。' }, chapter_number: 10 },
  { event: { id: 'meeting', project_id: 'xiaoao', type: 'Event', name: '五霸岡聚會', aliases: [], description: '群雄聚会。' }, chapter_number: 20 },
]

const detail = {
  event: events[0].event,
  chapter_number: 10,
  participants: [people[0], { id: 'feng', project_id: 'xiaoao', type: 'Person', name: '风清扬', aliases: [], description: '' }],
  evidence: [{ id: 'ev-1', chapter_id: 'chapter-10', chapter_number: 10, chapter_title: '传剑', start_offset: 1, end_offset: 6, quote: '风清扬传剑' }],
  relationship_states: {
    started: [{ id: 'fact-1', type: 'KNOWS', label: '掌握', source: people[0], target: { id: 'dugu', project_id: 'xiaoao', type: 'Swordplay', name: '独孤九剑', aliases: [], description: '' }, from_chapter: 10 }],
    active: [],
    ended: [],
  },
}

function mockFetch(options: { failDetailOnce?: boolean } = {}) {
  let detailCalls = 0
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url.includes('/search')) return new Response(JSON.stringify(people))
    if (url.includes('/timeline/')) {
      detailCalls += 1
      if (options.failDetailOnce && detailCalls === 1) return new Response(JSON.stringify({ detail: { code: 'GRAPH_UNAVAILABLE' } }), { status: 503 })
      if (url.includes('meeting')) return new Response(JSON.stringify({ ...detail, event: events[1].event, chapter_number: 20 }))
      return new Response(JSON.stringify(detail))
    }
    return new Response(JSON.stringify(events))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function LocationProbe() {
  const location = useLocation()
  return <output aria-label="location">{location.pathname}{location.search}</output>
}

function renderStory(withLocation = false) {
  return render(
    <MemoryRouter initialEntries={['/story?project=xiaoao']}>
      <StoryPage />
      {withLocation && <LocationProbe />}
    </MemoryRouter>,
  )
}

describe('StoryPage', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('expands an event with participants, temporal relationship groups, and evidence', async () => {
    mockFetch()
    const user = userEvent.setup()
    renderStory()

    const trigger = await screen.findByRole('button', { name: /思過崖傳劍/ })
    await user.click(trigger)

    expect(await screen.findByRole('heading', { name: '新增关系' })).toBeVisible()
    expect(screen.getByLabelText('新增关系')).toHaveTextContent('令狐沖 掌握 独孤九剑')
    expect(screen.getByText('本章无结束关系')).toBeVisible()
    expect(screen.getByText('风清扬传剑')).toBeVisible()
    expect(screen.getByText('参与人物')).toBeVisible()
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
  })

  it('keeps only one event expanded', async () => {
    mockFetch()
    const user = userEvent.setup()
    renderStory()

    const first = await screen.findByRole('button', { name: /思過崖傳劍/ })
    const second = screen.getByRole('button', { name: /五霸岡聚會/ })
    await user.click(first)
    await screen.findByText('风清扬传剑')
    await user.click(second)

    expect(first).toHaveAttribute('aria-expanded', 'false')
    expect(second).toHaveAttribute('aria-expanded', 'true')
  })

  it('reuses cached detail after collapsing and reopening', async () => {
    const fetchMock = mockFetch()
    const user = userEvent.setup()
    renderStory()

    const trigger = await screen.findByRole('button', { name: /思過崖傳劍/ })
    await user.click(trigger)
    await screen.findByText('风清扬传剑')
    await user.click(trigger)
    await user.click(trigger)

    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/timeline/teaching')).length).toBe(1)
  })

  it('shows an inline error and retries event detail', async () => {
    const fetchMock = mockFetch({ failDetailOnce: true })
    const user = userEvent.setup()
    renderStory()

    await user.click(await screen.findByRole('button', { name: /思過崖傳劍/ }))
    expect(await screen.findByText('详情加载失败')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '重试' }))

    expect(await screen.findByText('风清扬传剑')).toBeVisible()
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes('/timeline/teaching')).length).toBe(2)
  })

  it('collapses the selected event when the person filter changes', async () => {
    mockFetch()
    const user = userEvent.setup()
    renderStory()

    const trigger = await screen.findByRole('button', { name: /思過崖傳劍/ })
    await user.click(trigger)
    await screen.findByText('风清扬传剑')
    await user.selectOptions(screen.getByRole('combobox', { name: '人物' }), 'linghu')

    await waitFor(() => expect(trigger).toHaveAttribute('aria-expanded', 'false'))
  })

  it('opens the selected event in its graph neighborhood', async () => {
    mockFetch()
    const user = userEvent.setup()
    renderStory(true)

    await user.click(await screen.findByRole('button', { name: /思過崖傳劍/ }))
    await screen.findByText('风清扬传剑')
    await user.click(screen.getByRole('button', { name: '在图谱中查看' }))

    expect(screen.getByLabelText('location')).toHaveTextContent('/graph?project=xiaoao&entity=teaching')
  })
})
