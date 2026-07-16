# 数据库设计文档实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一份同时面向教学、开发和运维的数据库设计文档，准确描述当前 SQLite 与 Neo4j 双数据库实现。

**Architecture:** 以当前 `origin/master` 中的 SQLAlchemy 模型、仓储逻辑、Neo4j 写入 Cypher、配置与 Docker Compose 为事实来源。正文采用“架构与数据流 → SQLite → Neo4j → 跨库一致性 → 运维与安全 → 查询附录”的分层结构，并使用 Mermaid 提供总体架构图、ER 图和属性图模型图。

**Tech Stack:** Markdown、Mermaid、SQLite、SQLAlchemy 2、Neo4j 5.26 Community、Cypher、Docker Compose。

## Global Constraints

- 只新增或修改文档，不改变数据库模型、API、业务逻辑或部署配置。
- 已实现结构必须能在当前代码中找到直接证据；建议项必须显式标记为“建议”。
- SQLite 表结构以 `apps/api/src/app/**/models.py` 为准。
- Neo4j 节点、关系、约束和索引以 `apps/api/src/app/graph/neo4j.py` 为准。
- 文档不得包含真实密码、Cookie、会话令牌、CSRF、模型 API Key 或小说全文。
- 图示使用 GitHub 可渲染的 Mermaid，不引入外部图片。
- 所有仓库内链接使用相对路径。

---

### Task 1: 建立数据库事实清单

**Files:**
- Read: `apps/api/src/app/projects/models.py`
- Read: `apps/api/src/app/jobs/models.py`
- Read: `apps/api/src/app/review/models.py`
- Read: `apps/api/src/app/auth/models.py`
- Read: `apps/api/src/app/projects/repository.py`
- Read: `apps/api/src/app/jobs/repository.py`
- Read: `apps/api/src/app/review/repository.py`
- Read: `apps/api/src/app/auth/repository.py`
- Read: `apps/api/src/app/graph/models.py`
- Read: `apps/api/src/app/graph/neo4j.py`
- Read: `apps/api/src/app/graph/repository.py`
- Read: `apps/api/src/app/review/graph.py`
- Read: `apps/api/src/app/settings.py`
- Read: `compose.yaml`

**Interfaces:**
- Consumes: 当前分支基于 `origin/master` 的数据库实现。
- Produces: SQLite 表、约束与索引清单；Neo4j 节点、关系、约束与索引清单；跨库数据生命周期清单。

- [ ] **Step 1: 列出全部 SQLite ORM 表**

Run:

```bash
rg -n '__tablename__|UniqueConstraint|ForeignKey|index=True|primary_key=True' \
  apps/api/src/app/{projects,jobs,review,auth}/models.py
```

Expected: 输出 `projects`、`jobs`、`job_events`、`job_quality`、`review_items`、`review_actions`、`quality_snapshots`、`admin_accounts`、`admin_sessions`、`admin_login_throttles`、`admin_audit_events` 共 11 张表及其约束声明。

- [ ] **Step 2: 核对 SQLite 运行时升级逻辑**

Run:

```bash
rg -n 'create_all|ALTER TABLE|BEGIN IMMEDIATE|ondelete=' \
  apps/api/src/app/{projects,jobs,review,auth}/*.py
```

Expected: 确认表由 `Base.metadata.create_all` 初始化；`projects` 和 `jobs.kind` 存在兼容升级；任务领取和认证关键写入使用 `BEGIN IMMEDIATE`；显式外键级联仅按代码记录。

- [ ] **Step 3: 列出 Neo4j 约束、索引和写入关系**

Run:

```bash
rg -n 'CREATE CONSTRAINT|CREATE INDEX|MERGE \(|-\[:|\[r:RELATED' \
  apps/api/src/app/graph/neo4j.py apps/api/src/app/review/graph.py
```

Expected: 输出 6 个唯一约束、2 个实体索引，以及 `HAS_CHAPTER`、`HAS_ENTITY`、`IN_CHAPTER`、`HAS_ATTRIBUTE`、`EVIDENCED_BY`、`SOURCE`、`TARGET`、`RELATED` 等关系。

- [ ] **Step 4: 核对部署存储位置和数据卷**

Run:

```bash
rg -n 'SQLITE_URL|DATA_ROOT|NEO4J_|volumes:|app-data|neo4j-data' \
  compose.yaml apps/api/src/app/settings.py docs/deployment-docker-azure-openai.md
```

Expected: SQLite 文件为容器内 `/data/tspw-graph.db`，上传目录为 `/data/uploads`，二者位于 `app-data`；Neo4j `/data` 位于 `neo4j-data`。

