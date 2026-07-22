#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${SPECIESNET_API_PYTHON:-/root/autodl-tmp/speciesnet-venv/bin/python}"
HOST="${SPECIESNET_API_HOST:-127.0.0.1}"
PORT="${SPECIESNET_API_PORT:-8101}"
PID_DIR="$PROJECT_ROOT/storage/pids"
LOG_DIR="$PROJECT_ROOT/storage/logs"
PID_FILE="$PID_DIR/speciesnet_api.pid"
LOG_FILE="$LOG_DIR/speciesnet_api.log"

mkdir -p "$PID_DIR" "$LOG_DIR" "$PROJECT_ROOT/storage/speciesnet_cache"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "SpeciesNet Python not found or not executable: $PYTHON_BIN" >&2
  exit 1
fi

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "SpeciesNet API is already running with PID $OLD_PID"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export SPECIESNET_API_HOST="$HOST"
export SPECIESNET_API_PORT="$PORT"
export SPECIESNET_CACHE_DIR="${SPECIESNET_CACHE_DIR:-$PROJECT_ROOT/storage/speciesnet_cache}"

nohup "$PYTHON_BIN" -m uvicorn services.speciesnet_api.app:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers 1 \
  >>"$LOG_FILE" 2>&1 &

PID="$!"
echo "$PID" >"$PID_FILE"
echo "Started SpeciesNet API PID $PID at http://$HOST:$PORT"

for _ in $(seq 1 120); do
  if "$PYTHON_BIN" - <<PY >/dev/null 2>&1
import json, urllib.request
with urllib.request.urlopen("http://$HOST:$PORT/health", timeout=2) as response:
    data = json.load(response)
    raise SystemExit(0 if data.get("model_loaded") else 1)
PY
  then
    echo "SpeciesNet API health check passed"
    exit 0
  fi
  sleep 2
done

echo "SpeciesNet API did not become healthy. See $LOG_FILE" >&2
exit 1

