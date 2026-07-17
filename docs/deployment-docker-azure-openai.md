# Docker 部署手册：江湖图谱 + Azure OpenAI

本文说明如何用 Docker Compose 部署运行江湖图谱，并配置 Azure OpenAI 作为在线抽取模型。

## 1. 部署目标

Docker Compose 会启动四个服务：

| 服务 | 作用 | 默认端口 |
| --- | --- | --- |
| `web` | React 前端，Nginx 托管静态文件 | `5173` |
| `api` | FastAPI 后端，提供图谱、项目、审核和模型档案 API | Compose 内部 `8000` |
| `worker` | 后台构建 Worker，读取任务并调用模型抽取 | 无外部端口 |
| `neo4j` | 图数据库 | `7474` / `7687` |

持久化数据使用两个 Docker volume：

- `tspw-graph_app-data`：上传文件、SQLite 数据库、任务状态；
- `tspw-graph_neo4j-data`：Neo4j 图数据库数据。

## 2. 前置条件

服务器或本机需要安装：

- Docker Engine 或 Docker Desktop；
- Docker Compose v2；
- Git；
- 一个可用的 Azure OpenAI 资源、部署名和 API Key。

检查 Docker：

```bash
docker --version
docker compose version
```

## 3. 获取代码

```bash
git clone https://github.com/Vincent-Ye/tspw-graph.git
cd tspw-graph
git checkout v0.3.1
```

如果需要使用最新主分支：

```bash
git checkout master
git pull --ff-only origin master
```

## 4. 创建环境配置

复制示例配置：

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
NEO4J_PASSWORD=replace-with-a-strong-local-password
DATA_ROOT=./data/uploads
SQLITE_URL=sqlite:///./tspw-graph.db

MODEL_PROFILES_JSON=[{"id":"fixed:test","provider":"fixed","base_url":"","model":"deterministic-test","api_key_env":"","timeout_seconds":10},{"id":"azure:gpt-4o-mini","provider":"azure-openai","base_url":"https://YOUR_RESOURCE.openai.azure.com","model":"YOUR_DEPLOYMENT_NAME","api_key_env":"AZURE_OPENAI_API_KEY","api_version":"2024-06-01","timeout_seconds":60}]

AZURE_OPENAI_API_KEY=replace-with-your-azure-openai-key

AUTH_BOOTSTRAP_USERNAME=admin
AUTH_BOOTSTRAP_PASSWORD=replace-with-a-strong-temporary-password
AUTH_COOKIE_SECURE=false
```

关键字段说明：

| 字段 | 示例 | 说明 |
| --- | --- | --- |
| `provider` | `azure-openai` | 必须使用该值，表示 Azure OpenAI provider |
| `base_url` | `https://my-resource.openai.azure.com` | Azure OpenAI 资源 endpoint，不包含 `/openai/deployments/...` |
| `model` | `gpt-4o-mini-prod` | Azure OpenAI deployment name，不是基础模型名称 |
| `api_key_env` | `AZURE_OPENAI_API_KEY` | API 用它判断 profile 是否可用；Worker 用它读取密钥并调用模型 |
| `api_version` | `2024-06-01` | Azure OpenAI API version |
| `timeout_seconds` | `60` | 单次模型请求超时 |
| `reasoning_effort` | 省略 | Responses API 推理强度；`gpt-5.6-sol` 建议设为 `low` |
| `max_output_tokens` | 省略 | Responses API 最大输出 Token；必须为正整数 |

注意：

- `MODEL_PROFILES_JSON` 必须是合法 JSON，建议保持单行，避免 shell 或 `.env` 解析问题。
- Azure OpenAI 的 `model` 字段填部署名。例如你在 Azure Portal 中创建的 deployment 叫 `kg-extractor-gpt4o-mini`，这里就填这个部署名。

### Azure v1 Responses 模型

Azure AI Foundry 中以 `/openai/v1/responses` 结尾的部署使用新的 Responses API。以 `gpt-5.6-sol` 为例，`.env` 可写为：

