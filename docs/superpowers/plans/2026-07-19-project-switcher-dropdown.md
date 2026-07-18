# Viewport-Safe Project Switcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the native project `select` with an accessible custom listbox whose popup always remains inside the browser viewport.

**Architecture:** `ProjectSwitcher` keeps all project-domain behavior and delegates popup geometry and listbox interaction to a focused `ViewportListbox` component. A pure `placeListbox` function computes fixed-position popup geometry; React renders the popup through a body portal so header overflow and stacking contexts cannot clip it.

**Tech Stack:** React 19, React DOM portal, TypeScript 5.8, Vitest, Testing Library, project Vercel-style CSS tokens.

## Global Constraints

- Do not add a third-party UI or positioning dependency.
- Prefer downward expansion, fall back upward, and preserve an 8px viewport margin.
- Limit popup height to 320px and use internal scrolling for additional projects.
- Preserve project URL synchronization, build-time locking, and cross-page selection behavior.
- Support mouse, outside click, `ArrowUp`, `ArrowDown`, `Home`, `End`, `Enter`, `Space`, and `Escape`.
- Keep the accessible name `当前项目`.

---

### Task 1: Pure viewport positioning

**Files:**
- Create: `apps/web/src/features/projects/listboxPosition.ts`
- Test: `apps/web/src/features/projects/listboxPosition.test.ts`

**Interfaces:**
- Produces: `placeListbox(trigger: Pick<DOMRect, 'top' | 'bottom' | 'left' | 'right' | 'width'>, viewport: { width: number; height: number }, desiredHeight: number): { top: number; left: number; width: number; maxHeight: number; placement: 'top' | 'bottom' }`

- [ ] **Step 1: Write failing geometry tests**

```ts
import { describe, expect, it } from 'vitest'
import { placeListbox } from './listboxPosition'

describe('placeListbox', () => {
  it('opens below with an 8px viewport margin when space is available', () => {
    expect(placeListbox({ top: 40, bottom: 72, left: 900, right: 1080, width: 180 }, { width: 1200, height: 800 }, 240)).toEqual({
      top: 80, left: 900, width: 180, maxHeight: 240, placement: 'bottom',
    })
  })

  it('opens above and caps height when the trigger is near the bottom', () => {
    expect(placeListbox({ top: 700, bottom: 732, left: 900, right: 1080, width: 180 }, { width: 1200, height: 760 }, 320)).toEqual({
      top: 372, left: 900, width: 180, maxHeight: 320, placement: 'top',
    })
  })

  it('shifts left and shrinks on a narrow viewport', () => {
    expect(placeListbox({ top: 40, bottom: 72, left: 330, right: 510, width: 180 }, { width: 390, height: 800 }, 240)).toEqual({
      top: 80, left: 202, width: 180, maxHeight: 240, placement: 'bottom',
    })
  })
})
```

- [ ] **Step 2: Run the tests and verify the missing module failure**

Run: `npm test -- --run src/features/projects/listboxPosition.test.ts`

Expected: FAIL because `./listboxPosition` does not exist.

- [ ] **Step 3: Implement deterministic placement**

```ts
export type ListboxPlacement = {
  top: number
  left: number
  width: number
  maxHeight: number
  placement: 'top' | 'bottom'
}

const VIEWPORT_MARGIN = 8
const POPUP_GAP = 8
const MAX_HEIGHT = 320

export function placeListbox(
  trigger: Pick<DOMRect, 'top' | 'bottom' | 'left' | 'right' | 'width'>,
  viewport: { width: number; height: number },
  desiredHeight: number,
): ListboxPlacement {
  const width = Math.min(trigger.width, viewport.width - VIEWPORT_MARGIN * 2)
  const left = Math.min(
    Math.max(VIEWPORT_MARGIN, trigger.left),
    viewport.width - VIEWPORT_MARGIN - width,
  )
  const below = viewport.height - VIEWPORT_MARGIN - trigger.bottom - POPUP_GAP
  const above = trigger.top - VIEWPORT_MARGIN - POPUP_GAP
  const placement = below >= Math.min(desiredHeight, MAX_HEIGHT) || below >= above ? 'bottom' : 'top'
  const available = Math.max(0, placement === 'bottom' ? below : above)
  const maxHeight = Math.min(MAX_HEIGHT, desiredHeight, available)
  const top = placement === 'bottom'
    ? trigger.bottom + POPUP_GAP
    : trigger.top - POPUP_GAP - maxHeight
  return { top, left, width, maxHeight, placement }
}
```

- [ ] **Step 4: Run the focused tests**

Run: `npm test -- --run src/features/projects/listboxPosition.test.ts`

Expected: 3 tests PASS.

- [ ] **Step 5: Commit the geometry unit**

```bash
git add apps/web/src/features/projects/listboxPosition.ts apps/web/src/features/projects/listboxPosition.test.ts
git commit -m "feat: calculate viewport-safe listbox placement"
```

