# 系统架构与数据库设计文档拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将混合的数据库设计文档拆分成职责清晰、内容完整且互相引用的系统架构设计与数据库设计文档。

**Architecture:** 新建 `docs/system-architecture-design.md` 承载组件协作、端到端流程、跨存储一致性、生命周期、运维与安全；收敛 `docs/database-design.md`，仅保留数据模型、字段字典、约束、映射、数据库性能和查询。两个文件共享稳定相对链接，但不复制大段正文。

**Tech Stack:** Markdown、Mermaid、SQLite SQL、Neo4j Cypher、Git。

## Global Constraints

- 保留 `docs/database-design.md` 原路径，避免既有链接失效。
- 新增文件固定命名为 `docs/system-architecture-design.md`。
- 两份文档必须能够独立阅读，并在开头互相链接。
- 不修改应用代码、数据库 schema、Docker Compose 或运行时行为。
- 不删除原文中的表结构、图模型、查询、运维命令、风险说明和代码链接。
- 系统能力和已知限制必须以当前代码事实为准，不得把建议描述为已实现功能。

---

### Task 1: 建立系统架构设计文档

**Files:**
- Create: `docs/system-architecture-design.md`
- Reference: `docs/database-design.md`
- Reference: `docs/superpowers/specs/2026-07-16-system-database-document-split-design.md`

**Interfaces:**
- Consumes: 原数据库设计文档中的系统级章节和已批准拆分规格。
- Produces: 一份独立可读的系统架构设计文档，供数据库设计文档交叉引用。

- [ ] **Step 1: 写入文档元信息和相关文档链接**

在文件开头写入：

```markdown
# 笑傲江湖知识图谱系统架构设计

版本：1.0

更新日期：2026-07-16

相关文档：[数据库设计](database-design.md)
```

- [ ] **Step 2: 迁移总体架构和组件职责**

从原文迁移并重新组织：

- Web、API、Worker、SQLite、Neo4j、上传目录；
- 各组件的职责边界；
- 默认 Docker Compose 部署位置；
- 双存储架构 Mermaid 图。

章节名称固定为：

```markdown
## 1. 文档目标与适用范围
## 2. 总体系统架构
## 3. 组件职责与部署边界
```

- [ ] **Step 3: 迁移端到端数据流和任务生命周期**

迁移小说上传、文本规范化、任务领取、抽取、图导入、质量报告与完成状态的数据流，并补充：

```markdown
## 4. 小说文本进入知识图谱的数据流
## 5. 构建任务生命周期
### 5.1 完整构建
### 5.2 属性补抽
### 5.3 暂停、失败与重试
```

保留现有时序 Mermaid 图和状态边界说明。

- [ ] **Step 4: 迁移跨存储一致性和审核流程**

新增以下系统级章节：

```markdown
## 6. 跨存储一致性设计
## 7. 项目隔离与审核流程
### 7.1 项目隔离
### 7.2 事实审核
### 7.3 实体合并
### 7.4 别名拆分
### 7.5 项目删除
```

必须明确：

- SQLite 与 Neo4j 没有跨库事务；
- 审核先更新 Neo4j，再记录 SQLite 动作；
- 实体合并当前不迁移 `HAS_ATTRIBUTE`；
- 别名拆分当前不迁移事实和属性，也不显式补建 `HAS_ENTITY`；
- 项目删除按 Neo4j、上传目录、SQLite 的顺序执行，存在部分成功风险。

- [ ] **Step 5: 迁移运维、安全和系统级演进章节**

迁移并整理：

```markdown
## 8. Docker 数据卷、备份与恢复
## 9. 安全架构
## 10. 可观测性与巡检
## 11. 系统级已知限制与演进建议
## 附录 A：系统代码定位
```

系统级限制至少包含跨库事务、同项目重建不清理旧图、项目删除补偿、Neo4j Community 备份和端口暴露。

- [ ] **Step 6: 验证系统架构文档章节**

Run:

```bash
for heading in \
  '总体系统架构' \
  '组件职责与部署边界' \
  '小说文本进入知识图谱的数据流' \
  '构建任务生命周期' \
  '跨存储一致性设计' \
  '项目隔离与审核流程' \
  '备份与恢复' \
  '安全架构' \
  '可观测性与巡检' \
  '系统级已知限制'; do
  rg -q "$heading" docs/system-architecture-design.md || exit 1
done
```

Expected: 命令退出码为 0。

- [ ] **Step 7: 提交系统架构文档**

```bash
git add docs/system-architecture-design.md
git commit -m "docs: add system architecture design"
```

---

### Task 2: 收敛数据库设计文档

**Files:**
- Modify: `docs/database-design.md`
- Reference: `docs/system-architecture-design.md`

**Interfaces:**
- Consumes: Task 1 产生的系统架构设计文档。
- Produces: 只承担数据组织、约束、查询和数据库演进职责的数据库设计文档。

- [ ] **Step 1: 更新文档定位和交叉链接**

在标题元信息后增加：

```markdown
相关文档：[系统架构设计](system-architecture-design.md)
```

文档目标明确限定为 SQLite、Neo4j、数据映射、约束、索引、查询和数据库运维注意事项。

- [ ] **Step 2: 保留数据库模型核心章节**

数据库文档保留并连续编号：

```markdown
## 1. 文档目标与适用范围
## 2. 存储职责摘要
## 3. SQLite 逻辑模型
## 4. SQLite 完整表结构
## 5. Neo4j 属性图模型
## 6. Neo4j 节点、关系和属性字典
## 7. SQLite 与 Neo4j 的数据映射
## 8. 项目隔离、约束与性能设计
## 9. 典型 SQL、典型 Cypher 和排查查询
## 10. 数据库级已知限制与演进建议
## 附录 A：数据库代码定位
```

