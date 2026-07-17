# 受控信息抽取并发设计

## 背景

当前 `ExtractionPipeline` 按片段串行调用模型。服务器实测 Azure Responses
`gpt-5.6-sol` 单片段中位耗时约 14 秒，350 个片段预计需要约 92 分钟。
部署配额为 500 RPM、500,000 TPM，而串行任务只使用约 4 RPM 和
35,000–45,000 TPM，因此主要瓶颈是客户端串行执行，而不是 Azure 配额。

本设计在不改变图谱合并和导入语义的前提下，并发执行模型网络请求。

## 目标

- 通过环境变量控制单个构建任务的最大模型请求并发数。
- 完整图谱构建和属性补抽使用相同并发配置。
- 保持结果确定性，不因请求完成顺序改变图谱内容。
- 保持单片段独立重试、内容过滤处理、进度更新和取消语义。
- 致命错误或用户取消时不导入部分图谱。
- 未配置并发时保持现有串行行为。

## 非目标

- 不改造 Provider 为异步接口。
- 不启动多个 Worker 共同处理同一任务。
- 不新增片段任务表、租约或跨进程调度。
- 不实现全局 Azure 令牌桶或动态并发调节。
- 不改变文本切片大小、抽取提示词或图谱导入格式。

## 配置

`Settings` 新增：

```python
extraction_concurrency: int = Field(default=1, ge=1, le=16)
```

Docker Compose 将以下变量注入应用容器：

```dotenv
EXTRACTION_CONCURRENCY=4
```

- 默认值为 `1`，与当前串行版本兼容。
- 允许范围为 `1–16`；超出范围时应用启动配置校验失败。
- 推荐服务器初始值为 `4`。
- API 和 Worker 共享 Settings；实际并发只发生在 Worker 执行抽取时。

## 架构

### 并发边界

`ExtractionPipeline` 使用 `ThreadPoolExecutor`。工作线程只执行：

1. 构造并提交当前片段的 `ExtractionRequest`。
2. 调用现有同步 `ExtractionProvider.extract()`。
3. 执行该片段的重试、`Retry-After` 和指数退避。
4. 返回片段索引、抽取结果和重试次数。

主线程负责：

1. 接收完成的 Future。
2. 执行规则补充和结果归一化。
3. 更新已完成片段数和任务进度。
4. 暂存按片段索引标识的归一化结果。
5. 全部成功后按原文片段顺序合并实体、关系、属性、证据和拒绝项。
6. 最终一次性调用 Neo4j Importer。

SQLite 进度更新和 Neo4j 写入不在工作线程中执行，避免数据库并发写入和
线程安全问题。现有 Provider 持有的 `httpx.Client` 可被多个线程共享处理并发
HTTP 请求。

### 滑动并发窗口

Pipeline 初始最多提交 `extraction_concurrency` 个片段。每当任意 Future 完成，
主线程处理结果并补充一个尚未提交的片段，使在途请求数不超过配置值。
不会一次性向 Executor 排队全部 350 个片段，因此取消或失败后可以立即停止
派发新的模型请求。

模型响应允许乱序完成，但最终合并严格按照源片段索引进行。这样可以保持
重复实体、属性和证据合并的确定性。

## 进度语义

- Pipeline 开始时报告 `0 / total_chunks`。
- 每个片段完成模型处理后，主线程将 `completed_chunks` 加一。
- 内容过滤导致的跳过也计入已处理片段。
- 并发响应可能集中完成，因此 UI 进度可能短时间连续跳动。
- 全部成功时最终报告 `total_chunks / total_chunks`。
- Worker 在任务开始时记录总片段数和实际并发数。

`completed_chunks` 表示已经完成模型处理的片段数量，不承诺片段按编号依次
完成。

## 重试与错误处理

### 可重试错误

`408`、`409`、`429`、`5xx` 和网络错误继续使用现有单片段重试逻辑。发生重试
时只占用对应工作线程，不中断其他片段。服务返回 `Retry-After` 时优先采用，
否则使用现有指数退避。

### 内容过滤

`MODEL_CONTENT_FILTER` 继续被视为可跳过片段：

- 增加 `failed_chunks`。
- 在质量报告中记录拒绝代码。
- 更新处理进度。
- 继续派发后续片段。

