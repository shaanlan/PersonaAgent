# PersonaAgent persona-chat service
#
# Build:   docker build -t persona-chat .
# Run:     docker run --env-file .env -p 8090:8090 persona-chat
# Compose: docker compose up -d   （本地测试见 README 部署章节）
#
# 与 docs/design.md §13.3 示例的差异（对齐已实现代码）：
#   1. python:3.11-slim -> 3.12-slim（pyproject requires-python >= 3.12）
#   2. 删除 `COPY prompts`（Prompt 内置于 app/agent/prompts/，仓库无根级 prompts/）
#   3. 先 COPY app 再 uv sync（项目是 hatchling package，打包需要 app/ 存在）
#   4. --extra mysql --extra llm（asyncmy / litellm 是 optional extras；chromadb 按需另装）
#   5. uv run --no-sync（容器内不二次 sync，运行时无需网络）

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1

# curl 供 compose healthcheck 使用
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev --extra mysql --extra llm

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8090/healthz || exit 1

CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8090", "--workers", "1"]