```dotenv
AZURE_OPENAI_API_KEY=replace-with-your-azure-openai-key
MODEL_PROFILES_JSON=[{"id":"fixed:test","provider":"fixed","base_url":"","model":"deterministic-test","api_key_env":"","timeout_seconds":10},{"id":"azure:gpt-5.6-sol","provider":"azure-openai-responses","base_url":"https://dxp-5099-resource.services.ai.azure.com/openai/v1","model":"gpt-5.6-sol","api_key_env":"AZURE_OPENAI_API_KEY","timeout_seconds":180,"reasoning_effort":"low","max_output_tokens":12000}]
QA_MODEL_PROFILE_ID=azure:gpt-5.6-sol
```

- Azure 门户显示的完整 Endpoint 可能以 `/openai/v1/responses` 结尾；`base_url` 只填写到 `/openai/v1`。
- `model` 必须填写 Deployment info 中的 Name。
- `azure-openai-responses` 不填写 `api_version`，不会调用旧的 deployment-scoped Chat Completions URL。
- `reasoning_effort=low` 与服务器实测的 5–16 秒单片段调用一致，可避免模型默认投入过多推理 Token。
- `max_output_tokens=12000` 为结构化抽取设置明确上限；可以按模型输出完整性继续调节。
- `QA_MODEL_PROFILE_ID` 指向该 profile 后，同一个 deployment 也用于问答意图解析。
- 原有 `azure-openai` profile 仍用于 `/chat/completions`，两种 profile 可以同时存在。

更新 `.env` 后执行以下检查：

```bash
sudo docker compose config >/dev/null
sudo docker compose up -d --build api worker
sudo docker compose exec worker printenv MODEL_PROFILES_JSON
sudo docker compose exec api printenv QA_MODEL_PROFILE_ID
sudo docker compose exec worker sh -c 'test -n "$AZURE_OPENAI_API_KEY" && echo AZURE_OPENAI_API_KEY=set'
curl -s http://localhost:5173/api/model-profiles
```

也可以在当前 Shell 已设置 `AZURE_OPENAI_API_KEY` 时直接冒烟测试端点；命令不会输出密钥：

```bash
AZURE_RESPONSES_ENDPOINT=https://dxp-5099-resource.services.ai.azure.com/openai/v1
curl --fail-with-body --silent --show-error \
  "${AZURE_RESPONSES_ENDPOINT}/responses" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${AZURE_OPENAI_API_KEY}" \
  -d '{"model":"gpt-5.6-sol","input":"只回答 OK。","store":false}'
```

预期结果：

- Compose 配置校验无错误。
- Worker 的 profile 中包含 `azure-openai-responses`、`/openai/v1` 和正确 deployment name。
- API 的 `QA_MODEL_PROFILE_ID` 等于新 profile ID。
- 密钥检查只输出 `AZURE_OPENAI_API_KEY=set`，不会显示密钥值。
- `/api/model-profiles` 中新 profile 的 `available` 为 `true`。
- 直接 smoke test 返回 HTTP 2xx，响应顶层 `status` 为 `completed`，且 `output` 中包含模型文本。
- 不要把真实密钥提交到 Git；`.env` 不应纳入版本管理。
- `AUTH_BOOTSTRAP_*` 只在管理员表为空时生效。首次登录后系统强制修改临时密码。
- 通过 HTTPS 域名部署时必须设置 `AUTH_COOKIE_SECURE=true`，然后重建 API 容器。

### 模型请求受控并发

完整小说会被拆分为多个片段。Worker 可以并发调用模型，以缩短总构建时间；并发仅作用于模型 HTTP 请求，结果仍按原文片段顺序合并，SQLite 状态更新和 Neo4j 导入仍由 Worker 主线程串行完成。

在 `.env` 中增加：

```dotenv
# 每个 Worker 进程允许同时执行的模型请求数，范围 1–16。
EXTRACTION_CONCURRENCY=4
```

建议从 `4` 开始，根据 Azure 部署的 TPM、RPM、429 比例和服务器日志逐步调节：

- `1`：完全串行，也是未配置时的默认值；
- `2`：额度较低或 429 较多时的保守配置；
- `4`：Responses 模型的推荐初始生产配置；
- 更高值会更快消耗 TPM/RPM，并不保证同比提速。

应用并验证配置：

```bash
sudo docker compose config
sudo docker compose up -d --build worker
sudo docker compose exec worker printenv EXTRACTION_CONCURRENCY
sudo docker compose logs -f worker
```

