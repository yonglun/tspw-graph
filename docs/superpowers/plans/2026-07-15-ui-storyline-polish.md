# UI Controls, Graph Guidance, and Temporal Storyline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace header authentication text with accessible icons, make graph guidance visually legible, and turn storyline events into evidence-backed chapter relationship comparisons.

**Architecture:** Keep timeline list loading lightweight and add one on-demand event-detail endpoint. The Neo4j repository returns event context plus raw participant facts; `GraphService` classifies those facts into started, active, and ended states; React renders one cached expandable event at a time and deep-links to the graph.

**Tech Stack:** React 19, TypeScript 5.8, React Router 7, Vitest, Testing Library, FastAPI, Pydantic 2, Neo4j 5, pytest.

## Global Constraints

- Preserve the existing Vercel-inspired achromatic interface and use blue only for interaction/focus.
- Do not add a third-party icon dependency; use inline SVG.
- Keep authentication and session behavior unchanged.
- Do not rebuild, migrate, or precompute graph data.
- Describe results as `章节前后状态变化`; never claim event causation.
- Every color indicator must retain an adjacent text label.
- New controls must be keyboard accessible and expose stable accessible names.
- Implement with tests first and commit each independently reviewable increment.
- Run web commands from `apps/web`, API commands from `apps/api`, and repository checks from the worktree root unless a step states otherwise.

---

## File Map

- `apps/web/src/components/AuthIcons.tsx`: login/logout SVG glyphs only.
- `apps/web/src/App.tsx`: authenticated/anonymous header controls.
- `apps/web/src/App.test.tsx`: header accessibility and logout behavior.
- `apps/web/src/features/graph/GraphCanvas.tsx`: structured graph empty state.
- `apps/web/src/features/graph/GraphPage.tsx`: colored legend and graph deep-link loading.
- `apps/web/src/features/graph/GraphPage.test.tsx`: graph presentation and deep-link behavior.
- `apps/web/src/features/graph/entityTypeStyles.ts`: remains the single source of entity colors.
- `apps/web/src/features/story/StoryPage.tsx`: list/detail state, caching, retry, and navigation.
- `apps/web/src/features/story/StoryPage.test.tsx`: storyline interactions and failure states.
- `apps/web/src/api/client.ts`: timeline detail client types.
- `apps/web/src/styles/vercel.css`: header, graph, legend, and storyline presentation.
- `apps/api/src/app/graph/models.py`: typed timeline detail response models.
- `apps/api/src/app/graph/repository.py`: event context and participant fact query.
- `apps/api/src/app/graph/service.py`: temporal classification and label enrichment.
- `apps/api/src/app/graph/router.py`: event detail route.
- `apps/api/tests/graph/test_service.py`: temporal classification tests.
- `apps/api/tests/graph/test_router.py`: response and not-found API tests.

---

### Task 1: Accessible Header Authentication Icons

**Files:**
- Create: `apps/web/src/components/AuthIcons.tsx`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/styles/vercel.css`
- Test: `apps/web/src/App.test.tsx`

**Interfaces:**
- Produces: `LoginIcon(): JSX.Element` and `LogoutIcon(): JSX.Element`.
- Preserves: `/login` navigation and `auth.logout()` behavior.

- [x] **Step 1: Write failing header-control tests**

Add assertions to the anonymous and ready-session tests:

```tsx
const login = await screen.findByRole('link', { name: '管理员登录' })
expect(login).toHaveClass('auth-icon-control')
expect(login).toHaveAttribute('title', '管理员登录')
expect(login).not.toHaveTextContent('管理员登录')

const logout = await screen.findByRole('button', { name: '退出管理员登录' })
expect(logout).toHaveClass('auth-icon-control')
expect(logout).toHaveAttribute('title', '退出管理员登录')
expect(screen.queryByText('admin')).not.toBeInTheDocument()
```

In the ready-session test, make `logout` a spy and assert that clicking the icon calls it once.

- [x] **Step 2: Run the tests and confirm RED**

Run from `apps/web`:

```bash
npm test -- --run src/App.test.tsx
```

Expected: FAIL because the current controls contain visible text and have no `auth-icon-control` class or icon-only accessible label.

- [x] **Step 3: Add inline SVG icon components**

Create `AuthIcons.tsx`:

```tsx
export function LoginIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m10 17 5-5-5-5" /><path d="M15 12H3" /><path d="M13 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" /></svg>
}

