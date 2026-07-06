#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/qixinchaye/wiki/73神话"
cd "$ROOT"

/usr/bin/python3 "$ROOT/raw/07-系统脚本/codex_fetch_interactive_qa.py" --write "$@"