### 致命错误

任意片段出现配置错误、无效响应或重试耗尽时：

1. 停止提交新片段。
2. 取消尚未开始运行的 Future。
3. 等待最多 `extraction_concurrency` 个已经发出的请求完成或超时。
4. 丢弃本任务已取得的所有片段结果。
5. 向上抛出原始错误，由 Worker 将任务标记失败。
6. 不调用 Neo4j Importer。

## 取消语义

用户取消任务时采用安全取消：

1. 主线程在派发前和每个 Future 完成后检查任务状态。
2. 一旦发现取消，停止派发新片段。
3. 取消 Executor 中尚未开始的 Future。
4. 等待最多 `extraction_concurrency` 个在途 HTTP 请求结束或达到各自超时。
5. 丢弃所有抽取结果并抛出 `PipelineCancelled`。
6. 不导入 Neo4j，任务保持 `CANCELLED`。

安全取消可能不会立即结束，因为同步 HTTP 请求无法被 Python Future 强制终止；
但最多只需等待当前并发窗口内的请求，并且不会继续消耗后续片段 Token。

## 线程安全与资源生命周期

- 单个 Pipeline 调用只创建一个 Executor，并在调用结束时关闭。
- 聚合字典、质量计数器和进度回调只由主线程修改。
- 工作线程不访问 JobRepository、ProjectRepository、UploadStore 或 GraphImporter。
- Provider 被工作线程共享；其抽取方法必须不修改请求间共享业务状态。
- 发生异常或取消时统一清理 Future 和 Executor，避免后台线程泄漏到下一任务。

## 可观测性

保留现有每次模型请求的以下日志：

- 模型、结构化输出格式和请求 ID。
- 请求耗时。
- 输入、输出、推理和总 Token。
- HTTP、网络和重试信息。

新增任务级日志：

```text
Extraction batch started project_id=... total_chunks=350 concurrency=4
Extraction batch cancelled project_id=... completed_chunks=... in_flight=...
Extraction batch failed project_id=... chunk_id=... completed_chunks=...
```

日志不得包含 API Key、完整提示词、小说原文或完整模型响应。

## 测试策略

### 配置测试

- 默认并发为 `1`。
- `EXTRACTION_CONCURRENCY=4` 被正确解析。
- `0`、负数和大于 `16` 的值被拒绝。
- Compose 将变量传入 Worker。

### Pipeline 测试

- 仪器化 Provider 证明同时在途请求不超过配置值。
- 并发为 `4` 时确实观察到多个请求同时运行。
- 并发为 `1` 时保持串行。
- 人为设置不同响应延迟，验证乱序完成后仍按源片段顺序合并。
- 进度从零开始、单调增长并最终等于总片段数。
- 单片段重试不会阻塞其他线程继续完成。
- 内容过滤只跳过对应片段。
- 致命错误停止派发、等待在途请求且不调用 Importer。
- 用户取消停止派发、等待在途请求且不调用 Importer。
- Executor 在成功、失败和取消路径均被关闭。

### 集成测试

- 完整构建使用配置的并发数。
- 属性补抽使用相同并发数。
- 质量报告中的成功、失败、调用和重试计数保持准确。

## 部署与回滚

部署后在服务器 `.env` 设置：

```dotenv
EXTRACTION_CONCURRENCY=4
```

然后校验并重建 Worker：

```bash
sudo docker compose config >/dev/null
sudo docker compose up -d --build worker
sudo docker compose exec worker printenv EXTRACTION_CONCURRENCY
sudo docker compose logs -f worker
```

若出现 Azure 429、服务器资源压力或 Provider 兼容性问题，可将配置改回：

```dotenv
EXTRACTION_CONCURRENCY=1
```

无需回滚代码即可恢复串行行为。

## 验收标准

- 并发值为 `4` 时，在日志或测试中可证明最多存在 4 个同时模型请求。
- 350 片段任务的预计总耗时显著低于串行基线，且没有新增 429 风暴。
- 任务进度持续更新并最终准确。
- 同一输入在串行与并发模式下产生相同的确定性合并结果。
- 取消和致命失败均不产生部分 Neo4j 图谱。
- 将并发设为 `1` 后行为与现有版本兼容。