export function LogoutIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m14 17-5-5 5-5" /><path d="M9 12h12" /><path d="M11 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6" /></svg>
}
```

- [x] **Step 4: Replace text controls and add fixed-size styling**

In `SiteHeader`, render:

```tsx
{auth.status === 'ready' ? <button className="auth-icon-control" type="button" aria-label="退出管理员登录" title="退出管理员登录" onClick={() => void auth.logout()}><LogoutIcon /></button> : auth.status === 'anonymous' ? <NavLink className="auth-icon-control" aria-label="管理员登录" title="管理员登录" to="/login"><LoginIcon /></NavLink> : null}
```

Add CSS:

```css
.auth-icon-control {
  width: 32px;
  height: 32px;
  display: inline-grid;
  place-items: center;
  flex: 0 0 32px;
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius);
  background: transparent;
  color: var(--ds-text-secondary);
  text-decoration: none;
}
.auth-icon-control:hover { background: var(--ds-background-hover); color: var(--ds-text-primary); }
.auth-icon-control svg { width: 18px; height: 18px; }
```

Remove obsolete `.account-menu` and `.login-link` text-control rules that no longer have consumers.

- [x] **Step 5: Run focused tests and commit**

```bash
npm test -- --run src/App.test.tsx
git add apps/web/src/components/AuthIcons.tsx apps/web/src/App.tsx apps/web/src/App.test.tsx apps/web/src/styles/vercel.css
git commit -m "feat: replace administrator text controls with icons"
```

Expected: App tests PASS.

---

### Task 2: Graph Legend and Empty-State Guidance

**Files:**
- Modify: `apps/web/src/features/graph/GraphCanvas.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.tsx`
- Modify: `apps/web/src/styles/vercel.css`
- Test: `apps/web/src/features/graph/GraphPage.test.tsx`

**Interfaces:**
- Consumes: `visibleEntityTypeStyles(nodes)` and each style's `label` and `color`.
- Produces: `.graph-legend-dot` with inline `--legend-color`, and `.canvas-empty-path` copy.

- [x] **Step 1: Write failing empty-state and legend marker tests**

Add one test for the untouched graph page:

```tsx
renderGraph()
expect(screen.getByRole('heading', { name: '从一个人物开始' })).toBeVisible()
expect(screen.getByText('搜索 → 选择实体 → 展开关系')).toBeVisible()
```

Extend the existing legend test:

```tsx
const personLegend = screen.getByTestId('legend-人物')
expect(personLegend).toHaveStyle('--legend-color: #4f46e5')
expect(personLegend).toHaveAccessibleName('人物')
```

- [x] **Step 2: Run graph tests and confirm RED**

```bash
npm test -- --run src/features/graph/GraphPage.test.tsx
```

Expected: FAIL because the current empty state has no heading/path structure and legend markers have no stable test/accessibility identity.

- [x] **Step 3: Implement the structured empty state**

Replace the empty canvas fragment with:

```tsx
<div className="canvas-empty" role="status">
  <span className="canvas-empty-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="7" cy="12" r="3" /><circle cx="18" cy="6" r="2" /><circle cx="18" cy="18" r="2" /><path d="m10 11 6-4M10 13l6 4" /></svg></span>
  <h2>从一个人物开始</h2>
  <p>在上方搜索并选择实体。图谱会先展开一度邻居，再由你决定是否继续探索。</p>
  <span className="canvas-empty-path">搜索 → 选择实体 → 展开关系</span>
