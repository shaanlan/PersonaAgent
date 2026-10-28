# 更新日志

本文件记录项目的所有重要变更。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [未发布]

## [0.1.0] - 2026-10-28

### 新增

- FastAPI 应用：类型化配置、结构化日志、请求 ID、统一错误处理，以及本地开发
  用的 CORS。
- `/api/v1/chat` 对话 API：创建/列出/删除会话、列出消息、SSE 流式对话、中止
  生成、登录后绑定匿名会话、提交消息反馈。
- LangGraph `StateGraph` 流程：`load_context -> route -> (guardrail |
  personal_report) -> retrieve -> generate -> finalize`，包含查询改写重试
  循环；不使用 checkpointer（每轮从数据库重建状态）。
- 流式事件契约 `meta -> sources -> actions -> token* -> done | error`，支持
  心跳，以及中止时保留已生成内容。
- 会话访问控制：Bearer JWT（开发环境可用 `mock:<uid>`）或
  `X-Chat-Session-Token`，并支持可选的内部服务令牌。
- 限流：会话创建、消息发送、并发流（全局 / 按 IP / 按 uid），阈值可配置。
- RAG 流程：扫描、清洗、切分、嵌入、存储、检索，支持快照/目录清单，默认使用
  mock 语料。
- 可插拔适配器：mock/litellm LLM、mock/ollama/OpenAI 兼容 embedding、从 Go
  报告 API 降级到 mock 的报告客户端。
- 性格报告注入、受控操作与推荐问题，并对返回链接做 URL 白名单校验。
- `chat_sessions`、`chat_messages`、`chat_feedback` 的 Alembic 迁移（兼容
  SQLite 和 MySQL）。
- 金标评测脚本（`app.eval.run`），覆盖意图准确率、Recall@5 和链接有效率。
- Dockerfile、基础/本地/生产 Compose 配置、健康检查/就绪检查端点，以及
  `start`、`ingest`、`warmup` 辅助脚本。
- 单元与集成测试：路由、操作、意图、安全、限流、检索、SSE 和 API 流程。
- 独立示例：零依赖状态机版和 LangGraph 教学版。

[未发布]: https://github.com/shaanlan/PersonaAgent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/shaanlan/PersonaAgent/releases/tag/v0.1.0
