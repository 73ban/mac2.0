#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
DATE="$(date +%F)"
ARTICLES="${JYG_ARTICLES:-20}"

cd "$ROOT"

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_firecrawl_jiuyangongshe_fetch.py" \
  --date "$DATE" \
  --default-frontpages \
  --discover-articles "$ARTICLES" \
  --focus-current-warroom \
  --focus-articles-per-stock 3 \
  --category frontpage

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_jiuyangongshe_focus_to_wiki.py" \
  --date "$DATE" \
  --write

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_daily_important_info_top10.py" \
  --date "$DATE" \
  --write

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_dynamic_warroom_top5.py" \
  --date "$DATE" \
  --write \
  --apply-wiki \
  --notify

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_dynamic_warroom_evolution.py" \
  --date "$DATE" \
  --write

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_feishu_protocol_lint.py" \
  --write
