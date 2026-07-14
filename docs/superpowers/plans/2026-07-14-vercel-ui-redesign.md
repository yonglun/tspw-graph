# 江湖图谱 Vercel 风格前端重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有业务、API 与路由的前提下，把全站重构为灰阶、精确、可访问的 Vercel 风格界面。

**Architecture:** 保留现有 React 页面组件与数据获取逻辑，用新的 `vercel.css` 设计系统层替换 `swiss.css`，并对导航、图谱实体详情和状态展示做少量语义化结构调整。实施按基础系统、阅读页面、图谱工作台、业务工作台和全站回归五个可独立验证的增量推进。

**Tech Stack:** React 19、TypeScript 5、React Router 7、Cytoscape、CSS Custom Properties、Vitest、Testing Library、Vite。

## Global Constraints

- 页面背景 `#FAFAFA`，提升表面 `#FFFFFF`，凹陷表面 `#F2F2F2`。
- 主文字 `#171717`，次文字 `#4D4D4D`，弱文字 `#8F8F8F`。
- `#0072F5` 是唯一交互强调色；其他颜色仅用于 8–10px 实体类别或状态点。
- 界面字重只允许 400、500、600；不得出现 700 或 800。
- 所有间距使用 4px 基准令牌。
- 容器视觉边界使用 shadow-as-border；不使用 CSS 实线边框作为容器边界。
- 不使用背景渐变、网格、纹理、装饰印章或大面积状态色。
- 不引入新的运行时依赖。
- 现有 API、路由、项目参数、构建流程、图谱交互和审核动作保持兼容。
- 关键视口为 320、768、1024、1440px。

---

## File Map

- Create: `apps/web/src/styles/vercel.css` — 全站设计令牌、基础控件、页面布局和响应式规则。
- Delete: `apps/web/src/styles/swiss.css` — 移除上一版红黄瑞士风覆盖层。
- Modify: `apps/web/src/App.tsx` — 引入新样式并语义化品牌结构。
- Modify: `apps/web/src/App.test.tsx` — 验证全局导航、品牌和项目参数保持。
- Modify: `apps/web/src/features/guide/GuidePage.tsx` — 移除装饰印章并语义化三元组示例。
- Modify: `apps/web/src/features/guide/GuidePage.test.tsx` — 验证导览三元组结构。
- Modify: `apps/web/src/features/ontology/OntologyPage.tsx` — 增加小型类别点和属性区域关联语义。
- Modify: `apps/web/src/features/ontology/OntologyPage.test.tsx` — 验证属性展开和类别标记。
- Modify: `apps/web/src/features/graph/GraphCanvas.tsx` — 将图节点改为小型类别点，选中状态改为交互蓝。
- Modify: `apps/web/src/features/graph/EntityPanel.tsx` — 用原生按钮承载属性与关系选择。
- Modify: `apps/web/src/features/graph/GraphPage.test.tsx` — 验证键盘选择和证据定位。
- Create: `apps/web/src/components/StatusDot.tsx` — 统一带文字的状态指示点。
- Create: `apps/web/src/components/StatusDot.test.tsx` — 验证状态点不只依赖颜色。
- Modify: `apps/web/src/features/build/JobProgress.tsx` — 使用统一状态点展示任务状态。
- Modify: `apps/web/src/features/review/ReviewDetail.tsx` — 使用统一状态点展示严重度。
- Modify: `apps/web/src/features/review/ReviewPage.test.tsx` — 验证审核状态与可读详情。
- Modify: `apps/web/src/styles/theme.css` — 仅删除被新设计系统确认取代的旧全局动画和冲突规则。

---

### Task 1: 建立 Vercel 设计系统与全局导航

**Files:**
- Create: `apps/web/src/styles/vercel.css`
- Delete: `apps/web/src/styles/swiss.css`
- Modify: `apps/web/src/App.tsx`
- Modify: `apps/web/src/App.test.tsx`

**Interfaces:**
- Consumes: 现有 `SiteHeader`、`ProjectSwitcher`、React Router `NavLink`。
- Produces: `vercel.css` 的全局令牌与共享类；后续页面任务只使用这些令牌和类。

- [ ] **Step 1: 为品牌和导航语义编写失败测试**

在 `apps/web/src/App.test.tsx` 新增：