`docker compose config` 只解析并校验最终 Compose 配置，不会启动或修改容器。日志中会出现批次的 `chunks`、`concurrency`，以及每个 Azure Responses 请求的 `duration_seconds`、Token 用量和 request ID。

任务取消时，Worker 会停止提交新片段并取消尚未开始的请求。同步 HTTP 请求一旦开始不能被强制中断，因此最多仍需等待当前在途请求正常结束或达到 profile 的 `timeout_seconds`；这些结果会被丢弃，任务不会导入部分图谱。发生致命模型错误时采用相同的“停止提交、等待在途、禁止部分导入”策略。

如出现持续 429、响应延迟上升或额度压力，先回退并发度：

```dotenv
EXTRACTION_CONCURRENCY=2
```

若需完全恢复旧的串行执行方式：

```dotenv
EXTRACTION_CONCURRENCY=1
```

修改后重新构建或重建 Worker 容器即可生效。

## 5. 启动服务

```bash
docker compose up -d --build --wait
```

启动后访问：

- 前端：`http://127.0.0.1:5173/guide`
- Neo4j Browser：`http://127.0.0.1:7474`

Neo4j 登录：

- 用户名：`neo4j`
- 密码：`.env` 中的 `NEO4J_PASSWORD`

管理员入口位于页面右上角。未登录时构建、审核和管理员菜单均隐藏。首次使用 `.env` 中的管理员账号和临时密码登录，并按提示修改密码。

如果全部管理员账号均无法登录，使用交互式恢复命令重置一个已有管理员：

```bash
docker compose exec api python -m app.auth.recover admin
```

该命令不会创建新管理员，会启用目标账号、撤销其现有会话，并要求下次登录修改密码。

查看服务状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f web
docker compose logs -f neo4j
```

## 6. 验证 Azure OpenAI 配置是否生效

打开前端：

```text
http://127.0.0.1:5173/build
```

在“模型配置”下拉框中应该能看到：

```text
azure-openai · YOUR_DEPLOYMENT_NAME
```

如果该选项显示“不可用”，通常是因为：

- `MODEL_PROFILES_JSON` 中 `api_key_env` 不是 `AZURE_OPENAI_API_KEY`；
- `.env` 中没有设置 `AZURE_OPENAI_API_KEY`；
- 修改 `.env` 后没有重启 Compose 服务。

重启服务：

```bash
docker compose up -d --build --wait
```

也可以直接检查 API 返回：

```bash
curl http://127.0.0.1:5173/api/model-profiles
```

预期 Azure profile 中：

```json
{
  "provider": "azure-openai",
  "available": true
}
```

## 7. 构建一个新项目

1. 打开 `http://127.0.0.1:5173/build`；
2. 上传 TXT 小说；
3. 填写项目标题；
4. 在模型配置中选择 Azure OpenAI profile；
5. 点击“开始构建”；
6. 构建完成后进入图谱页面查看结果。

构建过程由 `worker` 调用 Azure OpenAI。Compose 会把模型密钥同时注入 `api` 和 `worker`：

- `api` 只检查对应环境变量是否存在，用于让前端显示该模型 profile 可选；
- `worker` 负责真正调用 Azure OpenAI。

## 8. 停止、升级和清理

停止服务但保留数据：

```bash
docker compose down
```

升级代码后重新构建：

```bash
git pull --ff-only origin master
docker compose up -d --build --wait
```

升级到带实体属性补抽和图谱性能优化的版本后，建议立即执行一次图谱 API 计时检查：

```bash
git pull
sudo docker compose up -d --build --wait
python3 scripts/check-graph-performance.py --base-url http://localhost:5173 --project-id xiaoao --query 令狐冲
```

输出会包含搜索 P50/P95、一度图谱、详情和二度图谱的毫秒耗时，以及被选中的实体 ID。预算超标只打印 warning，不会让脚本失败；搜索无结果或请求失败会返回非零退出码。

删除所有容器和网络但保留 volume：

```bash
docker compose down
```

删除容器、网络和数据 volume：

```bash
docker compose down -v
```

`docker compose down -v` 会删除 SQLite、上传文件和 Neo4j 数据。生产环境不要随意执行。

## 9. 备份数据

备份上传文件、SQLite 和任务状态：

