#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
DATE="$(date +%F)"

cd "$ROOT"

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_fetch_interactive_qa.py" --write
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_interactive_qa_to_wiki.py" --date "$DATE"
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_daily_important_info_top10.py" --date "$DATE" --write
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_evening_stock_news_radar.py" --write --notify
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_dynamic_warroom_top5.py" --write --apply-wiki --notify
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_warroom_mode_feedback.py"
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_feishu_noise_control.py"

printf '{"ok":true,"date":"%s","task":"evening_holding_warroom_closed_loop"}\n' "$DATE"