```tsx
it('renders the monochrome product header with primary navigation', () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify([]))))
  render(<App />)

  const header = screen.getByRole('banner')
  expect(header).toHaveClass('site-header')
  expect(screen.getByRole('link', { name: '江湖图谱' })).toHaveClass('brand')
  expect(screen.getByRole('navigation', { name: '主导航' })).toBeVisible()
  expect(screen.getByLabelText('当前项目')).toBeVisible()
})
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd apps/web && npm test -- --run src/App.test.tsx`

Expected: FAIL，因为品牌链接当前缺少精确的 `aria-label="江湖图谱"` 和新的内部结构。

- [ ] **Step 3: 更新品牌结构和样式入口**

将 `apps/web/src/App.tsx` 的样式导入和品牌改为：

```tsx
import './styles/theme.css'
import './styles/vercel.css'

function SiteHeader() {
  const { projectId } = useProject()
  return (
    <header className="site-header">
      <NavLink aria-label="江湖图谱" className="brand" to={projectPath('/guide', projectId)}>
        <span className="brand-mark" aria-hidden="true">江</span>
        <span className="brand-name">江湖图谱</span>
      </NavLink>
      <nav aria-label="主导航">
        {links.map(([path, label]) => (
          <NavLink key={path} to={projectPath(path, projectId)}>{label}</NavLink>
        ))}
      </nav>
      <ProjectSwitcher />
    </header>
  )
}
```

删除 `apps/web/src/styles/swiss.css`，创建 `apps/web/src/styles/vercel.css`，以以下完整令牌和基础规则开头：

```css
:root {
  --ds-background-primary: #fafafa;
  --ds-background-elevated: #fff;
  --ds-background-recessed: #f2f2f2;
  --ds-background-hover: #ebebeb;
  --ds-text-primary: #171717;
  --ds-text-secondary: #4d4d4d;
  --ds-text-muted: #8f8f8f;
  --ds-interactive: #0072f5;
  --ds-focus: #005fcc;
  --ds-shadow-border: 0 0 0 1px rgb(0 0 0 / 8%);
  --ds-shadow-small: var(--ds-shadow-border), 0 2px 2px rgb(0 0 0 / 4%);
  --ds-shadow-menu: var(--ds-shadow-border), 0 1px 1px rgb(0 0 0 / 2%), 0 4px 8px -4px rgb(0 0 0 / 4%), 0 16px 24px -8px rgb(0 0 0 / 6%);
  --ds-focus-ring: 0 0 0 2px #fff, 0 0 0 4px var(--ds-interactive);
  --ds-radius: 6px;
  --ds-radius-card: 12px;
  --ds-page-width: 1200px;
  --ds-workspace-width: 1400px;
  --ds-header-height: 64px;
  font-family: Geist Sans, Inter, "Helvetica Neue", Arial, "PingFang SC", sans-serif;
  color: var(--ds-text-primary);
  background: var(--ds-background-primary);
}

body { margin: 0; min-width: 320px; background: var(--ds-background-primary); color: var(--ds-text-primary); font-weight: 400; }
button, input, select { font: inherit; }
button, a { transition: color .15s, background-color .15s, box-shadow .15s; }
button:focus-visible, a:focus-visible, [role="button"]:focus-visible { outline: 0; box-shadow: var(--ds-focus-ring); }
input:focus-visible, select:focus-visible { outline: 1px auto var(--ds-focus); outline-offset: 1px; }
.site-header { min-height: var(--ds-header-height); background: var(--ds-background-primary); box-shadow: 0 1px 0 rgb(0 0 0 / 10%); }
.brand { color: var(--ds-text-primary); font-size: 14px; font-weight: 500; text-decoration: none; }
.brand-mark { display: inline-grid; width: 24px; height: 24px; place-items: center; color: var(--ds-text-primary); }
.brand-name { white-space: nowrap; }
.site-header nav a { color: var(--ds-text-secondary); font-size: 14px; font-weight: 400; border-radius: var(--ds-radius); }
.site-header nav a:hover, .site-header nav a.active { color: var(--ds-text-primary); background: var(--ds-background-hover); }
```

- [ ] **Step 4: 运行导航测试、类型检查和生产构建**

