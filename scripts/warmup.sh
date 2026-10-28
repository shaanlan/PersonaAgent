#!/usr/bin/env bash
# Warm up the service: build index + verify health endpoints (design §13.4/§8.4).
set -euo pipefail
cd "$(dirname "$0")/.."

BASE="${1:-http://127.0.0.1:8090}"

echo "==> building index"
uv run python -m app.rag.ingest --mock >/dev/null

echo "==> healthz"
curl -fsS "${BASE}/healthz"
echo

echo "==> readyz"
curl -fsS "${BASE}/readyz"
echo
echo "warmup ok"
