# 贡献指南

感谢参与 PersonaAgent。本指南说明本地开发方式和提交 PR 前的检查项。

## 环境准备

要求：Python 3.12 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync
cp .env.example .env
./scripts/start.sh
```

默认配置完全自包含（SQLite + mock LLM/embedding/报告 API），无需外部服务。
API 文档地址：<http://127.0.0.1:8090/docs>。

## 提交 PR 前

```bash
uv run ruff check app tests
uv run ruff format app tests
uv run mypy app
uv run pytest
```

如果修改了 Prompt、路由规则、检索阈值或链接操作，请额外运行金标评测，并确认
指标仍然达标：

```bash
uv run python -m app.eval.run
```

## 开发约定

- 阅读 `AGENTS.md` 了解架构和分层规则。
- 路由保持轻量；编排放在 `app/services`，传输细节放在 `app/api`。
- 保持 mock 优先：可选集成必须能降级到 mock，且不能在导入期加载。
- 新增配置写入 `app/core/config.py` 和 `.env.example`，并提供安全默认值。
- 修改 Prompt 时新增版本文件（如 `app/agent/prompts/<name>/v2.md`），不要原地
  重写旧版本。
- 数据库结构变更请新增 Alembic revision；不要修改已应用的迁移，并保持 MySQL
  兼容。
- 用户可见的变更请更新 `CHANGELOG.md` 的 `[未发布]` 部分。
- 不要提交 `.env`、运行时数据（`data/`、`index-artifact/`）或密钥。

## 提交信息

使用简短的祈使句主题，例如：

```text
Add feedback endpoint
Fix SSE abort cleanup
```

保持提交聚焦，避免把重构和行为变更混在一起。

## 问题反馈

请在 <https://github.com/shaanlan/PersonaAgent/issues> 提交 Issue，并附上复现
步骤。安全相关问题请按 `SECURITY.md` 的流程私下报告。
