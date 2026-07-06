#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
DATE="$(date +%F)"

cd "$ROOT"
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_daily_master_dashboard.py" --date "$DATE"
