import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ViewportListbox } from './ViewportListbox'

const options = [
  { value: 'xiaoao', label: '笑傲江湖' },
  { value: 'tianlong', label: '天龙八部' },
]

afterEach(() => cleanup())

describe('ViewportListbox', () => {
  it('opens a portalled listbox and selects an option', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <ViewportListbox
        label="当前项目"
        value="xiaoao"
        options={options}
        onChange={onChange}
      />,
    )

    const trigger = screen.getByRole('button', { name: '当前项目' })
    await user.click(trigger)

    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('listbox', { name: '当前项目' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '笑傲江湖' })).toHaveAttribute('aria-selected', 'true')

    await user.click(screen.getByRole('option', { name: '天龙八部' }))

    expect(onChange).toHaveBeenCalledWith('tianlong')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('supports keyboard navigation and Escape', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <ViewportListbox
        label="当前项目"
        value="xiaoao"
        options={options}
        onChange={onChange}
      />,
    )

    const trigger = screen.getByRole('button', { name: '当前项目' })
    trigger.focus()
    await user.keyboard('{Enter}{ArrowDown}{Enter}')
    expect(onChange).toHaveBeenCalledWith('tianlong')

    await user.click(trigger)
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('cannot be opened while disabled', async () => {
    const user = userEvent.setup()
    render(
      <ViewportListbox
        label="当前项目"
        value="xiaoao"
        options={options}
        disabled
        disabledTitle="构建完成前不能切换项目"
        onChange={vi.fn()}
      />,
    )

    const trigger = screen.getByRole('button', { name: '当前项目' })
    expect(trigger).toBeDisabled()
    expect(trigger).toHaveAttribute('title', '构建完成前不能切换项目')
    await user.click(trigger)
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('closes when its surrounding route changes', async () => {
    const user = userEvent.setup()
    const view = render(
      <ViewportListbox
        label="当前项目"
        value="xiaoao"
        options={options}
        dismissSignal="/graph?project=xiaoao"
        onChange={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: '当前项目' }))
    expect(screen.getByRole('listbox')).toBeInTheDocument()

    view.rerender(
      <ViewportListbox
        label="当前项目"
        value="xiaoao"
        options={options}
        dismissSignal="/ask?project=xiaoao"
        onChange={vi.fn()}
      />,
    )
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
})
