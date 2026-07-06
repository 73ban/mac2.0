#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
SCRIPT="$ROOT/raw/07-系统脚本/codex-openai-compatible-bridge.mjs"
LOG_DIR="$ROOT/.system/logs"
PID_FILE="$ROOT/.system/codex-bridge.pid"

mkdir -p "$LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "codex bridge already running: $old_pid"
    exit 0
  fi
fi

nohup node "$SCRIPT" >> "$LOG_DIR/codex-bridge.log" 2>&1 &
echo $! > "$PID_FILE"
echo "codex bridge started: $(cat "$PID_FILE")"
