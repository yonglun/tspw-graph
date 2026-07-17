# Azure Responses 性能控制与诊断设计

## 背景

服务器实测同一 3984 字片段在 Azure Responses API 使用低推理时分别耗时
4.96 秒和 16.29 秒，但正式构建中单片段可能超过 5 分钟。当前正式请求未设置
推理强度和最大输出 Token，同时网络错误与流水线重试没有日志。180 秒超时配合
两次静默重试，能够产生约 6 分钟的不可见等待。

## 目标

- 允许每个模型档案独立设置 Responses API 的推理强度和最大输出 Token。
- 为 `gpt-5.6-sol` 示例配置低推理和 12000 输出 Token 上限。
- 记录每次请求的耗时、请求 ID、Token 用量、状态与格式名称。
- 明确记录网络错误、HTTP 错误以及流水线重试次数和等待时间。
- 保持现有模型档案向后兼容，不改变分片大小、串行语义和图谱导入流程。

## 配置契约

`ModelProfileSettings` 新增两个可选字段：

- `reasoning_effort`: Responses API 推理强度；省略时不发送 `reasoning`。
- `max_output_tokens`: 正整数；省略时不发送 `max_output_tokens`。

`azure-openai-responses` 示例使用：

```json
{
  "reasoning_effort": "low",
  "max_output_tokens": 12000
}
```

其他 provider 会解析并保留这两个字段，但不会使用它们。

## 请求与日志

共享的 `AzureResponsesClient` 接收上述可选配置，并在请求体中按需加入：

```json
{
  "reasoning": {"effort": "low"},
  "max_output_tokens": 12000
}
```

成功日志包含模型、结构化输出格式、耗时、响应状态、请求 ID 和 usage。HTTP
失败日志增加耗时和请求 ID；网络失败日志包含错误类型和耗时。日志不得包含 API
Key、提示词、小说正文或完整模型响应。

流水线在可重试错误发生时记录片段 ID、错误码、当前重试次数、最大重试次数和
等待秒数；重试耗尽时记录明确的失败日志。

## 兼容性与风险控制

- 两个新增字段均为可选，旧 `.env` 无需立即修改即可启动。
- 不开启并发，避免在尚未量化单次调用前触发 RPM/TPM 限流。
- 不缩短 180 秒超时；低推理和输出上限先减少正常请求时延，日志负责揭示异常请求。
- 抽取与问答共用同一模型档案，因此两条 Responses 调用路径采用相同控制参数。

## 验证

- 请求体在配置存在时包含低推理和输出上限，不存在时保持原契约。
- 配置字段执行合法性校验。
- 成功、HTTP 失败、网络失败与流水线重试均有可诊断日志，且不泄露密钥。
- Azure Responses、provider registry、QA 和 pipeline 相关测试全部通过。