</div>
```

- [x] **Step 4: Render explicit legend markers**

Change the footer mapping to:

```tsx
{visibleEntityTypeStyles(graph.nodes).map(type => <span className="graph-legend-item" key={type.label}><i className="graph-legend-dot" data-testid={`legend-${type.label}`} aria-label={type.label} style={{ '--legend-color': type.color } as CSSProperties} />{type.label}</span>)}
```

- [x] **Step 5: Add centered, responsive styling**

Add CSS that makes the marker visible and centers the empty state:

```css
.graph-canvas { position: relative; }
.canvas-empty { position: absolute; inset: 0; display: grid; place-content: center; justify-items: center; padding: 32px; text-align: center; }
.canvas-empty-icon { width: 48px; height: 48px; display: grid; place-items: center; margin-bottom: 16px; border-radius: 50%; background: var(--ds-background-recessed); }
.canvas-empty-icon svg { width: 24px; height: 24px; }
.canvas-empty h2 { margin: 0 0 8px; font-size: 18px; font-weight: 500; letter-spacing: -.3px; }
.canvas-empty p { max-width: 420px; margin: 0 0 16px; color: var(--ds-text-secondary); font-size: 13px; line-height: 1.6; }
.canvas-empty-path { padding: 5px 9px; border-radius: 999px; background: var(--ds-background-recessed); color: var(--ds-text-secondary); font: 11px Geist Mono, ui-monospace, monospace; }
.graph-legend-item { display: inline-flex; align-items: center; gap: 6px; }
.graph-legend-dot { width: 10px; height: 10px; display: inline-block; flex: 0 0 10px; border-radius: 50%; background: var(--legend-color); box-shadow: 0 0 0 1px rgb(0 0 0 / 8%); }
```

- [x] **Step 6: Run graph tests and commit**

```bash
npm test -- --run src/features/graph/GraphPage.test.tsx
git add apps/web/src/features/graph/GraphCanvas.tsx apps/web/src/features/graph/GraphPage.tsx apps/web/src/features/graph/GraphPage.test.tsx apps/web/src/features/graph/entityTypeStyles.ts apps/web/src/styles/vercel.css
git commit -m "feat: clarify graph legend and empty state"
```

Expected: GraphPage tests PASS.

---

### Task 3: Timeline Detail Models and Temporal Classification

**Files:**
- Modify: `apps/api/src/app/graph/models.py`
- Modify: `apps/api/src/app/graph/service.py`
- Test: `apps/api/tests/graph/test_service.py`

**Interfaces:**
- Consumes repository method: `timeline_detail(project_id: str, event_id: str) -> dict[str, Any] | None`.
- Produces service method: `GraphService.timeline_detail(project_id: str, event_id: str) -> TimelineEventDetail`.
- Produces response models: `TimelineRelationship`, `TimelineRelationshipStates`, `TimelineEventDetail`.

- [x] **Step 1: Write failing service classification tests**

Add a repository stub that returns chapter 10 with four facts:

```python
class TimelineDetailRepository:
    def timeline_detail(self, project_id: str, event_id: str):
        person = {"id": "linghu", "project_id": project_id, "type": "Person", "name": "令狐冲", "aliases": [], "description": ""}
        return {
            "event": {"id": event_id, "project_id": project_id, "type": "Event", "name": "思过崖传剑", "aliases": [], "description": ""},
            "chapter_number": 10,
            "participants": [person],
            "evidence": [{"id": "ev-1", "chapter_id": "c10", "chapter_number": 10, "chapter_title": "第十章", "start_offset": 1, "end_offset": 6, "quote": "风清扬传剑"}],
            "relationships": [
                {"id": "started", "type": "KNOWS", "source": person, "target": {"id": "dugu", "project_id": project_id, "type": "Swordplay", "name": "独孤九剑", "aliases": [], "description": ""}, "from_chapter": 10, "to_chapter": None},
                {"id": "active", "type": "MEMBER_OF", "source": person, "target": {"id": "huashan", "project_id": project_id, "type": "Sect", "name": "华山派", "aliases": [], "description": ""}, "from_chapter": 1, "to_chapter": 20},
                {"id": "ended", "type": "HOLDS", "source": person, "target": {"id": "qin", "project_id": project_id, "type": "Artifact", "name": "短琴", "aliases": [], "description": ""}, "from_chapter": 2, "to_chapter": 10},
                {"id": "timeless", "type": "MASTER_OF", "source": {"id": "feng", "project_id": project_id, "type": "Person", "name": "风清扬", "aliases": [], "description": ""}, "target": person, "from_chapter": None, "to_chapter": None},
            ],
        }
