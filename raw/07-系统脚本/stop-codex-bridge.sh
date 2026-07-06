#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
PID_FILE="$ROOT/.system/codex-bridge.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "codex bridge pid file not found"
  exit 0
fi

pid="$(cat "$PID_FILE" || true)"
if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  echo "codex bridge stopped: $pid"
else
  echo "codex bridge not running"
fi
rm -f "$PID_FILE"
