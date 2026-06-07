#!/bin/bash
set -e

PORT="${PORT:-8000}"
WORKERS="${WORKERS:-2}"
LOG_LEVEL="${LOG_LEVEL:-info}"

exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL"
