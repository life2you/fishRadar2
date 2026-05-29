#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[worker-py] starting execution worker"
echo "[worker-py] queue backend: ${QUEUE_BACKEND:-mysql}"
echo "[worker-py] redis url: ${REDIS_URL:-redis://127.0.0.1:6379/0}"
echo "[worker-py] queue name: ${REDIS_QUEUE_NAME:-fishradar2:worker_jobs}"
echo "[worker-py] event channel: ${REDIS_EVENT_CHANNEL:-fishradar2:events}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[worker-py] python binary not found: $PYTHON_BIN" >&2
  exit 1
fi

exec "$PYTHON_BIN" tools/worker_job_runner.py
