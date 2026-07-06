#!/usr/bin/env bash
set -euo pipefail

WEKNORA_DIR="/Users/qixinchaye/Workspace/ymj8903668-droid-open-source/WeKnora"
MODE="${1:-lite}"
export PATH="/Users/qixinchaye/.local/bin:/Applications/Docker.app/Contents/Resources/bin:${PATH}"

cd "${WEKNORA_DIR}"

case "${MODE}" in
  lite)
    if [ ! -x "./WeKnora-lite" ]; then
      PATH="/Users/qixinchaye/.local/go/go1.26.4/bin:${PATH}" make build-lite
    fi
    if [ ! -f ".env.lite" ]; then
      cp .env.lite.example .env.lite
    fi
    set -a
    # shellcheck disable=SC1091
    . ./.env.lite
    set +a
    exec ./WeKnora-lite
    ;;
  docker)
    if ! command -v docker >/dev/null 2>&1; then
      echo "docker command not found. Install and start Docker Desktop, or run this script without arguments to use Lite mode." >&2
      exit 2
    fi
    if [ ! -f ".env" ]; then
      cp .env.example .env
    fi
    exec docker compose up -d
    ;;
  status)
    if pgrep -fl "WeKnora-lite" >/dev/null 2>&1; then
      pgrep -fl "WeKnora-lite"
    else
      echo "WeKnora Lite is not running."
    fi
    ;;
  *)
    echo "Usage: $0 [lite|docker|status]" >&2
    exit 64
    ;;
esac
