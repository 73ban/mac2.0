#!/usr/bin/env bash
set -euo pipefail

LABELS=(
  "com.73wiki.cloud-data-connectors"
  "com.73wiki.data-interface-health"
  "com.73wiki.eastmoney-market-snapshot"
  "com.73wiki.evening-stock-news-radar"
  "com.73wiki.interactive-qa"
  "com.73wiki.local-werss"
  "com.73wiki.paddleocr-raw08"
  "com.73wiki.tdxrs-auction-snapshot"
  "com.73wiki.tdxrs-close-basics"
  "com.73wiki.weknora-lite"
)

DOMAIN="gui/$(id -u)"
PLIST_DIR="$HOME/Library/LaunchAgents"

for label in "${LABELS[@]}"; do
  plist="$PLIST_DIR/$label.plist"
  if [[ ! -f "$plist" ]]; then
    echo "MISSING $label $plist"
    continue
  fi

  if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
    launchctl kickstart -k "$DOMAIN/$label" >/dev/null 2>&1 || true
    echo "RESTARTED $label"
  else
    launchctl bootstrap "$DOMAIN" "$plist" >/dev/null 2>&1 || true
    launchctl kickstart -k "$DOMAIN/$label" >/dev/null 2>&1 || true
    echo "LOADED $label"
  fi
done