- [ ] **Step 3: 删除已迁移的系统级正文**

从数据库文档移除以下详细正文，并在需要处用一段摘要链接到系统架构文档：

- 端到端构建数据流；
- 完整构建、属性补抽、任务重试和项目删除流程；
- Docker 备份恢复操作；
- 管理员认证、会话、CSRF、审计和网络暴露；
- 系统级监控指标；
- 审核流程和实体合并步骤的完整说明。

数据库文档仍须保留与数据库直接相关的隔离键、外键、孤立节点和索引说明。

- [ ] **Step 4: 保持 SQLite 覆盖完整**

Run:

```bash
for table in projects jobs job_events job_quality review_items review_actions \
  quality_snapshots admin_accounts admin_sessions admin_login_throttles \
  admin_audit_events; do
  rg -q "$table" docs/database-design.md || exit 1
done
```

Expected: 11 张表全部找到，退出码为 0。

- [ ] **Step 5: 保持 Neo4j 覆盖完整**

Run:

```bash
for term in Project Chapter Entity Fact Evidence AttributeAssertion \
  HAS_CHAPTER HAS_ENTITY IN_CHAPTER SOURCE TARGET RELATED EVIDENCED_BY \
  HAS_ATTRIBUTE; do
  rg -q "$term" docs/database-design.md || exit 1
done
```

Expected: 6 类节点和 8 类关系全部找到，退出码为 0。

- [ ] **Step 6: 验证查询示例和数据库限制仍存在**

Run:

```bash
for term in \
  'SQLite：项目及最新任务' \
  'Cypher：按名称搜索项目内实体' \
  'Cypher：孤立属性' \
  'PRAGMA foreign_keys=ON' \
  'job_events.sequence' \
  'AttributeAssertion'; do
  rg -q "$term" docs/database-design.md || exit 1
done
```

Expected: 命令退出码为 0。

- [ ] **Step 7: 提交数据库文档收敛**

```bash
git add docs/database-design.md
git commit -m "docs: focus database design on data models"
```

---

### Task 3: 验证双文档完整性并更新状态

**Files:**
- Modify: `docs/superpowers/specs/2026-07-16-system-database-document-split-design.md`
- Modify: `docs/superpowers/plans/2026-07-16-system-database-document-split.md`
- Verify: `docs/system-architecture-design.md`
- Verify: `docs/database-design.md`

**Interfaces:**
- Consumes: 已拆分的两份设计文档。
- Produces: 通过结构、链接、内容覆盖和安全检查的最终文档集。

- [ ] **Step 1: 检查双向链接**

Run:

```bash
rg -q '\\[数据库设计\\]\\(database-design.md\\)' docs/system-architecture-design.md
rg -q '\\[系统架构设计\\]\\(system-architecture-design.md\\)' docs/database-design.md
```

Expected: 两条命令均退出码为 0。

- [ ] **Step 2: 检查代码围栏和 Mermaid 图**

Run:

```bash
python - <<'PY'
from pathlib import Path

paths = [
    Path("docs/system-architecture-design.md"),
    Path("docs/database-design.md"),
]
for path in paths:
    text = path.read_text()
    assert text.count("```") % 2 == 0, f"unclosed fence: {path}"
    assert "```mermaid" in text, f"missing Mermaid diagram: {path}"
print("markdown fences and Mermaid diagrams: ok")
PY
```

Expected: 输出 `markdown fences and Mermaid diagrams: ok`。

- [ ] **Step 3: 检查仓库内 Markdown 链接**

Run:

```bash
python - <<'PY'
import re
from pathlib import Path

missing = []
for doc in [
    Path("docs/system-architecture-design.md"),
    Path("docs/database-design.md"),
]:
    for target in re.findall(r'\[[^]]+\]\(([^)]+)\)', doc.read_text()):
        if '://' in target or target.startswith('#'):
            continue
        path = (doc.parent / target.split('#', 1)[0]).resolve()
        if not path.exists():
            missing.append((str(doc), target))
assert not missing, f"missing links: {missing}"
print("local links: ok")
PY
```

Expected: 输出 `local links: ok`。

- [ ] **Step 4: 检查内容没有因拆分丢失**

Run:

```bash
for term in \
  '跨存储一致性' \
  'ATTRIBUTE_BACKFILL' \
  'HAS_ATTRIBUTE' \
  'Argon2' \
  'BEGIN IMMEDIATE' \
  'MODEL_RESPONSE_INVALID' \
  'Neo4j Community' \
  '同项目完整构建'; do
  rg -q "$term" docs/system-architecture-design.md docs/database-design.md || exit 1
done
```

Expected: 所有关键事实至少存在于一份文档中。

- [ ] **Step 5: 检查敏感信息和空白错误**

Run:

```bash
! rg -n \
  'AZURE_OPENAI_API_KEY=.+|OPENAI_API_KEY=.+|tspw_admin_session=.+|Pass@word1' \
  docs/system-architecture-design.md docs/database-design.md
git diff --check
```

Expected: 两条命令均退出码为 0。

- [ ] **Step 6: 更新规格和计划状态**

将拆分规格状态改为：

```markdown
状态：已实现
```

仅在全部检查通过后，把本计划全部复选框更新为 `[x]`。

- [ ] **Step 7: 提交最终验证状态**

```bash
git add \
  docs/superpowers/specs/2026-07-16-system-database-document-split-design.md \
  docs/superpowers/plans/2026-07-16-system-database-document-split.md
git commit -m "docs: complete architecture document split"
```