```

Assert IDs by group, relation labels, and evidence deduplication:

```python
detail = GraphService(TimelineDetailRepository()).timeline_detail("p-1", "event-1")
assert [item.id for item in detail.relationship_states.started] == ["started"]
assert [item.id for item in detail.relationship_states.active] == ["active", "timeless"]
assert [item.id for item in detail.relationship_states.ended] == ["ended"]
assert detail.relationship_states.started[0].label == "掌握"
assert detail.evidence[0].quote == "风清扬传剑"
```

Add tests for a fact with `from_chapter == to_chapter == 10` being in `started`, duplicate fact IDs appearing once, and `None` raising `EntityNotFoundError`.
Add a chapterless event fixture and assert all three relationship-state lists are empty while participants and evidence remain available.

- [x] **Step 2: Run service tests and confirm RED**

Run from `apps/api`:

```bash
python -m pytest tests/graph/test_service.py -q
```

Expected: FAIL because timeline detail models and service method do not exist.

- [x] **Step 3: Add typed response models**

Add:

```python
class TimelineRelationship(BaseModel):
    id: str
    type: str
    label: str
    source: EntitySummary
    target: EntitySummary
    from_chapter: int | None = None
    to_chapter: int | None = None


class TimelineRelationshipStates(BaseModel):
    started: list[TimelineRelationship] = Field(default_factory=list)
    active: list[TimelineRelationship] = Field(default_factory=list)
    ended: list[TimelineRelationship] = Field(default_factory=list)


class TimelineEventDetail(BaseModel):
    event: EntitySummary
    chapter_number: int | None = None
    participants: list[EntitySummary] = Field(default_factory=list)
    evidence: list[EvidenceDetail] = Field(default_factory=list)
    relationship_states: TimelineRelationshipStates
```

- [x] **Step 4: Implement deterministic classification in `GraphService`**

Add `_timeline_relationship` to enrich labels via `relation_by_id`, deduplicate by fact ID, and classify with this precedence:

```python
if chapter_number is None:
    return TimelineRelationshipStates()

if from_chapter == chapter_number:
    bucket = started
elif to_chapter == chapter_number:
    bucket = ended
elif (from_chapter is None or from_chapter < chapter_number) and (to_chapter is None or to_chapter > chapter_number):
    bucket = active
else:
    continue
