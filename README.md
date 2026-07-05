# 江湖图谱

以《笑傲江湖》为语料的本体与知识图谱教学演示。网站用一条循序渐进的教学路径说明：本体如何约束概念，知识图谱如何保存事实，原文证据如何让查询和问答可验证。

Phase 1 使用人工校验的核心图谱，包含人物、门派、武学、事件、关系与原文证据。在线上传小说、模型配置和全书自动抽取属于 Phase 2，本版本没有伪装成可用功能的入口。

## 技术栈

- React 19、TypeScript、Vite、Cytoscape.js
- FastAPI、Pydantic、SQLAlchemy
- Neo4j 5 Community（Docker Compose）
- Pytest、Vitest、Playwright

## 前置条件

- Python 3.12+
- Node.js 22+ 与 npm
- Docker Desktop（macOS/Windows）或 Docker Engine + Compose（Linux）

## 安装与启动

```bash
make install
make neo4j-up
.venv/bin/python scripts/import_core_graph.py
make dev
```

`make dev` 会打印两个开发服务命令。分别在两个终端执行：

```bash
.venv/bin/uvicorn app.main:app --app-dir apps/api/src --reload
npm --prefix apps/web run dev
```

浏览器打开 `http://127.0.0.1:5173/guide`。Neo4j Browser 位于 `http://127.0.0.1:7474`。

## 环境变量

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt 地址 |
| `NEO4J_USER` | `neo4j` | Neo4j 用户名 |
| `NEO4J_PASSWORD` | `development-only` | 本地演示密码；生产环境必须覆盖 |
| `SQLITE_URL` | `sqlite:///./tspw-graph.db` | 项目元数据数据库 |

FastAPI 会读取仓库根目录的 `.env`。Compose 的本地默认认证与上表一致。

## 数据与验证

核心数据位于 `data/xiaoao/core-graph.json`。导入脚本会逐条核对证据的章节、字符偏移、短引文与 SHA-256 文本指纹；重复导入是幂等的。

完整验证会启动 Neo4j、导入种子图谱，并运行后端单元/集成测试、前端测试、类型检查、生产构建、证据校验和浏览器端到端测试：

```bash
make verify
```

停止本地 Neo4j：

```bash
make neo4j-down
```