- [ ] **Step 5: 检查事实清单没有遗漏模型文件**

Run:

```bash
rg --files apps/api/src/app | rg '/models\.py$' | sort
```

Expected: 除 ORM 表外还能看到抽取、图谱、本体和问答的 Pydantic 领域模型；计划中只把 SQLAlchemy 模型写成 SQLite 物理表。

### Task 2: 编写架构、数据流与 SQLite 设计

**Files:**
- Create: `docs/database-design.md`
- Reference: `docs/superpowers/specs/2026-07-16-database-design-document-design.md`
- Reference: `apps/api/src/app/projects/models.py`
- Reference: `apps/api/src/app/jobs/models.py`
- Reference: `apps/api/src/app/review/models.py`
- Reference: `apps/api/src/app/auth/models.py`

**Interfaces:**
- Consumes: Task 1 的 SQLite 事实清单。
- Produces: 文档第 1–5 节，包括总体架构图、数据流图、SQLite ER 图和 11 张表的字段字典。

- [ ] **Step 1: 创建文档标题、状态说明和导航目录**

在 `docs/database-design.md` 写入：文档目标、适用读者、事实来源、版本日期、数据库职责摘要和 15 节目录。明确“当前实现”和“建议”两类内容的视觉标记。

- [ ] **Step 2: 编写总体架构图**

使用 Mermaid `flowchart LR` 表达：

```text
Browser -> Web -> API
API -> SQLite
API -> Uploads
API -> Neo4j
Worker -> SQLite
Worker -> Uploads
Worker -> Neo4j
```

在图后解释 SQLite 是控制面与工作流存储，Neo4j 是图谱查询存储，上传目录保存原始 TXT。

- [ ] **Step 3: 编写构建数据流**

使用 Mermaid `sequenceDiagram` 覆盖上传、创建任务、Worker 领取任务、切分、抽取、解析、验证、导入、质量报告和完成状态。明确模型调用结果不会直接绕过验证写入 Neo4j。

- [ ] **Step 4: 编写 SQLite ER 图**

使用 Mermaid `erDiagram` 表达已声明外键：

```text
PROJECTS ||--o{ JOBS : owns
JOBS ||--o{ JOB_EVENTS : emits
JOBS ||--o| JOB_QUALITY : summarizes
ADMIN_ACCOUNTS ||--o{ ADMIN_SESSIONS : owns
```

在图下注明审核表和管理员审计表通过业务 ID 关联，但当前没有数据库外键。

- [ ] **Step 5: 编写 11 张 SQLite 表字典**

每张表使用统一小节和 Markdown 表格，列出字段、类型、可空、默认值/生成规则、索引或约束、说明。对以下 JSON 字段给出脱敏结构示例：

- `job_events.snapshot`
- `job_quality.report`
- `review_items.target`
- `review_items.evidence_ids`
- `review_actions.payload`
- `quality_snapshots.metrics`
- `admin_audit_events.metadata`

- [ ] **Step 6: 核对表名与字段名**

Run:

```bash
for file in apps/api/src/app/{projects,jobs,review,auth}/models.py; do
  echo "--- $file"
  rg -n '__tablename__|Mapped\[' "$file"
done
```

Expected: 文档中的表和字段逐项对应输出；不得使用历史规格中未落地的 `password_changed_at` 或 `recent_failure_at` 等字段。

- [ ] **Step 7: 提交架构与 SQLite 章节**

```bash
git add docs/database-design.md
git commit -m "docs: describe database architecture and sqlite schema"
```

### Task 3: 编写 Neo4j 图模型与跨库一致性设计

**Files:**
- Modify: `docs/database-design.md`
- Reference: `apps/api/src/app/graph/models.py`
- Reference: `apps/api/src/app/graph/neo4j.py`
- Reference: `apps/api/src/app/graph/repository.py`
- Reference: `apps/api/src/app/review/graph.py`

**Interfaces:**
- Consumes: Task 1 的 Neo4j 事实清单和 Task 2 的项目/任务定义。
- Produces: 文档第 6–11 节，包括图模型、节点关系字典、映射、一致性、性能与生命周期。

- [ ] **Step 1: 编写 Neo4j 图模型图**

使用 Mermaid `flowchart LR` 展示 `Project`、`Chapter`、`Entity`、`Fact`、`Evidence`、`AttributeAssertion` 六类节点及八类结构关系。用单独说明解释 `Fact` 与 `RELATED` 的双重表达。

- [ ] **Step 2: 编写节点字典**

