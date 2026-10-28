# AGENTS.md

面向在本仓库工作的编码 Agent 的说明。

## 项目是什么

`persona-chat`：一个受控 MBTI 对话助手的后端服务，基于 FastAPI + LangGraph。
通过 SSE 流式返回答案，用站内内容做 RAG  grounding，并可注入用户的性格报告。

- 行为的唯一事实来源：`docs/design.md`（技术）与 `docs/requirement.md`（产品）。
  修改行为前先读相关章节；README 记录了与设计文档的已知差异。
- `docs/ref/` 是上游前端/后端/内容设计文档，仅供参考。

## 环境

- Python **3.12**（见 `.python-version`），依赖管理使用 **uv**。
- 默认配置**不依赖任何外部服务**：SQLite、mock LLM、mock embedding、内存
  Chroma、mock 报告 API。必须保持这条零依赖路径可用。
- 不要提交 `.env`；新增配置项时同步更新 `.env.example`。
- 运行时产物（`data/`、`index-artifact/`）已加入 gitignore。

## 常用命令

```bash
uv sync                              # 安装依赖（默认包含 dev 组）
./scripts/start.sh                   # 在 127.0.0.1:8090 启动
uv run pytest                        # 单元 + 集成测试
uv run pytest tests/unit -q          # 快速子集
uv run python -m app.eval.run        # 金标评测（意图 / Recall@5 / 链接）
uv run ruff check app tests          # 静态检查
uv run ruff format app tests         # 格式化（不要手工格式化）
uv run mypy app                      # 类型检查
uv run alembic upgrade head          # 执行数据库迁移
./scripts/ingest.sh [snapshot_dir]   # 重建检索索引
```

完成任务前运行 `ruff check`、`ruff format`、`mypy app` 和 `pytest`。
可选依赖：`uv sync --extra mysql`、`--extra llm`、`--extra rag`。

## 目录结构

```text
app/api/       路由、鉴权依赖、SSE 传输
app/core/      配置、日志、错误、安全、限流、意图、i18n
app/db/        SQLAlchemy 模型、会话、Repository
app/schemas/   Pydantic 请求/响应契约
app/agent/     ChatState、LangGraph 节点/边、工具、版本化 Prompt
app/rag/       扫描 -> 清洗 -> 切分 -> 嵌入 -> 存储 -> 检索
app/llm/       LLMClient 协议 + mock/litellm 适配器 + 模型路由
app/services/  业务编排（chat/session/报告客户端）
app/eval/      golden.jsonl + 评测脚本
migrations/    Alembic；测试在 tests/{unit,integration}
```

## 约定

- 保持现有分层：路由保持轻量；编排放在 `app/services`；传输细节留在
  `app/api`。
- 全异步（`async def`、SQLAlchemy async session），不要新增同步数据库调用。
- 配置统一放在 `app/core/config.py`（`pydantic-settings`，环境变量驱动）。
  新增配置时同时更新 `.env.example`，并提供安全默认值。
- Pydantic 模型定义对外契约；不要直接返回 ORM 行对象。
- Prompt 是 `app/agent/prompts/<name>/v1.md` 下的版本化文件。需要改动时新增
  版本文件（如 `v2.md`），不要原地重写；同时更新 `PROMPT_VERSION`/加载逻辑。
- LLM、embedding、报告接口都是带 mock 兜底的适配器：不要让可选依赖在导入期
  变成必需依赖。
- SSE 事件顺序是契约的一部分（`meta -> sources -> actions -> tokens* ->
  done | error`）。LangGraph 异步节点不会传播 contextvars，自定义事件请用
  `get_stream_writer()`。
- Ruff：行宽 120，规则 `E,F,I,UP,B`（忽略 `B008`）。Mypy：
  `check_untyped_defs`、`no_implicit_optional`。
- 除非解释非显而易见的约束，否则不要加注释；公共服务/路由行为保留 docstring。
- 迁移：新增 Alembic revision（不要修改已应用的迁移），同时兼容 MySQL 与
  SQLite。
- 测试：`tests/conftest.py` 会设置测试环境变量并提供 `app`、`client`、
  `session_headers`、`read_sse`。开发时可用 `mock:<uid>` Bearer token。
- `examples/` 下是独立的教学代码，不要让主应用依赖它们。

## 注意事项

- `DB_AUTO_CREATE=true` 只建表，不做迁移。生产环境设为 `false`，并在应用外
  执行 `alembic upgrade head`。
- 本地 SQLite 文件在 `data/persona_chat.db`；删除即可重置开发数据。
- 限流是进程内全局状态；测试通过 fixture 重置。
- 如果修改了 Prompt 文案、检索阈值或路由规则，请运行评测确认金标指标。
