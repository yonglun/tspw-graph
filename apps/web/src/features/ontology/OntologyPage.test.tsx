import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { OntologyPage } from './OntologyPage'

describe('OntologyPage', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('expands an ontology class and shows effective inherited properties', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      entity_types: [{
        id: 'Person', label: '人物', description: '小说中的人物角色', color: '#4f46e5',
        property_definitions: [],
        effective_property_definitions: [{ id: 'gender', label: '性别', description: '人物性别', value_type: 'ENUM', multiple: false, enum_values: ['男', '女'] }],
      }],
      relation_types: [],
      example: { subject: '令狐冲', predicate: 'KNOWS', object: '岳不群' },
    }))))
    const user = userEvent.setup()
    render(<OntologyPage />)

    await user.click(await screen.findByRole('button', { name: /人物/ }))

    const personCard = screen.getByRole('article', { name: /人物/ })
    expect(within(personCard).getByTestId('entity-type-dot')).toBeVisible()
    expect(screen.getByText('性别')).toBeVisible()
    expect(screen.getByText('人物性别')).toBeVisible()
    expect(screen.getByText(/男、女/)).toBeVisible()
    expect(screen.getByRole('button', { name: /收起属性/ })).toHaveAttribute('aria-expanded', 'true')
  })

  it('presents the ABox example as a structured instance relationship', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      entity_types: [],
      relation_types: [],
      example: { subject: '令狐冲', predicate: 'KNOWS', object: '独孤九剑' },
    }))))
    const user = userEvent.setup()
    render(<OntologyPage />)

    await user.click(await screen.findByRole('button', { name: 'ABox 实例层' }))

    const example = screen.getByRole('figure', { name: 'ABox 实例关系示例' })
    expect(within(example).getByRole('group', { name: '主体实例' })).toHaveTextContent('令狐冲')
    expect(within(example).getByRole('group', { name: '关系类型' })).toHaveTextContent('KNOWS')
    expect(within(example).getByRole('group', { name: '客体实例' })).toHaveTextContent('独孤九剑')
    expect(within(example).getByText('通过约束检查')).toBeVisible()
    expect(within(example).getByText(/主体必须是人物/)).toBeVisible()
  })
})
