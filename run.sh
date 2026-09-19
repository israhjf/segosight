#!/usr/bin/env bash
# One command from clone to running.
#
#   ./run.sh          build the UI, build the warehouse if absent, serve on :8000
#   ./run.sh dev      API on :8000 plus the Vite dev server on :5173
#
# The API owns the DuckDB write lock, so the pipeline runs inside it rather
# than as a second process -- which is why "Ingest data" is a button.
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
[ -x "$PY" ] || { echo "Creating venv..."; python3 -m venv .venv; }
$PY -m pip install -q -r requirements.txt

if [ ! -f warehouse/segosight.duckdb ]; then
  echo "Building the warehouse (first run)..."
  $PY -m segosight.pipeline
fi

if [ "${1:-serve}" = "dev" ]; then
  echo "API      -> http://127.0.0.1:8000"
  echo "UI (dev) -> http://127.0.0.1:5173"
  $PY -m uvicorn segosight.api.app:app --reload --port 8000 &
  trap 'kill 0' EXIT
  (cd ui && pnpm install --silent && pnpm run dev)
else
  if [ ! -d ui/dist ]; then
    echo "Building the UI..."
    (cd ui && pnpm install --silent && pnpm run build)
  fi
  echo "SegoSight -> http://127.0.0.1:8000"
  exec $PY -m uvicorn segosight.api.app:app --port 8000
fi
