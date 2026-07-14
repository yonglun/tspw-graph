import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'

import { StatusDot } from './StatusDot'

it('pairs a small status indicator with readable text', () => {
  render(<StatusDot tone="success">构建完成</StatusDot>)

  const status = screen.getByRole('status', { name: '构建完成' })
  expect(status).toHaveClass('status-dot-label', 'is-success')
  expect(status.querySelector('.status-dot')).toHaveAttribute('aria-hidden', 'true')
})
