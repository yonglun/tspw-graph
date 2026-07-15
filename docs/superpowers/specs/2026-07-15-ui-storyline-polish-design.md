# UI Controls, Graph Guidance, and Temporal Storyline Design

**Date:** 2026-07-15
**Status:** Approved design
**Branch:** `codex/ui-storyline-polish`

## 1. Goal

Improve four related usability problems without changing the product's Vercel-inspired visual language:

1. Replace oversized administrator login/logout text controls with compact icon controls.
2. Make graph entity-type colors explicit and legible in the legend.
3. Turn the graph's initial blank canvas into a centered, actionable empty state.
4. Make storyline events interactive and explain how participant relationships differ before, during, and after an event chapter.

The storyline must demonstrate the teaching goal that a static graph relation has a temporal context. It must distinguish relationships that started, remained active, or ended at a chapter boundary without claiming that every same-chapter change was caused by the selected event.

## 2. Scope

### In scope

- Header login and logout icon controls.
- Graph legend dots and graph empty-state layout.
- Expandable storyline event cards.
- A new event-detail API that returns participants, evidence, and chapter relationship states.
- Deep-linking from an expanded storyline event to the graph page with that event selected.
- Unit, integration, component, accessibility, and browser verification for these paths.

### Out of scope

- Changing authentication/session behavior.
- Adding a third-party icon package.
- Rebuilding or migrating graph data.
- Inferring causal relationships between events and facts.
- Precomputing or materializing timeline snapshots during extraction.
- Redesigning unrelated pages.

## 3. Visual and Interaction Design

### 3.1 Administrator controls

- Anonymous sessions see one 32px login icon button in the header.
- Authenticated sessions see one 32px logout icon button in the same position.
- Use small inline SVG icons so no icon dependency is added.
- Icon-only controls retain `aria-label` and `title` values of `管理员登录` and `退出管理员登录`.
- Controls use the existing achromatic hover treatment and double focus ring.
- The authenticated username is not required as visible header text; session identity remains available on the administrator page.

### 3.2 Graph legend

- Continue using `entityTypeStyles.ts` as the single source of truth for node and legend colors.
- Every visible legend entry contains a 10px circular color marker, a subtle one-pixel shadow border, and its text label.
- The legend lists only entity types present in the current neighborhood and retains the existing ontology order.
- Color is supplemental: every dot is paired with a text label.
- On narrow screens the legend wraps without overlapping graph controls or counts.

### 3.3 Graph empty state

- Center the empty state horizontally and vertically inside the graph canvas.
- Show a monochrome graph/network symbol, the heading `从一个人物开始`, a concise two-line explanation, and a compact action path.
- Copy:
  - Heading: `从一个人物开始`
  - Body: `在上方搜索并选择实体。图谱会先展开一度邻居，再由你决定是否继续探索。`
  - Path: `搜索 → 选择实体 → 展开关系`
- The empty state must not intercept the search input and must remain balanced at desktop and mobile canvas heights.

### 3.4 Storyline event cards

- Each event card header is a semantic button and can be operated with pointer, Enter, or Space.
- Only one event is expanded at a time. Clicking the expanded event collapses it.
- The collapsed card shows chapter, event type, name, and a plus indicator.
- The expanded card shows:
  - participant chips;
  - three relationship groups: `新增关系`, `持续关系`, `结束关系`;
  - event evidence with chapter metadata;
  - a `在图谱中查看` action.
- Each state group includes a text label and small status dot. Color alone never communicates status.
- Empty groups explicitly say `本章无新增关系`, `本章无持续关系`, or `本章无结束关系`.
- Introductory copy is shortened to `点击事件，查看参与者在该章节前后的关系状态。`

## 4. API and Data Model

Keep the existing timeline list endpoint lightweight. Add an on-demand event detail endpoint:

```http
GET /api/graph/timeline/{event_id}?project_id={project_id}
```

Proposed response:

```json
{
  "event": {
    "id": "event-id",
    "project_id": "project-id",
    "type": "Event",
    "name": "思过崖传剑",
    "aliases": [],
    "description": ""
  },
  "chapter_number": 10,
  "participants": [
    { "id": "person-id", "type": "Person", "name": "令狐冲" }
  ],
  "evidence": [
    {
      "id": "evidence-id",
      "chapter_id": "chapter-id",
      "chapter_number": 10,
      "chapter_title": "正文",
      "start_offset": 100,
      "end_offset": 120,
      "quote": "原文证据"
    }
  ],
  "relationship_states": {
    "started": [],
    "active": [],
    "ended": []
  }
}
```

Each relationship-state item contains the fact ID, relation type/label, source summary, target summary, `from_chapter`, and `to_chapter`.

## 5. Temporal Classification

The selected event chapter is the minimum valid chapter attached to the event's graph relationships. Participants are `Person` entities directly related to the event entity. Event evidence is collected from facts in which the event is the source or target, ordered by chapter and offset, and deduplicated by evidence ID.

For temporal facts connected to any participant:

- **Started:** `from_chapter == event_chapter`.
- **Ended:** `to_chapter == event_chapter` and the fact did not also start in the same chapter.
- **Active:** the fact started before the event chapter and has no end chapter or ends after the event chapter.
- Facts with neither boundary are eligible for `active` only when they are connected to a participant and are treated as timeless/current facts.
- Facts that start and end in the event chapter appear in `started`; their displayed range makes the single-chapter duration explicit.
- Duplicate facts are removed by fact ID.

The UI labels the result `章节前后状态变化`. It does not use causal language such as `事件导致`.

## 6. Client Data Flow

1. The storyline page loads the existing event list.
2. Clicking a collapsed event records it as the selected event and requests its detail.
3. While loading, only that card shows an inline skeleton.
4. A successful response renders participants, grouped state changes, evidence, and the graph action.
5. Details are cached in page state by event ID so reopening an event does not repeat the request.
6. Changing project clears the selected event and cache.
7. Changing the person filter collapses the current event and refreshes the list.
8. `在图谱中查看` navigates to `/graph?project={project_id}&entity={event_id}`.
9. The graph page recognizes the optional `entity` query parameter, retrieves that entity, and loads its one-hop neighborhood. Invalid or missing entities fall back to the normal empty state with a non-blocking error message.

## 7. Loading, Empty, and Error States

- Timeline list loading uses a page-level skeleton or status message.
- Event detail loading is local to the selected card.
- Event detail failure shows `详情加载失败` and a `重试` button in that card; other events remain usable.
- An event without participants, evidence, or relationship states still opens and explains which data is unavailable.
- API graph-unavailable errors retain the existing structured 503 response behavior.
- Stale detail responses must not reopen or overwrite a different selected event.

## 8. Accessibility

- Icon controls have stable accessible names and visible focus states.
- Event headers use native buttons with `aria-expanded` and `aria-controls`.
- Expanded regions use stable IDs and are announced through their headings.
- Loading and failure messages use appropriate status/alert roles.
- Legend and relationship-state colors always have adjacent text labels.
- Keyboard users can operate every new control without a pointer.

## 9. Testing and Verification

### Backend

- Detail response aggregates event, participants, and evidence.
- Started, active, and ended boundaries are classified correctly.
- Single-chapter facts, timeless facts, missing evidence, and duplicate graph rows are handled deterministically.
- Project scoping prevents cross-project event access.
- Unknown events return the existing entity-not-found response.

### Frontend

- Anonymous and authenticated headers expose icon-only controls through their accessible names.
- Legend entries render the mapped color marker and label.
- Empty graph canvas renders the new structured guidance.
- Event cards expand, collapse, enforce single selection, and reuse cached detail.
- Loading, error, retry, and empty state groups render correctly.
- Graph deep links select the event and load its neighborhood.
- Project/person changes clear incompatible event-detail state.

### Runtime verification

- Run API and web unit suites, web type checking, and production build.
- Verify desktop and narrow viewports in a real browser.
- Verify login/logout icon focus, event keyboard control, legend wrapping, graph empty-state alignment, deep linking, and a clean console.

## 10. Delivery Strategy

Implement in small increments:

1. Header icon controls and tests.
2. Graph legend and empty-state presentation with tests.
3. Event-detail models, repository query, service, router, and backend tests.
4. Expandable storyline UI and frontend tests.
5. Graph deep-link selection and tests.
6. Full verification and browser review.