Run: `cd apps/web && npm test -- --run src/App.test.tsx && npm run typecheck && npm run build`

Expected: App tests PASS；TypeScript exits 0；Vite 输出 `built in`。

- [ ] **Step 5: 提交基础系统**

```bash
git add apps/web/src/App.tsx apps/web/src/App.test.tsx apps/web/src/styles/vercel.css apps/web/src/styles/swiss.css
git commit -m "feat: establish vercel frontend design system"
```

---

### Task 2: 重构导览、本体与故事线阅读页面

**Files:**
- Modify: `apps/web/src/features/guide/GuidePage.tsx`
- Modify: `apps/web/src/features/guide/GuidePage.test.tsx`
- Modify: `apps/web/src/features/ontology/OntologyPage.tsx`
- Modify: `apps/web/src/features/ontology/OntologyPage.test.tsx`
- Modify: `apps/web/src/styles/vercel.css`

**Interfaces:**
- Consumes: Task 1 的 `--ds-*` 令牌、`.page`、`.page-header`、基础按钮和焦点规则。
- Produces: `.content-page`、`.triple-card`、`.entity-type-dot`、`.ontology-grid`、`.timeline` 页面规则。

- [ ] **Step 1: 编写导览和本体失败测试**

在 `GuidePage.test.tsx` 增加：

```tsx
expect(screen.getByRole('group', { name: '知识三元组示例' })).toHaveTextContent('令狐冲掌握独孤九剑')
expect(screen.queryByText('知')).not.toBeInTheDocument()
```

在 `OntologyPage.test.tsx` 的属性展开断言后增加：

```tsx
const personCard = screen.getByRole('article', { name: /人物/ })
expect(within(personCard).getByTestId('entity-type-dot')).toBeVisible()
expect(screen.getByRole('button', { name: /收起属性/ })).toHaveAttribute('aria-expanded', 'true')
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd apps/web && npm test -- --run src/features/guide/GuidePage.test.tsx src/features/ontology/OntologyPage.test.tsx`

Expected: FAIL，因为三元组尚无 `group` 语义，本体卡片没有类别点和 article 标签。

- [ ] **Step 3: 调整导览和本体结构**

将导览示例改为：

```tsx
<div className="triple-card" role="group" aria-label="知识三元组示例">
  <div className="triple-node subject"><small>人物</small><strong>令狐冲</strong></div>
  <div className="relation"><span>掌握</span><i aria-hidden="true" /></div>
  <div className="triple-node object"><small>剑法</small><strong>独孤九剑</strong></div>
  <p>主体 — 关系 — 客体，构成一条可查询事实。</p>
</div>
```

将本体类型卡片根元素与按钮开头改为：

```tsx
<article className={`type-card${expanded ? ' is-expanded' : ''}`} key={type.id} aria-label={`${type.label} ${type.id}`}>
  <button type="button" className="type-card-toggle" aria-expanded={expanded} aria-controls={`type-properties-${type.id}`} onClick={() => setExpandedTypeId(expanded ? undefined : type.id)}>
    <i className="entity-type-dot" data-testid="entity-type-dot" style={{ '--type-color': type.color } as React.CSSProperties} aria-hidden="true" />
```

属性容器使用：

```tsx
<div className="type-properties" id={`type-properties-${type.id}`}>
```

- [ ] **Step 4: 完成阅读页面样式**

在 `vercel.css` 增加以下规则，并确保所有值来自 Task 1 令牌或 4px 间距：

```css
.page { width: min(var(--ds-page-width), calc(100% - 48px)); margin: 0 auto; padding: 64px 0 96px; }
.page-header { display: flex; align-items: end; justify-content: space-between; gap: 32px; margin-bottom: 48px; }
.page-header h1 { margin: 0; font-size: clamp(40px, 5vw, 48px); line-height: 1; font-weight: 600; letter-spacing: -2.28px; }
.eyebrow { margin: 0 0 12px; color: var(--ds-text-secondary); font-size: 12px; line-height: 16px; font-weight: 500; letter-spacing: 0; text-transform: uppercase; }
.guide-page { width: min(var(--ds-page-width), calc(100% - 48px)); margin: 0 auto; padding: 64px 0 96px; }
.triple-card, .abox { background: var(--ds-background-elevated); border-radius: var(--ds-radius-card); box-shadow: var(--ds-shadow-small); }
.triple-node { padding: 16px; background: var(--ds-background-elevated); border-radius: var(--ds-radius); box-shadow: var(--ds-shadow-border); }
.ontology-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; }
.type-card { min-width: 0; background: var(--ds-background-elevated); border-radius: var(--ds-radius-card); box-shadow: var(--ds-shadow-border); overflow: hidden; }
.type-card-toggle { width: 100%; padding: 24px; border: 0; background: transparent; text-align: left; }
.entity-type-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: var(--type-color, var(--ds-text-muted)); }
.type-properties { padding: 0 24px 24px; }
.timeline { border: 0; }
.timeline article { padding: 24px; background: var(--ds-background-elevated); border-radius: var(--ds-radius-card); box-shadow: var(--ds-shadow-border); }
```

