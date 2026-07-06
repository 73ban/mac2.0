#!/usr/bin/env bash
set -euo pipefail

cd /Users/qixinchaye/services/firecrawl
docker compose up -d
curl -fsS http://127.0.0.1:3002/ >/dev/null
echo "Firecrawl self-host is running at http://127.0.0.1:3002"
