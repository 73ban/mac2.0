#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
DATE="$(date +%F)"

cd "$ROOT"

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_dynamic_warroom_top5.py" \
  --date "$DATE" \
  --write \
  --apply-wiki \
  --notify

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_dynamic_warroom_evolution.py" \
  --date "$DATE" \
  --write

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_intraday_minute_watch.py" \
  --date "$DATE" \
  --write \
  --apply-wiki

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_intraday_alert_validation.py" \
  --date "$DATE" \
  --write

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_feishu_task_inbox.py" \
  --date "$DATE" \
  --write

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_feishu_protocol_lint.py" \
  --write
