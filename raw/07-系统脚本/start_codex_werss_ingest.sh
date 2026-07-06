#!/usr/bin/env bash
# LEGACY: do not use for the current 15-minute cloud data connector chain.
# Current chain: LaunchAgent com.73wiki.cloud-data-connectors ->
# .system/scripts/run-cloud-data-connectors.mjs -> WeRSS/API/URL RAW capture.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${ROOT_DIR}"
node "${ROOT_DIR}/.system/scripts/fetch-wechat-mp-seeds.mjs"
python3 "${SCRIPT_DIR}/codex_raw_watch.py" --root "${ROOT_DIR}" --once --lookback-hours 240
exec python3 "${SCRIPT_DIR}/codex_batch_ingest_queue.py"
