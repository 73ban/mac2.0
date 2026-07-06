#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
DATE="$(date +%F)"

cd "$ROOT"

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_shortline_mode_dictionary_scan.py"
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_mode_page_lint.py"
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_mode_page_structure_backfill.py"
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_mode_page_lint.py"
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_trade_mode_attribution_audit.py"
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_trade_mode_attribution_enrich.py" --limit 999 --write
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_trade_mode_dplus_bridge.py" --write
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_trade_mode_bigday_review.py"
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_feishu_protocol_lint.py" --write
/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_longrun_execution_dashboard.py"

printf '{"ok":true,"date":"%s","task":"shortline_mode_dictionary_scan"}\n' "$DATE"