```

Return `TimelineEventDetail` with deduplicated participants and evidence, preserving repository order inside each group.
When `chapter_number` is `None`, do not infer temporal state: return empty `started`, `active`, and `ended` lists while preserving the event, participants, and evidence.

- [x] **Step 5: Run service tests and commit**

```bash
python -m pytest tests/graph/test_service.py -q
git add apps/api/src/app/graph/models.py apps/api/src/app/graph/service.py apps/api/tests/graph/test_service.py
git commit -m "feat: classify storyline relationship states"
```

Expected: graph service tests PASS.

---

### Task 4: Neo4j Timeline Detail Query and API Route

**Files:**
- Modify: `apps/api/src/app/graph/repository.py`
- Modify: `apps/api/src/app/graph/router.py`
- Test: `apps/api/tests/graph/test_service.py`
- Test: `apps/api/tests/graph/test_router.py`

**Interfaces:**
- Produces repository method: `Neo4jGraphRepository.timeline_detail(project_id, event_id)` returning `event`, `chapter_number`, `participants`, `evidence`, and `relationships`.
- Exposes: `GET /api/graph/timeline/{event_id}?project_id=...` with `TimelineEventDetail` response model.

- [x] **Step 1: Write failing repository and router tests**

Repository query assertions must require:

```python
assert "event.type IN ['Event', 'TeachingEvent']" in session.statement
assert "participant.type = 'Person'" in session.statement
assert "coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'" in session.statement
assert session.parameters == {"project_id": "p-1", "event_id": "event-1"}
```

Add a router repository stub returning the raw detail shape from Task 3, call `/api/graph/timeline/event-1`, and assert status 200 plus `relationship_states.started[0].label == "掌握"`. Add a stub returning `None` and assert status 404 with `ENTITY_NOT_FOUND`.

- [x] **Step 2: Run focused API tests and confirm RED**

```bash
python -m pytest tests/graph/test_service.py tests/graph/test_router.py -q
```

Expected: FAIL because the repository method and route do not exist.

- [x] **Step 3: Implement one bounded Neo4j detail query**

Add the same `timeline_detail` signature to `GraphRepository`, then implement it in `Neo4jGraphRepository` with one bounded query:

```python
def timeline_detail(self, project_id: str, event_id: str) -> dict[str, Any] | None:
    statement = """
        MATCH (event:Entity {project_id: $project_id, id: $event_id})
        WHERE event.type IN ['Event', 'TeachingEvent']
          AND coalesce(event.review_status, 'ACCEPTED') <> 'MERGED'
        CALL {
            WITH event
            OPTIONAL MATCH (event)-[event_edge:RELATED]-(participant:Entity {project_id: $project_id})
            WHERE participant.type = 'Person'
              AND coalesce(participant.review_status, 'ACCEPTED') <> 'MERGED'
              AND coalesce(event_edge.review_status, 'ACCEPTED') <> 'REJECTED'
            RETURN min(event_edge.from_chapter) AS chapter_number,
                [item IN collect(DISTINCT participant) WHERE item IS NOT NULL | properties(item)] AS participants
        }
        CALL {
            WITH event
            OPTIONAL MATCH (event_fact:Fact {project_id: $project_id})-[:SOURCE|TARGET]->(event)
            WHERE coalesce(event_fact.review_status, 'ACCEPTED') <> 'REJECTED'
            OPTIONAL MATCH (event_fact)-[:EVIDENCED_BY]->(event_evidence:Evidence)
                -[:IN_CHAPTER]->(event_chapter:Chapter)
            WITH collect(DISTINCT {
                id: event_evidence.id,
                chapter_id: event_chapter.id,
                chapter_number: event_chapter.number,
                chapter_title: event_chapter.title,
                start_offset: event_evidence.start_offset,
                end_offset: event_evidence.end_offset,
                quote: event_evidence.quote
            }) AS evidence_rows
            RETURN [item IN evidence_rows WHERE item.id IS NOT NULL] AS evidence
        }
        CALL {
            WITH event
            OPTIONAL MATCH (event)-[:RELATED]-(participant:Entity {project_id: $project_id})
            WHERE participant.type = 'Person'
              AND coalesce(participant.review_status, 'ACCEPTED') <> 'MERGED'
            WITH event, collect(DISTINCT participant.id) AS participant_ids
            OPTIONAL MATCH (fact:Fact {project_id: $project_id})-[:SOURCE]->(source:Entity {project_id: $project_id})
            OPTIONAL MATCH (fact)-[:TARGET]->(target:Entity {project_id: $project_id})
            WHERE coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'
              AND coalesce(source.review_status, 'ACCEPTED') <> 'MERGED'
              AND coalesce(target.review_status, 'ACCEPTED') <> 'MERGED'
              AND (source.id IN participant_ids OR target.id IN participant_ids)
              AND source.id <> event.id AND target.id <> event.id
            WITH collect(DISTINCT {
                id: fact.id,
                type: fact.type,
                source: properties(source),
                target: properties(target),
                from_chapter: fact.from_chapter,
                to_chapter: fact.to_chapter
            }) AS relationship_rows
            RETURN [item IN relationship_rows WHERE item.id IS NOT NULL] AS relationships
        }
        RETURN properties(event) AS event, chapter_number, participants, evidence, relationships
    """
    with self.driver.session() as session:
        record = session.run(statement, project_id=project_id, event_id=event_id).single()
        if record is None:
            return None
        return {
            "event": dict(record["event"]),
            "chapter_number": record["chapter_number"],
            "participants": [dict(item) for item in record["participants"]],
            "evidence": [dict(item) for item in record["evidence"] if item.get("id")],
            "relationships": [dict(item) for item in record["relationships"] if item.get("id")],
        }
```

The query matches only project-scoped accepted entities/facts, excludes the selected event's own participant edges from relationship state groups, and returns `None` for a missing event.

The repository return shape is:

```python
return {
    "event": dict(record["event"]),
    "chapter_number": record["chapter_number"],
    "participants": [dict(item) for item in record["participants"]],
    "evidence": [dict(item) for item in record["evidence"] if item.get("id")],
    "relationships": [dict(item) for item in record["relationships"] if item.get("id")],
}
```

Return `None` when the event match produces no record.

- [x] **Step 4: Add the route after the timeline list route**

```python
@router.get("/api/graph/timeline/{event_id}", response_model=TimelineEventDetail)
def timeline_detail(repository: Repository, event_id: str, project_id: str) -> TimelineEventDetail:
    return execute(lambda: GraphService(repository).timeline_detail(project_id, event_id))
