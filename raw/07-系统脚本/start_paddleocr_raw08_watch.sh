#!/bin/bash
set -u

ROOT="/Users/qixinchaye/wiki/73神话"
LOCK_DIR="$ROOT/.system/locks/paddleocr-raw08.lock"
LOG_DIR="$ROOT/.system/logs"

mkdir -p "$LOG_DIR" "$ROOT/.system/locks"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') paddleocr raw08 already running"
  exit 0
fi

cleanup() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

cd "$ROOT" || exit 1

echo "$(date '+%Y-%m-%d %H:%M:%S') paddleocr raw08 scan start"
python3 raw/07-系统脚本/codex_paddleocr_raw08.py --limit 20
status=$?
echo "$(date '+%Y-%m-%d %H:%M:%S') paddleocr raw08 scan end status=$status"
exit "$status"
