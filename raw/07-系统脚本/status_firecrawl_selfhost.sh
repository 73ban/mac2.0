#!/usr/bin/env bash
set -euo pipefail

cd /Users/qixinchaye/services/firecrawl
docker compose ps
curl -fsS http://127.0.0.1:3002/ || true
echo