```

- [x] **Step 5: Run graph API tests and commit**

```bash
python -m pytest tests/graph/test_service.py tests/graph/test_router.py -q
git add apps/api/src/app/graph/repository.py apps/api/src/app/graph/router.py apps/api/tests/graph/test_service.py apps/api/tests/graph/test_router.py
git commit -m "feat: expose storyline event detail"
```

Expected: focused graph tests PASS.

---

### Task 5: Expandable Storyline Event Experience

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/features/story/StoryPage.tsx`
- Modify: `apps/web/src/features/story/StoryPage.test.tsx`
- Modify: `apps/web/src/styles/vercel.css`

**Interfaces:**
- Consumes: `GET /api/graph/timeline/{event_id}?project_id=...`.
- Produces client types: `TimelineRelationship`, `TimelineEventDetail`.
- Produces event buttons with `aria-expanded`, cache keyed by event ID, and retryable inline errors.

- [x] **Step 1: Write failing interaction tests**

Cover these outcomes with mocked fetch responses:

```tsx
await user.click(await screen.findByRole('button', { name: /思過崖傳劍/ }))
expect(await screen.findByRole('heading', { name: '新增关系' })).toBeVisible()
expect(screen.getByText(/令狐冲.*掌握.*独孤九剑/)).toBeVisible()
expect(screen.getByText('本章无结束关系')).toBeVisible()
expect(screen.getByText('风清扬传剑')).toBeVisible()
expect(screen.getByRole('button', { name: /思過崖傳劍/ })).toHaveAttribute('aria-expanded', 'true')
```

Also test:

- opening a second event collapses the first;
- collapsing and reopening uses one detail request;
- a 503 response renders `详情加载失败` and `重试`;
- clicking retry performs another request and shows detail;
- changing person clears the expanded detail.

- [x] **Step 2: Run StoryPage tests and confirm RED**

```bash
npm test -- --run src/features/story/StoryPage.test.tsx
```

Expected: FAIL because cards are not interactive and no detail endpoint is called.

- [x] **Step 3: Add client timeline types**

```ts
export type TimelineRelationship = {
  id: string
  type: string
  label: string
  source: EntitySummary
  target: EntitySummary
  from_chapter?: number
  to_chapter?: number
}

export type TimelineEventDetail = {
  event: EntitySummary
  chapter_number?: number
  participants: EntitySummary[]
  evidence: Evidence[]
  relationship_states: { started: TimelineRelationship[]; active: TimelineRelationship[]; ended: TimelineRelationship[] }
}

export function getTimelineDetail(projectId: string, eventId: string, signal?: AbortSignal) {
  return apiFetch<TimelineEventDetail>(
    `/api/graph/timeline/${encodeURIComponent(eventId)}?project_id=${encodeURIComponent(projectId)}`,
    { signal },
  )
}
```

- [x] **Step 4: Implement selected-event state, cache, and stale-request protection**

Use:

```tsx
const [expandedId, setExpandedId] = useState<string>()
const [details, setDetails] = useState<Record<string, TimelineEventDetail>>({})
const [detailLoading, setDetailLoading] = useState<string>()
const [detailErrors, setDetailErrors] = useState<Record<string, string>>({})
const detailRequest = useRef<AbortController>()
```

`toggleEvent(eventId)` collapses the selected ID, reuses `details[eventId]`, or requests the detail. Abort the previous request before a new one. Reset expanded ID/cache when project changes; reset only expanded ID when person changes.

Implement the state transition explicitly:

```tsx
async function toggleEvent(eventId: string, forceReload = false) {
  if (!forceReload && expandedId === eventId) {
    setExpandedId(undefined)
    return
  }
  setExpandedId(eventId)
  if (!forceReload && details[eventId]) return

  detailRequest.current?.abort()
  const controller = new AbortController()
  detailRequest.current = controller
  setDetailLoading(eventId)
  setDetailErrors((current) => ({ ...current, [eventId]: '' }))
  try {
    const detail = await getTimelineDetail(projectId, eventId, controller.signal)
    if (!controller.signal.aborted) {
      setDetails((current) => ({ ...current, [eventId]: detail }))
    }
  } catch (error) {
    if (!controller.signal.aborted) {
      setDetailErrors((current) => ({ ...current, [eventId]: toErrorMessage(error) }))
    }
  } finally {
    if (!controller.signal.aborted) setDetailLoading(undefined)
  }
}
```

