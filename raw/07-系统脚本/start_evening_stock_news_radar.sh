#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
cd "$ROOT"

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_fetch_interactive_qa.py" --write
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_evening_stock_news_radar.py" --write --notify
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_dynamic_warroom_top5.py" \
  --write \
  --apply-wiki \
  --notify \
  --force-notify
