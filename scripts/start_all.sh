#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/storage/logs"
PID_DIR="$ROOT/storage/pids"
mkdir -p "$LOG_DIR" "$PID_DIR" "$ROOT/storage/uploads" "$ROOT/storage/results" "$ROOT/storage/reports" "$ROOT/storage/annotated" "$ROOT/storage/playback" "$ROOT/storage/outputs" "$ROOT/models/registry" "$ROOT/models/checkpoints"

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
}

live_pid() {
  local file="$1"
  [[ -f "$file" ]] && kill -0 "$(cat "$file")" >/dev/null 2>&1
}

start_managed() {
  local name="$1"; shift
  local pid_file="$PID_DIR/$name.pid"
  if live_pid "$pid_file"; then
    echo "$name already running with PID $(cat "$pid_file")"
    return
  fi
  (cd "$ROOT" && nohup "$@" >"$LOG_DIR/$name.console.log" 2>"$LOG_DIR/$name.error.log" & echo $! >"$pid_file")
  echo "$name started with PID $(cat "$pid_file")"
}

need uv
need python
need node
need pnpm
need ffmpeg
need ffprobe

cd "$ROOT"
uv sync --extra bioclip
uv run python scripts/migrate_db.py

start_managed backend uv run python backend/main.py
start_managed worker uv run python scripts/worker.py
(cd "$ROOT/frontend" && if [[ ! -d node_modules ]]; then pnpm install; fi)
if live_pid "$PID_DIR/frontend.pid"; then
  echo "frontend already running with PID $(cat "$PID_DIR/frontend.pid")"
else
  (cd "$ROOT/frontend" && nohup pnpm dev >"$LOG_DIR/frontend.console.log" 2>"$LOG_DIR/frontend.error.log" & echo $! >"$PID_DIR/frontend.pid")
  echo "frontend started with PID $(cat "$PID_DIR/frontend.pid")"
fi

echo
echo "识境 is starting."
echo "Frontend: http://127.0.0.1:5174"
echo "API docs: http://127.0.0.1:8010/docs"
echo "Health: http://127.0.0.1:8010/api/health"
echo "Logs: $LOG_DIR"