- [x] **Step 5: Render accessible cards and relationship groups**

The trigger must be a native button with `aria-expanded` and `aria-controls`. Extract a focused `RelationshipStateGroup` inside `StoryPage.tsx` that receives `title`, `tone`, `items`, and `emptyText`. Render source name, localized label, target name, and optional chapter range. Render event evidence in blockquotes with chapter metadata.

Use a small presentational component so all three columns share identical semantics:

```tsx
function RelationshipStateGroup({ title, tone, items, emptyText }: RelationshipStateGroupProps) {
  return (
    <section className="timeline-state-card" aria-label={title}>
      <h3><span className={`timeline-state-dot is-${tone}`} aria-hidden="true" />{title}</h3>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <span>{item.source.name}</span>
              <span aria-label="关系"> {item.label} </span>
              <span>{item.target.name}</span>
            </li>
          ))}
        </ul>
      ) : <p className="timeline-state-empty">{emptyText}</p>}
    </section>
  )
}
```

If `detail.chapter_number` is absent, replace the three-column grid with `该事件缺少章节信息，暂不推断关系状态。` and continue showing participants and evidence.

Add the event layout styles:

```css
.timeline-event { overflow: hidden; border-radius: var(--ds-radius-card); background: var(--ds-background-elevated); box-shadow: var(--ds-shadow-small); }
.timeline-event-trigger { width: 100%; min-height: 72px; display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 16px; padding: 16px 20px; border: 0; background: transparent; color: var(--ds-text-primary); text-align: left; }
.timeline-event-trigger:hover { background: var(--ds-background-primary); }
.timeline-event-detail { padding: 20px; box-shadow: 0 -1px 0 rgb(0 0 0 / 8%); }
.timeline-participants { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.timeline-participants span { padding: 5px 9px; border-radius: 999px; background: var(--ds-background-recessed); color: var(--ds-text-secondary); font-size: 12px; }
.timeline-state-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.timeline-state-card { min-width: 0; padding: 14px; border-radius: var(--ds-radius); background: var(--ds-background-primary); box-shadow: var(--ds-shadow-border); }
.timeline-state-card h3 { display: flex; align-items: center; gap: 7px; margin: 0 0 10px; font-size: 13px; font-weight: 500; }
.timeline-state-card ul { margin: 0; padding: 0; list-style: none; }
.timeline-state-card li + li { margin-top: 8px; }
.timeline-state-dot { width: 8px; height: 8px; border-radius: 50%; }
.timeline-detail-error { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #b42318; }
@media (max-width: 760px) { .timeline-state-grid { grid-template-columns: 1fr; } }
```

- [x] **Step 6: Run StoryPage tests and commit**

```bash
npm test -- --run src/features/story/StoryPage.test.tsx
git add apps/web/src/api/client.ts apps/web/src/features/story/StoryPage.tsx apps/web/src/features/story/StoryPage.test.tsx apps/web/src/styles/vercel.css
git commit -m "feat: expand storyline events with temporal context"
```

Expected: StoryPage tests PASS.

---

### Task 6: Storyline-to-Graph Deep Linking

**Files:**
- Modify: `apps/web/src/features/story/StoryPage.tsx`
- Modify: `apps/web/src/features/story/StoryPage.test.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.test.tsx`

**Interfaces:**
- Produces URL: `/graph?project={projectId}&entity={eventId}`.
- Consumes optional graph search parameter: `entity`.
- Uses existing `/api/entities/{entity_id}` and `/api/graph/neighborhood` calls.

- [x] **Step 1: Write failing navigation and hydration tests**

In StoryPage tests, wrap with `MemoryRouter`, expand an event, click `在图谱中查看`, and assert pathname `/graph` plus both `project` and `entity` parameters.

In GraphPage tests, render:

```tsx
<MemoryRouter initialEntries={['/graph?project=xiaoao&entity=teaching']}>
  <AuthContext.Provider value={readyAuth}><GraphPage /></AuthContext.Provider>
</MemoryRouter>
```