分别记录六类节点的业务键、唯一约束、主要属性、入边、出边和生命周期。明确除 `Project.id` 外，其余节点使用 `(project_id, id)` 复合唯一约束。

- [ ] **Step 3: 编写关系字典**

记录以下关系：

| 关系 | 起点 | 终点 | 角色 |
| --- | --- | --- | --- |
| `HAS_CHAPTER` | Project | Chapter | 项目结构 |
| `HAS_ENTITY` | Project | Entity | 项目结构 |
| `IN_CHAPTER` | Evidence | Chapter | 证据定位 |
| `SOURCE` | Fact | Entity | 事实主语 |
| `TARGET` | Fact | Entity | 事实宾语 |
| `RELATED` | Entity | Entity | 邻居遍历投影 |
| `EVIDENCED_BY` | Fact/AttributeAssertion | Evidence | 可追溯证据 |
| `HAS_ATTRIBUTE` | Entity | AttributeAssertion | 属性断言 |

说明 `RELATED` 的 `project_id`、`id`、`type`、`from_chapter`、`to_chapter` 和 `confidence` 属性。

- [ ] **Step 4: 编写索引、约束与查询性能说明**

列出 6 个唯一约束和 2 个索引的原始 Cypher 语义。说明实体搜索使用 `(project_id, name)`，类型过滤使用 `(project_id, type)`，邻域查询从已定位实体沿 `RELATED` 展开，避免默认加载全图。

- [ ] **Step 5: 编写 SQLite 与 Neo4j 映射和一致性边界**

明确：

- `projects.id` 对应 `(:Project).id`。
- `jobs.project_id` 决定 Worker 写入的 Neo4j `project_id`。
- SQLite 不保存图节点副本，Neo4j 不保存管理员会话或任务租约。
- 两库之间没有分布式事务；幂等 ID、`MERGE`、任务状态和重试共同实现最终一致性。

- [ ] **Step 6: 编写数据生命周期**

覆盖完整构建、属性补抽、任务暂停/重试、审核接受/拒绝、实体合并、项目删除和重新构建。明确 SQLite 外键级联与业务清理的区别，不推断未声明的级联行为。

- [ ] **Step 7: 核对 Neo4j 结构与代码**

Run:

```bash
rg -n 'CREATE CONSTRAINT|CREATE INDEX' apps/api/src/app/graph/neo4j.py
rg -n 'MERGE .*\[:|MERGE .*\[r:RELATED' apps/api/src/app/graph/neo4j.py
```

Expected: 文档的约束、索引和关系集合与代码逐项一致。

- [ ] **Step 8: 提交 Neo4j 与一致性章节**

```bash
git add docs/database-design.md
git commit -m "docs: document neo4j graph model and consistency"
```

### Task 4: 编写运维、安全和查询附录

**Files:**
- Modify: `docs/database-design.md`
- Reference: `compose.yaml`
- Reference: `apps/api/src/app/settings.py`
- Reference: `apps/api/src/app/auth/security.py`
- Reference: `apps/api/src/app/auth/repository.py`
- Reference: `docs/deployment-docker-azure-openai.md`

**Interfaces:**
- Consumes: Task 2–3 的存储结构和生命周期说明。
- Produces: 文档第 12–15 节，包括备份恢复、安全、典型查询、限制与演进建议。

- [ ] **Step 1: 编写 Docker 数据卷说明**

记录：

- `app-data:/data` 保存 `/data/tspw-graph.db` 和 `/data/uploads`。
- `neo4j-data:/data` 保存 Neo4j 数据目录。
- `.env` 与宿主机部署配置独立于命名卷，备份时需要单独管理且不得泄露密钥。

- [ ] **Step 2: 编写一致性备份流程**

提供安全默认流程：进入维护窗口、停止 `web/api/worker` 写入、备份 `app-data` 与 `neo4j-data`、记录版本和时间、恢复服务。命令示例只使用占位备份目录，不执行删除卷操作。

- [ ] **Step 3: 编写恢复与校验流程**

恢复步骤包括配置、两个数据卷、服务启动、健康检查、SQLite 项目/任务检查、Neo4j 项目节点/实体/事实数量检查。明确未完成任务需要人工判断后重试或重建。

- [ ] **Step 4: 编写安全设计**

准确说明管理员密码摘要、会话令牌摘要、CSRF、登录限流和审计元数据；说明 Neo4j 7474/7687 端口暴露风险及生产建议。不要在任何示例中打印环境变量中的 Key 或密码。

- [ ] **Step 5: 编写典型 SQLite 查询**

至少包含：

