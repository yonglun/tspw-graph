import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { GuidePage } from './GuidePage'

describe('GuidePage', () => {
  it('moves from a triple to the ontology explanation', async () => {
    const user = userEvent.setup()
    render(<GuidePage />)

    const triple = screen.getByRole('group', { name: '知识三元组示例' })
    expect(triple).toHaveTextContent('令狐冲')
    expect(triple).toHaveTextContent('掌握')
    expect(triple).toHaveTextContent('独孤九剑')
    expect(screen.queryByText('知')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '下一步：什么是本体' }))

    expect(screen.getByRole('heading', { name: '本体定义世界的规则' })).toBeVisible()
  })
})