- [ ] **Step 5: 运行页面测试并提交**

Run: `cd apps/web && npm test -- --run src/features/guide/GuidePage.test.tsx src/features/ontology/OntologyPage.test.tsx src/features/story/StoryPage.test.tsx`

Expected: 3 test files PASS。

```bash
git add apps/web/src/features/guide apps/web/src/features/ontology apps/web/src/styles/vercel.css
git commit -m "feat: redesign knowledge learning pages"
```

---

### Task 3: 重构图谱画布与实体详情交互

**Files:**
- Modify: `apps/web/src/features/graph/GraphCanvas.tsx`
- Modify: `apps/web/src/features/graph/EntityPanel.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.test.tsx`
- Modify: `apps/web/src/styles/vercel.css`

**Interfaces:**
- Consumes: `Neighborhood`、`EntityDetail`、`getEntityTypeStyle(type)`、现有证据选择回调。
- Produces: 原生按钮形式的属性与关系选择；灰阶画布和小型类别节点。

- [ ] **Step 1: 编写键盘交互失败测试**

在 `GraphPage.test.tsx` 的关系证据测试中，在点击断言后增加：

```tsx
const relationButton = await screen.findByRole('button', { name: /师父.*岳不群/ })
relationButton.focus()
await user.keyboard(' ')
expect(await screen.findByText('关系原文证据')).toBeVisible()

const attributeButton = screen.getByRole('button', { name: /身份.*华山派大弟子/ })
attributeButton.focus()
await user.keyboard('{Enter}')
expect(screen.getAllByText('华山派大弟子').length).toBeGreaterThanOrEqual(1)
```

- [ ] **Step 2: 运行目标测试并确认失败**

Run: `cd apps/web && npm test -- --run src/features/graph/GraphPage.test.tsx -t "loads relation evidence"`

Expected: FAIL，因为属性和关系当前不是原生按钮，且可访问名称不稳定。

- [ ] **Step 3: 将属性与关系行改为原生按钮**

属性列表改为：

```tsx
<dl className="attribute-list">
  {groupedAttributes.map(group => (
    <div key={group.label} className={group.ids.includes(selectedAttributeId ?? '') ? 'is-selected' : ''}>
      <dt>{group.label}</dt>
      <dd>
        <button type="button" aria-label={`${group.label} ${group.values.join('、')}`} aria-pressed={group.ids.includes(selectedAttributeId ?? '')} onClick={() => onSelectAttribute?.(group.ids[0])}>
          {group.values.join('、')}
        </button>
      </dd>
    </div>
  ))}
</dl>
```

关系列表改为：

```tsx
<ul className="relation-list">
  {relations.map(relation => (
    <li key={relation.fact_id} className={relation.fact_id === selectedRelationId ? 'is-selected' : ''}>
      <button type="button" aria-label={`${relation.label} ${relation.other.name}`} aria-pressed={relation.fact_id === selectedRelationId} onClick={() => onSelectRelation?.(relation.fact_id)}>
        <span>{relation.label}</span>
        <b>{relation.other.name}</b>
      </button>
    </li>
  ))}
</ul>
```

- [ ] **Step 4: 将 Cytoscape 节点改为小型类别点**

节点数据增加中心状态：

```tsx
...graph.nodes.map(node => ({
  data: {
    id: node.id,
    label: node.name,
    type: node.type,
    color: getEntityTypeStyle(node.type).color,
    center: node.id === centerId,
  },
})),
```

