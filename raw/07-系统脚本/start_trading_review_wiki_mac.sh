#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/Users/qixinchaye/Workspace/trading-review-wiki-ymj-integrated"
PROJECT_ROOT="/Users/qixinchaye/wiki/73神话"

cd "${APP_DIR}"
export WIKI_PROJECT_PATH="${PROJECT_ROOT}"
exec npm run dev
