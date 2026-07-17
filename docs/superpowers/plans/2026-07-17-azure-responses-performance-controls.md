# Azure Responses 性能控制实施计划

1. 为 `ModelProfileSettings` 增加可选的 `reasoning_effort` 与
   `max_output_tokens`，先用配置测试锁定解析和校验行为。
2. 为 `AzureResponsesClient` 增加失败测试，覆盖请求参数、成功诊断日志与网络
   错误日志。
3. 将配置从 provider registry 传递到抽取和问答的共享 Responses 客户端。
4. 为流水线增加失败测试，覆盖重试调度与重试耗尽日志，然后实现日志。
5. 更新 `.env.example` 与 Docker Azure 部署手册中的 `gpt-5.6-sol` 示例。
6. 运行定向测试、API 全量测试和格式检查，审查差异与敏感信息风险。