节点与边样式改为：

```tsx
{ selector: 'node', style: { 'background-color': 'data(color)', color: '#171717', label: 'data(label)', 'font-family': 'Geist Sans, system-ui', 'font-size': 11, 'font-weight': 400, 'text-valign': 'bottom', 'text-margin-y': 8, width: 10, height: 10 } },
{ selector: 'node[center = true]', style: { width: 14, height: 14, 'border-width': 3, 'border-color': '#0072f5' } },
{ selector: 'edge', style: { width: 1, 'line-color': '#d4d4d4', 'target-arrow-color': '#d4d4d4', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: '#4d4d4d' } },
{ selector: 'edge[selected = "true"]', style: { width: 2, 'line-color': '#0072f5', 'target-arrow-color': '#0072f5', color: '#0072f5', 'font-size': 10 } },
```

- [ ] **Step 5: 完成图谱工作台样式**

在 `vercel.css` 增加：

```css
.graph-page { height: calc(100vh - var(--ds-header-height)); background: var(--ds-background-primary); }
.graph-toolbar { width: min(var(--ds-workspace-width), calc(100% - 48px)); margin: 0 auto; padding: 32px 0 24px; }
.search-wrap input { height: 40px; padding: 0 12px; border: 0; border-radius: var(--ds-radius); background: transparent; box-shadow: var(--ds-shadow-border); }
.search-results { border: 0; border-radius: var(--ds-radius-card); background: var(--ds-background-elevated); box-shadow: var(--ds-shadow-menu); overflow: hidden; }
.graph-workspace { width: min(var(--ds-workspace-width), calc(100% - 48px)); margin: 0 auto; background: var(--ds-background-elevated); border-radius: var(--ds-radius-card); box-shadow: var(--ds-shadow-border); overflow: hidden; }
.graph-canvas { background: var(--ds-background-elevated); background-image: none; }
.entity-panel { width: 384px; padding: 24px; border: 0; background: var(--ds-background-elevated); box-shadow: -1px 0 rgb(0 0 0 / 8%); }
.attribute-list button, .relation-list button { width: 100%; padding: 8px 12px; border: 0; border-radius: var(--ds-radius); background: transparent; color: var(--ds-text-primary); text-align: left; }
.attribute-list button:hover, .relation-list button:hover { background: var(--ds-background-hover); }
.attribute-list .is-selected button, .relation-list .is-selected button { box-shadow: var(--ds-focus-ring); }
```

- [ ] **Step 6: 运行图谱测试并提交**

Run: `cd apps/web && npm test -- --run src/features/graph/GraphPage.test.tsx`

Expected: 12 个图谱测试全部 PASS，包括 Space 和 Enter 键盘选择。

```bash
git add apps/web/src/features/graph apps/web/src/styles/vercel.css
git commit -m "feat: redesign graph workspace interactions"
```

---

### Task 4: 统一问答、构建与审核状态表达

**Files:**
- Create: `apps/web/src/components/StatusDot.tsx`
- Create: `apps/web/src/components/StatusDot.test.tsx`
- Modify: `apps/web/src/features/build/JobProgress.tsx`
- Modify: `apps/web/src/features/review/ReviewDetail.tsx`
- Modify: `apps/web/src/features/review/ReviewPage.test.tsx`
- Modify: `apps/web/src/styles/vercel.css`

**Interfaces:**
- Consumes: 构建任务 `status`、审核项 `severity`、Task 1 的状态颜色约束。
- Produces: `StatusDot({ label, tone })`；`tone` 为 `neutral | info | success | warning | danger`。

- [ ] **Step 1: 为状态点编写失败测试**

创建 `StatusDot.test.tsx`：

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusDot } from './StatusDot'

describe('StatusDot', () => {
  it('pairs the color marker with readable status text', () => {
    render(<StatusDot label="构建失败" tone="danger" />)
    expect(screen.getByText('构建失败')).toBeVisible()
    expect(screen.getByTestId('status-dot')).toHaveAttribute('data-tone', 'danger')
  })
})
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd apps/web && npm test -- --run src/components/StatusDot.test.tsx`

Expected: FAIL，模块 `StatusDot` 尚不存在。

- [ ] **Step 3: 实现状态点组件**

创建 `StatusDot.tsx`：

```tsx
export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

