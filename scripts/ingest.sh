#!/usr/bin/env bash
# Build the search index.
#   scripts/ingest.sh                 # built-in mock corpus
#   scripts/ingest.sh /path/snapshot  # content snapshot (Markdown/JSON)
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$#" -ge 1 ]; then
  exec uv run python -m app.rag.ingest --snapshot "$1" --out "${2:-./index-artifact}"
else
  exec uv run python -m app.rag.ingest --mock
fi
