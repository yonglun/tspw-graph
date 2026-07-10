# 江湖图谱

以《笑傲江湖》为语料的本体与知识图谱教学网站。内置核心图谱用于讲解本体、事实、证据、图查询和可解释问答；在线构建工作台可上传 TXT 小说，由持久化 Worker 抽取并导入隔离的 Neo4j 项目图谱。

## 技术栈与前置条件

- React 19、TypeScript、Vite、Cytoscape.js
- FastAPI、SQLAlchemy、SQLite、Neo4j 5 Community
- Python 3.12+、Node.js 22+、Docker Desktop/Engine + Compose

## Docker Compose 运行

```bash
cp .env.example .env
docker compose up -d --build --wait
```

打开 `http://127.0.0.1:5173/guide`。Compose 启动 `web` / `api` / `worker` / `neo4j` 四个服务，上传文件与 SQLite 使用 `app-data` 卷。停止服务：

```bash
docker compose down
```

完整 Docker 部署和 Azure OpenAI 配置见 [Docker 部署手册](docs/deployment-docker-azure-openai.md)。

## 本地进程运行

```bash
make install
make neo4j-up
.venv/bin/python scripts/import_core_graph.py
make dev
```

`make dev` 会输出 API、Worker 和 Web 的三个终端命令。

## 模型配置与密钥边界

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DATA_ROOT` | `./data/uploads` | 上传原文存储根目录 |
| `SQLITE_URL` | `sqlite:///./tspw-graph.db` | 项目、任务和质量报告 |
| `MODEL_PROFILES_JSON` | 内置 `fixed:test` | OpenAI 兼容接口、Azure OpenAI、Ollama 或测试模型档案 |
| `OPENAI_API_KEY` | 无 | OpenAI 兼容档案的密钥 |
| `AZURE_OPENAI_API_KEY` | 无 | Azure OpenAI 档案的密钥 |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt 地址 |

`.env.example` 含 OpenAI、Azure OpenAI 与 `http://host.docker.internal:11434` Ollama 示例。Azure OpenAI 档案使用 `provider="azure-openai"`，`base_url` 填资源端点，`model` 填部署名，`api_version` 默认可用 `2024-06-01`。档案只保存密钥环境变量名；Compose 会向 API 与 Worker 注入模型密钥，API 只用环境变量是否存在来标记模型档案可用，实际模型调用由 Worker 完成。

## 操作与恢复

- 上传后任务 ID 保存在 URL，刷新可恢复进度；SSE 断开后前端自动轮询。
- 任务可暂停、继续、取消；失败后可重试。Worker 重启会继续租约过期的任务。
- 在项目切换器中选中用户项目后可删除；内置《笑傲江湖》项目不可删除。
- 已有项目保留原始 TXT 时，可在 `/build` 选择“重新抽取属性”。属性补抽只增量写入有证据支持的实体属性和属性证据，不重建实体、关系事实或审核状态。

升级并验证图谱响应耗时：

```bash
git pull
sudo docker compose up -d --build --wait
python3 scripts/check-graph-performance.py --base-url http://localhost:5173 --project-id xiaoao --query 令狐冲
```

监控补抽或完整构建任务：

```bash
docker compose logs -f worker
```

### 阶段三：审核与质量改进

阶段三新增 `/review` 审核工作台。构建完成后，系统可扫描项目图谱生成待审核项；审核员可以接受/拒绝事实、合并重复实体、拆出别名，并通过审计日志追踪每次变更。

默认图谱和问答读取审核后有效数据。被拒绝事实不会出现在图谱和问答中，但原始证据和审计记录会保留。

常用命令：

```bash
curl -X POST http://127.0.0.1:8000/api/projects/xiaoao/review/scan
open http://127.0.0.1:5173/review
```

## 验证、真实模型冒烟与备份

```bash
make verify
make smoke-openai
make smoke-ollama
docker run --rm -v tspw-graph_app-data:/data -v "$PWD/backups:/backup" alpine tar czf /backup/app-data.tgz -C /data .
docker run --rm -v tspw-graph_neo4j-data:/data -v "$PWD/backups:/backup" alpine tar czf /backup/neo4j-data.tgz -C /data .
```

`make verify` 会核对内置图谱的原文证据，因此需要未纳入 Git 的 `笑傲江湖/笑傲江湖.txt`。若文件在其他位置，使用 `SOURCE_PATH=/path/to/笑傲江湖.txt make verify`。

真实模型冒烟测试在档案或密钥缺失时会明确跳过，不进入默认 `verify`。

首次在生产项目上执行属性补抽前，先备份 `tspw-graph_app-data` 和 `tspw-graph_neo4j-data` 两个 Docker volume。

## 许可证

项目代码采用 [Apache License 2.0](LICENSE)。小说原文不属于本项目开源许可范围，且不会被 Git 跟踪。
