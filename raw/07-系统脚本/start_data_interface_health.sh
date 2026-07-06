#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
DATE="$(date +%F)"

cd "$ROOT"
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_rotate_system_logs.py" \
  --max-mb 5 \
  --keep 7 \
  --quiet

if ! /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_ocr_healthcheck.py" --write; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN ocr healthcheck failed"
fi

STATUS=0
if /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_data_interface_control.py" \
  --date "$DATE" \
  --write; then
  :
else
  STATUS=$?
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN data interface health failed"
fi

if ! /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_raw_ingest_health_dashboard.py" \
  --date "$DATE" \
  --write; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN raw ingest health dashboard failed"
fi

if ! /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_raw_to_wiki_action_planner.py" \
  --date "$DATE" \
  --write; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN raw to wiki action planner failed"
fi

if ! /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_second_catalyst_radar.py" \
  --date "$DATE" \
  --days 2 \
  --write \
  --apply-wiki \
  --max-apply 20; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN second catalyst radar failed"
fi

if ! /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_interactive_qa_to_wiki.py" \
  --date "$DATE" \
  --write \
  --apply-wiki \
  --max-apply 40; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN interactive qa to wiki failed"
fi

if ! /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_daily_important_info_top10.py" \
  --date "$DATE" \
  --write \
  --notify; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN daily important info top10 failed"
fi

if ! /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_dynamic_warroom_top5.py" \
  --date "$DATE" \
  --write \
  --apply-wiki \
  --notify; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN dynamic warroom top5 failed"
fi

if ! /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_dynamic_warroom_evolution.py" \
  --date "$DATE" \
  --write; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN dynamic warroom evolution failed"
fi

if ! /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_shortline_learning_progress.py" \
  --date "$DATE" \
  --write \
  --notify; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN shortline learning progress failed"
fi

if ! /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_feishu_protocol_lint.py" \
  --write; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN feishu protocol lint failed"
fi

if ! /usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_automation_watchdog.py" \
  --date "$DATE" \
  --write \
  --notify; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') WARN automation watchdog failed"
fi

exit "$STATUS"