### Task 2: Accessible portal listbox

**Files:**
- Create: `apps/web/src/features/projects/ViewportListbox.tsx`
- Create: `apps/web/src/features/projects/ViewportListbox.test.tsx`
- Modify: `apps/web/src/styles/vercel.css`

**Interfaces:**
- Consumes: `placeListbox` from Task 1.
- Produces: `ViewportListbox({ label, value, options, disabled, disabledTitle, onChange })`, where `options` is `Array<{ value: string; label: string }>`.

- [ ] **Step 1: Write failing interaction tests**

```tsx
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { ViewportListbox } from './ViewportListbox'

afterEach(cleanup)

const options = [
  { value: 'p-1', label: '项目一' },
  { value: 'p-2', label: '项目二' },
]

it('selects an option and closes the portal listbox', async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<ViewportListbox label="当前项目" value="p-1" options={options} onChange={onChange} />)
  await user.click(screen.getByRole('button', { name: '当前项目' }))
  await user.click(screen.getByRole('option', { name: '项目二' }))
  expect(onChange).toHaveBeenCalledWith('p-2')
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
})

it('supports arrow navigation, selection, and escape focus restoration', async () => {
  const user = userEvent.setup()
  const onChange = vi.fn()
  render(<ViewportListbox label="当前项目" value="p-1" options={options} onChange={onChange} />)
  const trigger = screen.getByRole('button', { name: '当前项目' })
  await user.click(trigger)
  await user.keyboard('{ArrowDown}{Enter}')
  expect(onChange).toHaveBeenCalledWith('p-2')
  expect(trigger).toHaveFocus()
  await user.click(trigger)
  await user.keyboard('{Escape}')
  expect(trigger).toHaveFocus()
})

it('does not open while disabled', async () => {
  const user = userEvent.setup()
  render(<ViewportListbox label="当前项目" value="p-1" options={options} disabled disabledTitle="构建完成前不能切换项目" onChange={() => undefined} />)
  const trigger = screen.getByRole('button', { name: '当前项目' })
  expect(trigger).toBeDisabled()
  await user.click(trigger)
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests and verify the missing component failure**

Run: `npm test -- --run src/features/projects/ViewportListbox.test.tsx`

Expected: FAIL because `ViewportListbox` does not exist.

- [ ] **Step 3: Implement the component**

Implement a focused React component with these exact behaviors:

```tsx
type Option = { value: string; label: string }
type Props = {
  label: string
  value: string
  options: Option[]
  disabled?: boolean
  disabledTitle?: string
  onChange: (value: string) => void
}
```

- Use `createPortal(menu, document.body)`.
- Use `useId()` for the listbox ID and set `aria-controls`, `aria-expanded`, and `aria-haspopup="listbox"` on the trigger.
- On open, call `placeListbox(trigger.getBoundingClientRect(), { width: window.innerWidth, height: window.innerHeight }, Math.min(options.length * 40 + 8, 320))`.
- Store an active option index initialized from `value`; move it with arrows/Home/End and select it with Enter/Space.
- Close on outside pointer down, Escape, resize, or scroll; restore trigger focus for keyboard closure and selection.
- Render a check mark with `aria-hidden="true"` beside the selected option.

- [ ] **Step 4: Add Vercel-style popup CSS**

Add `.viewport-listbox-trigger`, `.viewport-listbox-menu`, and `.viewport-listbox-option` rules using existing design tokens:

```css
.viewport-listbox-trigger {
  width: 100%;
  height: 32px;
  padding: 0 32px 0 12px;
  border: 0;
  border-radius: var(--ds-radius);
  background: var(--ds-background-elevated);
  color: var(--ds-text-primary);
  box-shadow: var(--ds-shadow-border);
  font: inherit;
  text-align: left;
}

.viewport-listbox-menu {
  position: fixed;
  z-index: 1000;
  margin: 0;
  padding: 4px;
  overflow-y: auto;
  border: 0;
  border-radius: var(--ds-radius-large);
  background: var(--ds-background-elevated);
  box-shadow: var(--ds-shadow-menu);
  list-style: none;
}

.viewport-listbox-option {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  align-items: center;
  min-height: 40px;
  padding: 0 8px;
  border-radius: var(--ds-radius);
  cursor: default;
}

