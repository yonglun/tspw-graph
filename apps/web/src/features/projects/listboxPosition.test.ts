import { describe, expect, it } from 'vitest'

import { placeListbox } from './listboxPosition'

describe('placeListbox', () => {
  it('places the listbox below the trigger when there is enough room', () => {
    expect(
      placeListbox(
        { top: 32, bottom: 72, left: 24, right: 204, width: 180 },
        { width: 1280, height: 800 },
        240,
      ),
    ).toEqual({
      top: 80,
      left: 24,
      width: 180,
      maxHeight: 320,
      placement: 'bottom',
    })
  })

  it('places the listbox above the trigger when the bottom edge is crowded', () => {
    expect(
      placeListbox(
        { top: 700, bottom: 740, left: 24, right: 204, width: 180 },
        { width: 1280, height: 800 },
        320,
      ),
    ).toEqual({
      top: 372,
      left: 24,
      width: 180,
      maxHeight: 320,
      placement: 'top',
    })
  })

  it('keeps the listbox inside a narrow viewport', () => {
    expect(
      placeListbox(
        { top: 32, bottom: 72, left: 330, right: 510, width: 180 },
        { width: 390, height: 800 },
        240,
      ),
    ).toEqual({
      top: 80,
      left: 202,
      width: 180,
      maxHeight: 320,
      placement: 'bottom',
    })
  })
})
