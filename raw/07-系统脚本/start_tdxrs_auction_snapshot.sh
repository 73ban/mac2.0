#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
PY="$ROOT/.system/venv-tdxrs/bin/python"
SCRIPT="$ROOT/raw/07-系统脚本/codex_fetch_tdxrs_auction_snapshot.py"

cd "$ROOT"

exec "$PY" "$SCRIPT" \
  --session \
  --include-detail \
  --limit 100
