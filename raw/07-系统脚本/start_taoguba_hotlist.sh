#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
SCRIPT="$ROOT/raw/07-系统脚本/codex_fetch_taoguba_hotlist.py"
EMOTION_SCRIPT="$ROOT/raw/07-系统脚本/codex_taoguba_emotion_cycle.py"
MERGE_SCRIPT="$ROOT/raw/07-系统脚本/codex_merge_three_hotlists.py"
DATE="$(date +%F)"
SLOT="$(date +%H%M)"

cd "$ROOT"

/usr/bin/python3 "$SCRIPT" --date "$DATE" --slot "$SLOT" --limit 100
/usr/bin/python3 "$EMOTION_SCRIPT" --date "$DATE" --slot "$SLOT"
/usr/bin/python3 "$MERGE_SCRIPT" --date "$DATE" --tgb-slot "$SLOT"
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_shortline_mode_dictionary_scan.py"
