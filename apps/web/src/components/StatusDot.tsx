import type { ReactNode } from 'react'

type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'error'

export function StatusDot({ children, label, tone = 'neutral' }: { children: ReactNode; label?: string; tone?: StatusTone }) {
  const accessibleLabel = label ?? (typeof children === 'string' || typeof children === 'number' ? String(children) : undefined)
  return <span className={`status-dot-label is-${tone}`} role="status" aria-label={accessibleLabel}>
    <i className="status-dot" aria-hidden="true" />
    <span>{children}</span>
  </span>
}
