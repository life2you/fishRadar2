#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[radar-probe] starting execution worker"
echo "[radar-probe] queue backend: ${QUEUE_BACKEND:-mysql}"
echo "[radar-probe] redis url: ${REDIS_URL:-redis://127.0.0.1:6379/0}"
echo "[radar-probe] queue name: ${REDIS_QUEUE_NAME:-fishradar2:worker_jobs}"
echo "[radar-probe] event channel: ${REDIS_EVENT_CHANNEL:-fishradar2:events}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[radar-probe] python binary not found: $PYTHON_BIN" >&2
  exit 1
fi

exec "$PYTHON_BIN" tools/worker_job_runner.py
