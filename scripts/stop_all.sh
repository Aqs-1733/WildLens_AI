#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$ROOT/storage/pids"

stop_one() {
  local name="$1"
  local pid_file="$PID_DIR/$name.pid"
  if [[ ! -f "$pid_file" ]]; then
    echo "$name is not managed."
    return
  fi
  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid"
    echo "$name stopped (PID $pid)."
  else
    echo "$name PID $pid is not running."
  fi
  rm -f "$pid_file"
}

stop_one frontend
stop_one worker
stop_one backend