.viewport-listbox-option[aria-selected='true'],
.viewport-listbox-option.is-active {
  background: var(--ds-background-hover);
}
```

- [ ] **Step 5: Run focused component and type checks**

Run: `npm test -- --run src/features/projects/ViewportListbox.test.tsx src/features/projects/listboxPosition.test.ts && npm run typecheck`

Expected: all focused tests PASS and TypeScript exits 0.

- [ ] **Step 6: Commit the reusable listbox**

```bash
git add apps/web/src/features/projects/ViewportListbox.tsx apps/web/src/features/projects/ViewportListbox.test.tsx apps/web/src/styles/vercel.css
git commit -m "feat: add accessible viewport-safe listbox"
```

### Task 3: Integrate project switching and prevent regressions

**Files:**
- Modify: `apps/web/src/features/projects/ProjectSwitcher.tsx`
- Modify: `apps/web/src/app/ProjectContext.test.tsx`
- Modify: `apps/web/src/App.test.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.test.tsx`
- Modify: `apps/web/src/features/ask/AskPage.test.tsx`
- Modify: `apps/web/src/styles/vercel.css`

**Interfaces:**
- Consumes: `ViewportListbox` from Task 2.
- Preserves: `ProjectContext.setProjectId(projectId: string)` and accessible control name `当前项目`.

- [ ] **Step 1: Convert existing switch tests to user-visible listbox interaction**

Replace each `user.selectOptions(...)` sequence with:

```ts
await user.click(screen.getByRole('button', { name: '当前项目' }))
await user.click(await screen.findByRole('option', { name: '项目二' }))
```

Replace native value assertions with visible-name assertions:

```ts
expect(screen.getByRole('button', { name: '当前项目' })).toHaveTextContent('笑傲江湖完整版')
```

Keep all existing assertions about URL cleanup, graph clearing/reopening, QA suggestions, navigation persistence, and disabled state.

- [ ] **Step 2: Run the affected tests and verify they fail against the native select**

Run: `npm test -- --run src/app/ProjectContext.test.tsx src/App.test.tsx src/features/graph/GraphPage.test.tsx src/features/ask/AskPage.test.tsx`

Expected: FAIL because the native select is not a button-driven listbox.

- [ ] **Step 3: Replace the native select in `ProjectSwitcher`**

```tsx
import { useProject } from '../../app/ProjectContext'
import { DEFAULT_PROJECT_ID } from '../../api/client'
import { ViewportListbox } from './ViewportListbox'

export function ProjectSwitcher() {
  const { projects, projectId, setProjectId, projectSwitchLocked } = useProject()
  const userProjects = projects.filter(item => !item.is_builtin)
  const visibleProjects = userProjects.length > 0 ? userProjects : projects
  const options = visibleProjects.length > 0
    ? visibleProjects.map(item => ({ value: item.id, label: item.title }))
    : [{ value: DEFAULT_PROJECT_ID, label: '笑傲江湖' }]

  return (
    <div className="project-switcher">
      <span aria-hidden="true">当前项目</span>
      <ViewportListbox
        label="当前项目"
        value={projectId}
        options={options}
        disabled={projectSwitchLocked}
        disabledTitle={projectSwitchLocked ? '构建完成前不能切换项目' : undefined}
        onChange={setProjectId}
      />
    </div>
  )
}
```

- [ ] **Step 4: Remove obsolete native-select CSS selectors**

Change `.project-switcher select` and `.project-switcher select:disabled` rules to target `.viewport-listbox-trigger` and its disabled state. Preserve current 32px header control height, width, font size, and mobile layout.

- [ ] **Step 5: Run the complete web verification**

Run: `npm test -- --run && npm run typecheck && npm run build`

Expected: all web tests PASS, TypeScript exits 0, and Vite production build succeeds.

- [ ] **Step 6: Perform browser boundary verification**

Verify `/graph` at desktop and widths 820px and 390px:

1. Open the project switcher near the screen top.
2. Confirm the popup remains at least 8px inside all viewport edges.
3. Confirm a long project list scrolls internally and does not create horizontal page scrolling.
4. Select another project and confirm the URL and page content update.
5. Navigate using arrows and Escape and confirm focus returns to the trigger.

- [ ] **Step 7: Commit the integration**

```bash
git add apps/web/src/features/projects/ProjectSwitcher.tsx apps/web/src/app/ProjectContext.test.tsx apps/web/src/App.test.tsx apps/web/src/features/graph/GraphPage.test.tsx apps/web/src/features/ask/AskPage.test.tsx apps/web/src/styles/vercel.css
git commit -m "fix: keep project menu inside viewport"
```

### Task 4: Final review

**Files:**
- Review: all files changed by Tasks 1–3

**Interfaces:**
- Consumes: completed viewport-safe project switcher.
- Produces: merge-ready, verified change set.

- [ ] **Step 1: Inspect the final diff**

Run: `git diff master...HEAD -- apps/web docs/superpowers`

Expected: only the approved project-switcher change, its tests, and design/plan documents.

- [ ] **Step 2: Check formatting and repository state**

Run: `git diff --check && git status --short`

Expected: no whitespace errors and no unintended files.

- [ ] **Step 3: Run final web verification once more**

Run: `cd apps/web && npm test -- --run && npm run typecheck && npm run build`

Expected: all commands exit 0.
