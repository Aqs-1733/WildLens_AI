#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$PROJECT_ROOT/storage/pids/speciesnet_api.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "SpeciesNet API PID file not found; nothing to stop"
  exit 0
fi

PID="$(cat "$PID_FILE" || true)"
if [[ -z "$PID" ]]; then
  rm -f "$PID_FILE"
  echo "SpeciesNet API PID file was empty"
  exit 0
fi

if ! kill -0 "$PID" 2>/dev/null; then
  rm -f "$PID_FILE"
  echo "SpeciesNet API process $PID is not running"
  exit 0
fi

COMMAND="$(ps -p "$PID" -o args= || true)"
if [[ "$COMMAND" != *"services.speciesnet_api.app"* ]]; then
  echo "Refusing to stop PID $PID because it is not the SpeciesNet API: $COMMAND" >&2
  exit 1
fi

kill "$PID"
for _ in $(seq 1 30); do
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "Stopped SpeciesNet API PID $PID"
    exit 0
  fi
  sleep 1
done

echo "SpeciesNet API PID $PID did not stop after SIGTERM; sending SIGKILL"
kill -9 "$PID" 2>/dev/null || true
rm -f "$PID_FILE"