export function StatusDot({ label, tone = 'neutral' }: { label: string; tone?: StatusTone }) {
  return (
    <span className="status-dot-label">
      <i data-testid="status-dot" data-tone={tone} aria-hidden="true" />
      {label}
    </span>
  )
}
```

在 `JobProgress.tsx` 中增加：

```tsx
<StatusDot label={job.status} tone={job.status === 'FAILED' ? 'danger' : job.status === 'COMPLETED' ? 'success' : 'info'} />
```

在 `ReviewDetail.tsx` 中将严重度标签改为：

```tsx
<StatusDot label={`严重度 ${item.severity}`} tone={item.severity >= 70 ? 'danger' : item.severity >= 40 ? 'warning' : 'neutral'} />
```

- [ ] **Step 4: 为审核状态增加断言**

在 `ReviewPage.test.tsx` 首个测试中增加：

```tsx
expect(await screen.findByText('严重度 40')).toBeVisible()
expect(screen.getByTestId('status-dot')).toHaveAttribute('data-tone', 'warning')
```

- [ ] **Step 5: 完成问答、构建与审核布局样式**

在 `vercel.css` 增加：

```css
.status-dot-label { display: inline-flex; align-items: center; gap: 8px; color: var(--ds-text-secondary); font-size: 12px; line-height: 16px; }
.status-dot-label i { width: 10px; height: 10px; border-radius: 50%; background: var(--ds-text-muted); }
.status-dot-label i[data-tone="info"] { background: #0062d1; }
.status-dot-label i[data-tone="success"] { background: #398e4a; }
.status-dot-label i[data-tone="warning"] { background: #ff990a; }
.status-dot-label i[data-tone="danger"] { background: #e5484d; }
.ask-layout { display: grid; grid-template-columns: minmax(280px, 2fr) minmax(480px, 3fr); gap: 32px; }
.answer-card, .answer-empty, .build-grid > *, .review-queue, .review-detail { border: 0; border-radius: var(--ds-radius-card); background: var(--ds-background-elevated); box-shadow: var(--ds-shadow-border); }
.answer-card { padding: 32px; }
.answer-card h2 { font-size: 32px; line-height: 40px; font-weight: 600; letter-spacing: -1.28px; }
.build-grid { gap: 24px; border: 0; }
.quality-metrics { gap: 12px; border: 0; }
.quality-metrics > div { padding: 16px; border: 0; border-radius: var(--ds-radius); background: var(--ds-background-recessed); box-shadow: none; }
.review-workspace { display: grid; grid-template-columns: minmax(280px, 360px) minmax(0, 1fr); gap: 24px; border: 0; }
.review-queue button { border: 0; border-radius: var(--ds-radius); box-shadow: var(--ds-shadow-border); }
.review-queue button:hover, .review-queue button.active { background: var(--ds-background-hover); }
```

- [ ] **Step 6: 运行业务页面测试并提交**

Run: `cd apps/web && npm test -- --run src/components/StatusDot.test.tsx src/features/ask/AskPage.test.tsx src/features/build/BuildPage.test.tsx src/features/review/ReviewPage.test.tsx`

Expected: 4 个测试文件全部 PASS。

```bash
git add apps/web/src/components apps/web/src/features/build/JobProgress.tsx apps/web/src/features/review/ReviewDetail.tsx apps/web/src/features/review/ReviewPage.test.tsx apps/web/src/styles/vercel.css
git commit -m "feat: unify workflow status presentation"
```

---

### Task 5: 完成响应式、减少动态效果与遗留样式清理

**Files:**
- Modify: `apps/web/src/styles/vercel.css`
- Modify: `apps/web/src/styles/theme.css`
- Test: `apps/web/src/App.test.tsx`
- Test: `apps/web/src/features/graph/GraphPage.test.tsx`
- Test: `apps/web/src/features/review/ReviewPage.test.tsx`

**Interfaces:**
- Consumes: Tasks 1–4 的全部组件类与设计令牌。
- Produces: 320、768、1024、1440px 稳定布局；无冲突的最终样式层。

- [ ] **Step 1: 增加响应式与减少动态效果规则**

在 `vercel.css` 末尾增加：

```css
@media (max-width: 1024px) {
  .site-header { grid-template-columns: auto minmax(0, 1fr) 200px; padding-inline: 16px; }
  .page, .guide-page, .graph-toolbar, .graph-workspace { width: min(100% - 32px, var(--ds-page-width)); }
  .entity-panel { width: 320px; }
  .review-workspace { grid-template-columns: 300px minmax(0, 1fr); }
}

@media (max-width: 768px) {
  .site-header { grid-template-columns: 1fr auto; gap: 8px; }
  .site-header nav { grid-column: 1 / -1; overflow-x: auto; scrollbar-width: thin; }
  .ontology-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ask-layout, .review-workspace { grid-template-columns: 1fr; }
  .graph-workspace { display: block; }
  .entity-panel { width: 100%; box-shadow: 0 -1px rgb(0 0 0 / 8%); }
}

@media (max-width: 480px) {
  .page, .guide-page { width: calc(100% - 32px); padding-block: 40px 64px; }
  .page-header { display: block; margin-bottom: 32px; }
  .page-header h1 { font-size: 40px; line-height: 40px; letter-spacing: -1.6px; }
  .ontology-grid { grid-template-columns: 1fr; }
  .ask-form > div { display: grid; gap: 8px; }
  .ask-form button { width: 100%; }
  .triple-card { display: grid; gap: 12px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; }
}
```

- [ ] **Step 2: 清理会穿透覆盖层的旧规则**

从 `theme.css` 删除旧的 `.skeleton` 渐变动画、`.triple-stage:before` 网格、`.graph-canvas` 网格背景，以及对 `.brand span` 的红色背景。把全部 `font-weight:700` 和 `font-weight:800` 改为 `font-weight:600`；保留布局必需规则和所有后续证据、审核、构建功能类，确认 `vercel.css` 不依赖被删除的颜色变量。

在 `vercel.css` 增加静态、无渐变的加载占位：

```css
.skeleton { min-height: 384px; border-radius: var(--ds-radius-card); background: var(--ds-background-recessed); box-shadow: var(--ds-shadow-border); }
```

- [ ] **Step 3: 扫描禁止项并修正命中**

Run:

```bash
rg -n "font-weight:(700|800)|radial-gradient|background-image:linear-gradient|--swiss-|#e3342f|#d9f000" apps/web/src/styles apps/web/src/**/*.tsx
```

Expected: 无输出。状态点允许的颜色只出现在 `.status-dot-label i[data-tone]` 和 `entityTypeStyles.ts`。

- [ ] **Step 4: 运行全量前端验证**

Run: `cd apps/web && npm test -- --run --testTimeout=15000`

Expected: 全部测试文件 PASS。

Run: `cd apps/web && npm run typecheck`

Expected: exits 0，无 TypeScript 错误。

Run: `cd apps/web && npm run build`

Expected: Vite 完成生产构建并输出资源大小。

- [ ] **Step 5: 在真实浏览器完成四视口验收**

Run: `cd apps/web && npm run dev -- --host 127.0.0.1`

依次在 320×800、768×1024、1024×768、1440×900 检查 `/guide`、`/ontology`、`/graph`、`/ask`、`/build`、`/review`：

- 页面无横向滚动和文本重叠。
- 导航、项目选择、搜索、分段控件、属性、关系和审核按钮可用 Tab 到达。
- 焦点显示白色内环和蓝色外环。
- 图谱画布无网格，实体类别色仅显示为小点。
- 加载、错误和空状态均包含可读文字。
- 浏览器控制台无错误。

- [ ] **Step 6: 提交最终回归修正**

```bash
git add apps/web/src/styles apps/web/src/App.test.tsx apps/web/src/features/graph/GraphPage.test.tsx apps/web/src/features/review/ReviewPage.test.tsx
git commit -m "fix: complete responsive and accessibility polish"
```

---

## Final Verification

- [ ] Run: `git diff --check master...HEAD`

Expected: 无空白错误。

- [ ] Run: `cd apps/web && npm test -- --run --testTimeout=15000 && npm run typecheck && npm run build`

Expected: 测试、类型检查和生产构建全部通过。

- [ ] Review the final diff and confirm no API client, router contract, project context or backend file changed.

- [ ] Confirm the final UI against `docs/superpowers/specs/2026-07-14-vercel-ui-redesign-design.md` before merge.
