import { cleanup, render, screen } from '@testing-library/react'
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

    expect(screen.getByText('性别')).toBeVisible()
    expect(screen.getByText('人物性别')).toBeVisible()
    expect(screen.getByText(/男、女/)).toBeVisible()
    expect(screen.getByRole('button', { name: /收起属性/ })).toHaveAttribute('aria-expanded', 'true')
  })
})