```bash
mkdir -p backups
docker run --rm -v tspw-graph_app-data:/data -v "$PWD/backups:/backup" alpine \
  tar czf /backup/app-data.tgz -C /data .
```

备份 Neo4j 数据：

```bash
mkdir -p backups
docker run --rm -v tspw-graph_neo4j-data:/data -v "$PWD/backups:/backup" alpine \
  tar czf /backup/neo4j-data.tgz -C /data .
```

首次在生产项目上执行属性补抽前，必须同时备份 `tspw-graph_app-data` 和 `tspw-graph_neo4j-data` 两个 volume。属性补抽会保留已有实体、关系事实、审核状态和合并结果，只增量写入属性断言及其证据；但生产回滚仍应以 volume 备份为准。

恢复前应先停止服务：

```bash
docker compose down
```

## 10. 属性补抽与性能检查

现有项目保留原始 TXT 时，构建页会显示“重新抽取属性”：

1. 打开 `http://127.0.0.1:5173/build`；
2. 在项目切换器中选择要补抽的项目；
3. 在“属性补抽模型”中选择 Azure OpenAI profile；
4. 点击“重新抽取属性”；
5. 等待任务完成后进入图谱页，点击实体查看本体属性、关系摘要、属性证据和关系证据。

如果按钮显示“原始 TXT 不可用”，说明该项目没有可用于补抽的上传源文件，需要重新上传或恢复 `app-data` volume。

监控 Worker：

```bash
docker compose logs -f worker
```

补抽完成后可执行性能检查：

```bash
python3 scripts/check-graph-performance.py \
  --base-url http://localhost:5173 \
  --project-id xiaoao \
  --query 令狐冲
```

预期输出示例：

```text
search_p50_ms=120.0
search_p95_ms=180.0
one_hop_ms=240.0
detail_ms=360.0
two_hop_ms=520.0
entity_id=xiaoao:Person:example
```

## 11. 常见故障

### 端口被占用

现象：

```text
Bind for 0.0.0.0:7474 failed: port is already allocated
```

排查：

```bash
docker ps --format '{{.ID}} {{.Names}} {{.Ports}}'
```

处理：

- 停止占用 `5173`、`7474` 或 `7687` 的旧容器；
- 或修改 `compose.yaml` 中对应端口映射。

### Azure profile 不可用

检查 `.env`：

```bash
grep AZURE_OPENAI_API_KEY .env
grep MODEL_PROFILES_JSON .env
```

确认：

- `AZURE_OPENAI_API_KEY` 有值；
- `MODEL_PROFILES_JSON` 中 Azure profile 的 `api_key_env` 是 `AZURE_OPENAI_API_KEY`；
- 修改后已重启服务。

### Azure 返回 401 或 403

通常是密钥错误、资源 endpoint 错误，或 key 不属于该 Azure OpenAI 资源。

检查：

- `base_url` 是否是当前资源的 endpoint；
- `AZURE_OPENAI_API_KEY` 是否来自同一个资源；
- key 是否复制完整，没有多余空格。

### Azure 返回 404

通常是 deployment name 不正确。

检查：

- `MODEL_PROFILES_JSON` 中的 `model` 必须等于 Azure OpenAI deployment name；
- 不要填 `gpt-4o-mini` 这样的基础模型名，除非你的 deployment 就叫这个名字。

### Azure 返回 429 或 5xx

系统会把 429 和 5xx 视为可重试错误。可以：

- 降低并发使用；
- 换更高配额的 Azure OpenAI 部署；
- 稍后重试构建任务。

### Worker 没有处理任务

查看日志：

```bash
docker compose logs -f worker
```

确认：

- `worker` 容器是 healthy；
- `api` 和 `neo4j` 是 healthy；
- `.env` 中模型密钥配置正确。

## 12. 安全建议

- 不要把 `.env` 上传到 GitHub；
- 生产环境必须替换 `NEO4J_PASSWORD`；
- Azure OpenAI key 会作为容器环境变量注入 `api` 和 `worker`，建议定期轮换，并限制服务器登录权限；
- 如果部署到公网，建议在 Nginx、网关或云负载均衡层增加 HTTPS 和访问控制；
- 当前应用第一版不包含正式用户登录和权限控制，不建议直接裸露在公网。