Mock entity detail and neighborhood endpoints, then assert the event name and neighbor appear without typing in search.

- [x] **Step 2: Run both focused suites and confirm RED**

```bash
npm test -- --run src/features/story/StoryPage.test.tsx src/features/graph/GraphPage.test.tsx
```

Expected: FAIL because no navigation action or entity query hydration exists.

- [x] **Step 3: Add the storyline graph link**

Use `useNavigate` and navigate with:

```tsx
navigate({ pathname: '/graph', search: `?project=${encodeURIComponent(projectId)}&entity=${encodeURIComponent(detail.event.id)}` })
```

- [x] **Step 4: Hydrate GraphPage from the entity parameter**

Use `useSearchParams` to read `entity`. On project/entity change, fetch the entity detail first and pass it to the existing `selectEntity` path (`EntityDetail` structurally extends `EntitySummary`). Track the last hydrated `projectId:entityId` in a ref so state updates do not issue duplicate requests. Abort the initial entity-detail fetch on unmount/project change; `selectEntity` continues to own and abort its neighborhood/detail requests. If hydration returns 404, retain the empty canvas and show a non-blocking alert.

Implement the lifecycle with a keyed ref and cleanup:

```tsx
useEffect(() => {
  if (!projectId || !entityId) return
  const hydrationKey = `${projectId}:${entityId}`
  if (hydratedEntity.current === hydrationKey) return
  hydratedEntity.current = hydrationKey
  const controller = new AbortController()

  void apiFetch<EntityDetail>(
    `/api/entities/${encodeURIComponent(entityId)}?project_id=${encodeURIComponent(projectId)}`,
    { signal: controller.signal },
  )
    .then((entity) => selectEntity(entity))
    .catch((error) => {
      if (!controller.signal.aborted) setError(toErrorMessage(error))
    })

  return () => controller.abort()
}, [entityId, projectId, selectEntity])
```

- [x] **Step 5: Run focused tests and commit**

```bash
npm test -- --run src/features/story/StoryPage.test.tsx src/features/graph/GraphPage.test.tsx
git add apps/web/src/features/story/StoryPage.tsx apps/web/src/features/story/StoryPage.test.tsx apps/web/src/features/graph/GraphPage.tsx apps/web/src/features/graph/GraphPage.test.tsx
git commit -m "feat: link storyline events to graph neighborhoods"
```

Expected: StoryPage and GraphPage tests PASS.

---

### Task 7: Full Verification and Browser Review

**Files:**
- Modify only files required by failures discovered during verification.
- Update plan checkboxes as each verification step passes.

**Interfaces:**
- Verifies all public behavior introduced by Tasks 1–6.

- [x] **Step 1: Run the complete API suite**

From `apps/api`:

```bash
python -m pytest -q
```

Expected: all API tests PASS.

- [x] **Step 2: Run the complete web suite, type check, and build**

From `apps/web`:

```bash
npm test -- --run
npm run typecheck
npm run build
```

Expected: all web tests PASS, TypeScript exits 0, and Vite creates `dist/`.

- [x] **Step 3: Run repository-level configuration checks**

From the repository root:

```bash
git diff --check origin/master...HEAD
docker compose config --quiet
```

Expected: both commands exit 0.

- [x] **Step 4: Verify in a real browser at desktop width**

At 1440px width verify:

- anonymous login and authenticated logout controls are compact icon buttons with tooltips and focus rings;
- graph empty guidance is centered;
- a searched graph shows colored legend dots matching nodes;
- opening one storyline event closes another;
- started, active, and ended groups match API data;
- retry recovers from a simulated failed detail request;
- `在图谱中查看` loads the event neighborhood;
- browser console contains no errors.

- [x] **Step 5: Verify narrow layout and keyboard access**

At 390px width verify:

- header controls do not overlap the project selector or navigation;
- legend wraps without clipping;
- empty guidance remains centered;
- storyline state groups stack to one column;
- Tab, Enter, and Space operate icon and event controls in logical order.

- [x] **Step 6: Review final diff and commit verification fixes**

```bash
git status --short
git diff --stat origin/master...HEAD
git diff --check origin/master...HEAD
```

If verification required changes, stage only those files and commit:

```bash
git commit -m "fix: polish responsive storyline interactions"
```

If no files changed, do not create an empty commit.
