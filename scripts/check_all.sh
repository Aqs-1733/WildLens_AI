#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT/storage/pids"

check_tool() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "[ok] $1 -> $(command -v "$1")"
  else
    echo "[missing] $1"
  fi
}

check_pid() {
  local name="$1"
  local pid_file="$PID_DIR/$name.pid"
  if [[ ! -f "$pid_file" ]]; then
    echo "[idle] $name has no PID file"
    return
  fi
  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[ok] $name running PID $pid"
  else
    echo "[stale] $name PID $pid not running"
  fi
}

cd "$ROOT"
for tool in uv python node pnpm ffmpeg ffprobe; do check_tool "$tool"; done
for name in backend worker frontend; do check_pid "$name"; done

[[ -f .env ]] && echo "[ok] .env present" || echo "[info] .env absent; defaults and .env.example are used"
for path in storage/uploads storage/results storage/reports storage/logs models/registry models/checkpoints; do
  [[ -e "$path" ]] && echo "[ok] $path" || echo "[missing] $path"
done

if command -v curl >/dev/null 2>&1; then
  curl -fsS http://127.0.0.1:8010/api/health >/dev/null && echo "[ok] backend health" || echo "[warn] backend health unavailable"
  curl -fsS http://127.0.0.1:5174 >/dev/null && echo "[ok] frontend" || echo "[warn] frontend unavailable"
fi
