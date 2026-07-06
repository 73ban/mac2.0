#!/usr/bin/env python3
"""Health check for the Longxia -> Codex review handoff daemon."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path


ROOT = Path(os.environ.get("WIKI_PROJECT_PATH", "/Users/qixinchaye/wiki/73神话"))
CURRENT_STATUS_PATH = ROOT / ".system/longxia-review-handoff-current.json"
STATE_PATH = ROOT / ".system/longxia-review-handoff-state.json"
LOG_PATH = ROOT / ".system/logs/longxia-review-handoff.log"
LABEL = "com.qixinchaye.longxia-review-handoff"


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def tail(path: Path, lines: int = 8) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:]
    except Exception:
        return []


def current_quality(trade_date: str | None) -> dict | None:
    if not trade_date:
        return None
    path = ROOT / ".system" / f"longxia-review-quality-{trade_date}.json"
    if not path.exists():
        return None
    payload = read_json(path, {})
    return {
        "grade": payload.get("grade"),
        "score": payload.get("score"),
        "ok": payload.get("ok"),
        "issues": payload.get("issues", []),
        "warnings": payload.get("warnings", []),
        "generated_at": payload.get("generated_at"),
        "json": str(path.relative_to(ROOT)),
        "report": f"wiki/09-统计与进化/{trade_date}-龙虾复盘RAW质量验收.md",
        "action_plan": f"wiki/09-统计与进化/{trade_date}-龙虾复盘补交任务单.md",
    }


def normalize_latest_processed(latest_processed: dict | None, latest_quality: dict | None) -> dict | None:
    if not latest_processed:
        return None
    normalized = dict(latest_processed)
    snapshot = latest_processed.get("quality_check")
    if not latest_quality or not snapshot:
        return normalized
    snapshot_key = (
        snapshot.get("grade"),
        snapshot.get("score"),
        snapshot.get("ok"),
        len(snapshot.get("issues", [])),
        len(snapshot.get("warnings", [])),
    )
    current_key = (
        latest_quality.get("grade"),
        latest_quality.get("score"),
        latest_quality.get("ok"),
        len(latest_quality.get("issues", [])),
        len(latest_quality.get("warnings", [])),
    )
    if snapshot_key == current_key:
        normalized["quality_check_current"] = latest_quality
        normalized["quality_check_stale"] = False
        return normalized
    normalized["quality_check_at_processing"] = snapshot
    normalized["quality_check_current"] = latest_quality
    normalized["quality_check_stale"] = True
    normalized.pop("quality_check", None)
    return normalized


def launchd_running() -> dict:
    uid = os.getuid()
    result = subprocess.run(
        ["launchctl", "print", f"gui/{uid}/{LABEL}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    text = result.stdout + result.stderr
    running = bool(re.search(r"\bstate\s*=\s*running\b", text))
    return {
        "ok": result.returncode == 0 and running,
        "status": result.returncode,
        "state": "running" if running else "not_running",
    }


def main() -> int:
    status = read_json(CURRENT_STATUS_PATH, {})
    state = read_json(STATE_PATH, {"processed": {}, "seen": {}})
    launchd = launchd_running()
    processed = state.get("processed", {})
    latest_processed = None
    if processed:
        latest_processed = sorted(
            processed.values(),
            key=lambda item: item.get("at", ""),
        )[-1]
    latest_quality = current_quality(latest_processed.get("trade_date") if latest_processed else None)
    latest_processed_normalized = normalize_latest_processed(latest_processed, latest_quality)
    current_status = status.get("status", "unknown")
    updated_at = status.get("updated_at")
    stale_seconds = None
    if updated_at:
        try:
            stale_seconds = time.time() - time.mktime(time.strptime(updated_at, "%Y-%m-%d %H:%M:%S"))
        except Exception:
            stale_seconds = None
    ok = launchd["ok"] and current_status not in {"error", "codex_timeout", "codex_failed"}
    payload = {
        "ok": ok,
        "launchd": launchd,
        "current": status,
        "current_status_stale_seconds": round(stale_seconds, 1) if stale_seconds is not None else None,
        "latest_processed": latest_processed_normalized,
        "latest_quality_current": latest_quality,
        "processed_count": len(processed),
        "log_tail": tail(LOG_PATH),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