- 项目及最新任务。
- 排队或被 Worker 租用的任务。
- 项目质量报告。
- 待审核项数量。
- 有效管理员会话统计。
- 最近管理员审计事件。

查询只使用结构字段，不输出密码摘要、令牌摘要和 CSRF 值。

- [ ] **Step 6: 编写典型 Cypher 查询**

至少包含：

- 按名称搜索项目内实体。
- 查询实体一度关系。
- 查询关系事实及原文证据。
- 查询实体属性及属性证据。
- 按章节判断关系的 started/active/ended 状态。
- 统计单项目节点和关系数量。

所有查询使用 `$project_id`、`$entity_id` 等参数。

- [ ] **Step 7: 编写已知限制与演进建议**

已知限制至少包括：无正式迁移框架、SQLite 单写者特性、跨库最终一致性、审核表缺少项目外键、证据偏移依赖原文稳定性、Community 版备份能力限制。建议项单独标记，不伪装为当前实现。

- [ ] **Step 8: 提交运维与附录章节**

```bash
git add docs/database-design.md
git commit -m "docs: add database operations and query guide"
```

### Task 5: 全面核验并完成文档

**Files:**
- Modify: `docs/database-design.md`
- Modify: `docs/superpowers/specs/2026-07-16-database-design-document-design.md`
- Modify: `docs/superpowers/plans/2026-07-16-database-design-document.md`

**Interfaces:**
- Consumes: 完整数据库设计正文。
- Produces: 通过结构、事实、链接和格式检查的最终文档，以及完成状态更新。

- [ ] **Step 1: 检查必需章节**

Run:

```bash
for heading in \
  '总体数据库架构' \
  'SQLite 逻辑模型' \
  'SQLite 完整表结构' \
  'Neo4j 属性图模型' \
  '节点字典' \
  '关系字典' \
  '备份与恢复' \
  '安全设计' \
  '典型 SQL' \
  '典型 Cypher'; do
  rg -q "$heading" docs/database-design.md || exit 1
done
```

Expected: 命令退出码为 0。

- [ ] **Step 2: 检查所有 SQLite 表已记录**

Run:

```bash
for table in projects jobs job_events job_quality review_items review_actions \
  quality_snapshots admin_accounts admin_sessions admin_login_throttles \
  admin_audit_events; do
  rg -q "${table}" docs/database-design.md || exit 1
done
```

Expected: 命令退出码为 0。

- [ ] **Step 3: 检查所有 Neo4j 标签和关系已记录**

Run:

```bash
for term in Project Chapter Entity Fact Evidence AttributeAssertion \
  HAS_CHAPTER HAS_ENTITY IN_CHAPTER SOURCE TARGET RELATED EVIDENCED_BY \
  HAS_ATTRIBUTE; do
  rg -q "$term" docs/database-design.md || exit 1
done
```

Expected: 命令退出码为 0。

- [ ] **Step 4: 检查 Mermaid 和代码围栏成对闭合**

Run:

```bash
python - <<'PY'
from pathlib import Path

text = Path('docs/database-design.md').read_text()
assert text.count('```') % 2 == 0, 'unclosed fenced code block'
assert text.count('```mermaid') >= 3, 'expected at least three Mermaid diagrams'
print('markdown fences: ok')
PY
```

Expected: 输出 `markdown fences: ok`。

- [ ] **Step 5: 检查仓库内 Markdown 链接**

Run:

```bash
python - <<'PY'
import re
from pathlib import Path

doc = Path('docs/database-design.md')
missing = []
for target in re.findall(r'\[[^]]+\]\(([^)]+)\)', doc.read_text()):
    if '://' in target or target.startswith('#'):
        continue
    path = (doc.parent / target.split('#', 1)[0]).resolve()
    if not path.exists():
        missing.append(target)
assert not missing, f'missing links: {missing}'
print('local links: ok')
PY
```

Expected: 输出 `local links: ok`。

- [ ] **Step 6: 检查敏感信息与空白错误**

Run:

```bash
! rg -n 'AZURE_OPENAI_API_KEY=.+|OPENAI_API_KEY=.+|tspw_admin_session=.+' docs/database-design.md
git diff --check
```

Expected: 两条命令均退出码为 0。

- [ ] **Step 7: 更新规格和计划状态**

将设计规格状态改为“已实现”，并将本计划全部复选框更新为 `[x]`。只在全部检查通过后执行。

- [ ] **Step 8: 提交最终核验结果**

```bash
git add docs/database-design.md \
  docs/superpowers/specs/2026-07-16-database-design-document-design.md \
  docs/superpowers/plans/2026-07-16-database-design-document.md
git commit -m "docs: finalize database design documentation"
```

