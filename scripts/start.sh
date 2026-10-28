#!/usr/bin/env bash
# Start the persona-chat service (dev).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  echo "==> creating uv environment"
  uv sync
fi

if [ ! -f data/persona_chat.db ]; then
  echo "==> running migrations"
  uv run alembic upgrade head
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8090}"
echo "==> serving on http://${HOST}:${PORT}"
exec uv run uvicorn app.main:app --host "${HOST}" --port "${PORT}"
