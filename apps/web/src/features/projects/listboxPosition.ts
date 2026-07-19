const VIEWPORT_MARGIN = 8
const LISTBOX_GAP = 8
const LISTBOX_MAX_HEIGHT = 320

type TriggerRect = Pick<DOMRect, 'top' | 'bottom' | 'left' | 'right' | 'width'>
type Viewport = { width: number; height: number }

export type ListboxPlacement = {
  top: number
  left: number
  width: number
  maxHeight: number
  placement: 'top' | 'bottom'
}

export function placeListbox(
  trigger: TriggerRect,
  viewport: Viewport,
  desiredHeight: number,
): ListboxPlacement {
  const width = Math.min(trigger.width, Math.max(0, viewport.width - VIEWPORT_MARGIN * 2))
  const left = Math.min(
    Math.max(trigger.left, VIEWPORT_MARGIN),
    Math.max(VIEWPORT_MARGIN, viewport.width - VIEWPORT_MARGIN - width),
  )
  const maxHeight = Math.min(LISTBOX_MAX_HEIGHT, Math.max(0, viewport.height - VIEWPORT_MARGIN * 2))
  const contentHeight = Math.min(desiredHeight, maxHeight)
  const spaceBelow = viewport.height - trigger.bottom - LISTBOX_GAP - VIEWPORT_MARGIN
  const spaceAbove = trigger.top - LISTBOX_GAP - VIEWPORT_MARGIN
  const placement = spaceBelow >= contentHeight || spaceBelow >= spaceAbove ? 'bottom' : 'top'

  return {
    top:
      placement === 'bottom'
        ? Math.min(trigger.bottom + LISTBOX_GAP, viewport.height - VIEWPORT_MARGIN - contentHeight)
        : Math.max(VIEWPORT_MARGIN, trigger.top - LISTBOX_GAP - contentHeight),
    left,
    width,
    maxHeight,
    placement,
  }
}
