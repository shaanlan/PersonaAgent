# PersonaAgent

persona-chat 后端服务：基于站内内容的受控 MBTI 对话 Agent（FastAPI + LangGraph）。

技术设计见 [docs/design.md](docs/design.md)，产品需求见 [docs/requirement.md](docs/requirement.md)。

## 快速开始（零外部依赖）

```bash
uv sync                    # 安装依赖（Python 3.12，dev 组默认安装）
./scripts/start.sh           # 或: uv run uvicorn app.main:app --port 8090
```

打开 <http://127.0.0.1:8090/docs> 查看 API。默认配置下**不需要** MySQL / Ollama / Chroma：

| 组件 | 默认 | 生产切换方式 |
|---|---|---|
| 数据库 | SQLite（`data/persona_chat.db`） | `DATABASE_URL=mysql+asyncmy://...` + `uv sync --extra mysql` |
| LLM | `LLM_PROVIDER=mock` 模板流式回答 | `LLM_PROVIDER=litellm` + `uv sync --extra llm` + 模型配置 |
| 向量库 | 内存 + mock 语料（启动时自动构建） | `uv sync --extra rag` + `EMBEDDING_PROVIDER=ollama` |
| 报告 API | `PERSONALITY_API_BASE_URL=` 空 → mock 报告 | 填入 Go API 地址 |

## 常用命令

```bash
uv run alembic upgrade head        # 数据库迁移（生产用；开发默认 DB_AUTO_CREATE=true）
uv run pytest                      # 单元 + 集成测试
uv run python -m app.eval.run      # 金标评测：意图准确率 / Recall@5 / 链接有效率
uv run ruff check app && uv run ruff format app
uv run mypy app
./scripts/ingest.sh                # 构建 mock 索引；或传入内容快照目录
```

## 部署（Docker Compose）

Compose 文件与启动顺序按 [docs/design.md](docs/design.md) §13.2/§13.3 落地；`Dockerfile` 有 5 处对齐性修改，见其头部注释。

### 本地冒烟（SQLite + mock，最省事）

```bash
cp .env.example .env
docker compose up -d --build
curl -s http://127.0.0.1:8090/readyz
```

### 本地 overlay（MySQL + Ollama，design §13.2.2）

```bash
cp .env.example .env
# 按 .env.example 末尾说明改：MYSQL_HOST=mysql、设 MYSQL_PASSWORD / MYSQL_ROOT_PASSWORD，
# 需要真实模型时再切 LLM_PROVIDER=litellm + LLM_API_BASE=http://ollama:11434
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
# Ollama 首次需要：docker compose exec ollama ollama pull qwen2.5:3b-instruct && ... pull bge-m3
```

### 生产（外部 MySQL，design §13.3 启动顺序）

1. 预构建镜像（不在运行节点 build）：`docker build -t persona-chat:<version> .` 并推到制品库；
2. `.env`：`APP_ENV=production`、`AUTH_JWT_SECRET`、`DATABASE_URL`/`MYSQL_HOST`、`LLM_*`、`PERSONALITY_API_BASE_URL`，`DB_AUTO_CREATE=false`；
3. 迁移在应用外执行：`uv run alembic upgrade head`；
4. 索引产物解压到 `INDEX_ARTIFACT_DIR`（mock 模式可跳过，启动时自动建内存索引）；
5. `docker compose up -d persona-chat` → `/readyz` 通过后接入 Nginx（SSE 配置见 design §12.5）。

双节点（新节点只跑 persona-chat）、Nginx upstream、systemd 非 Docker 部署：见 design §13.2.3 / §13.9 / §13.10。

## 架构

```text
POST /sessions/{id}/messages:stream
  → 鉴权/限流/幂等校验，写入 user + assistant(pending) 消息
  → LangGraph StateGraph（无 checkpointer，按设计 §3.4 每次从 DB 重建状态）
      load_context → route ──┬─ guardrail ─────────────────→ finalize
                             ├─ load_personal_report → retrieve
                             └─ retrieve ──┬─ generate ─────────→ finalize
                                           └─ rewrite_query → retrieve
  → SSE: meta → sources → actions → token* → done | error
```

代码分层（设计 §四）：

```text
app/
├── api/          # 路由、鉴权依赖、SSE broker（传输层，无业务逻辑）
├── core/         # config / logging / errors / security / rate_limit / intents
├── db/           # SQLAlchemy 模型 + repository
├── schemas/      # Pydantic 契约（chat / intent / sse）
├── agent/        # ChatState、7 节点、条件边、3 个受控工具、版本化 Prompt
├── rag/          # 扫描/清洗/切分/嵌入/存储/检索/ingest CLI + mock 语料
├── llm/          # LLMClient 协议 + mock / litellm 实现 + 角色路由
├── services/     # chat_service（编排+流）、session_service、报告客户端
└── eval/         # golden.jsonl + 评测脚本
migrations/       # Alembic（chat_sessions / chat_messages / chat_feedback）
tests/            # 单元（路由/白名单/限流/检索）+ 集成（API/SSE/鉴权矩阵）
```

## 示例与文档

- `examples/persona_agent_demo/`：零依赖手写状态机版，用于逐步理解 Agent 流程（`python3 server.py`，端口 8090）
- `examples/langgraph_version/`：LangGraph 教学版（`uv run uvicorn app:app --app-dir examples/langgraph_version --port 8091`）
- 两者与本服务互不影响，可同时运行

## 与设计文档的已知差异

1. **流式事件注入**：设计 §5.7 用 contextvars 注入 StreamBroker，但 LangGraph 1.x 异步节点不传播 contextvars，改用官方 `get_stream_writer()`（`stream_mode="custom"`），效果等价。
2. **SQLite 默认**：开发环境无 MySQL，Alembic 迁移与模型类型保持 MySQL 兼容，生产改 `DATABASE_URL` 即可。
3. **mock 默认**：LLM/embedding/报告 API 均为可插拔适配器，缺依赖时降级为 mock，保证开箱即跑。
