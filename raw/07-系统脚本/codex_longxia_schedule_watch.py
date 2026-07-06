#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check Longxia/TDX scheduled outputs using task time + sync delay."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".system/longxia-task-schedule.json"
OUT_DIR = ROOT / "raw/11-Codex分析产物/龙虾定时任务验收"
WIKI_STATS = ROOT / "wiki/09-统计与进化"


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def latest_file(path: Path, date: str | None = None) -> Path | None:
    if not path.exists():
        return None
    files = [p for p in path.rglob("*") if p.is_file()]
    if date:
        compact = date.replace("-", "")
        files = [p for p in files if date in str(p) or compact in str(p)]
    return max(files, key=lambda p: p.stat().st_mtime, default=None)


def task_paths(task: dict[str, Any], date: str) -> list[Path]:
    values = []
    if task.get("paths"):
        values.extend(task.get("paths") or [])
    elif task.get("path"):
        values.append(task.get("path"))
    return [ROOT / str(value).format(date=date) for value in values]


def latest_for_task(task: dict[str, Any], date: str) -> tuple[Path | None, Path | None]:
    require_date = bool(task.get("requireDateInPath", True))
    best: Path | None = None
    best_root: Path | None = None
    for path in task_paths(task, date):
        current = latest_file(path, date if require_date else None)
        if current and (best is None or current.stat().st_mtime > best.stat().st_mtime):
            best = current
            best_root = path
    return best, best_root


def due_time(date: str, hhmm: str, delay: int) -> datetime:
    if not hhmm:
        return datetime.strptime(date, "%Y-%m-%d")
    hour, minute = [int(x) for x in hhmm.split(":", 1)]
    return datetime.strptime(date, "%Y-%m-%d").replace(hour=hour, minute=minute) + timedelta(minutes=delay)


def active_for_date(freq: str, dt_obj: datetime, is_trade_day: bool) -> bool:
    if freq == "daily":
        return True
    if freq == "trade_day":
        return is_trade_day
    if freq == "sunday":
        return dt_obj.weekday() == 6
    if freq in {"disabled", "manual"}:
        return False
    return True


def build(date: str, now_text: str | None = None) -> dict[str, Any]:
    config = read_json(CONFIG, {"tasks": [], "syncDelayMinutes": 10})
    now = datetime.strptime(now_text, "%Y-%m-%d %H:%M") if now_text else datetime.now()
    data_health = read_json(ROOT / ".system/data-interface-health.json", {})
    is_trade_day = bool(data_health.get("是否交易日"))
    delay = int(config.get("syncDelayMinutes") or 10)
    rows = []
    for task in config.get("tasks") or []:
        freq = str(task.get("frequency") or "daily")
        source_status = str(task.get("status") or "")
        raw_required = bool(task.get("rawRequired", True))
        active = active_for_date(freq, datetime.strptime(date, "%Y-%m-%d"), is_trade_day)
        check_at = due_time(date, str(task.get("time")), delay)
        paths = task_paths(task, date)
        latest, matched_root = latest_for_task(task, date)
        if source_status.upper() == "OFF" or freq == "disabled":
            state = "disabled"
            detail = f"停用任务，不要求写RAW；替代任务：{task.get('replacedBy') or task.get('note') or '-'}"
        elif not raw_required:
            state = "not_required"
            detail = "该任务不要求写RAW，只登记状态。"
        elif not active:
            state = "not_scheduled"
            detail = "该日期不在任务频率内"
        elif now < check_at:
            state = "not_due"
            detail = f"未到验收时间 {check_at.strftime('%H:%M')}"
        elif latest:
            state = "ok"
            detail = f"已同步：{rel(latest)}"
        else:
            state = "missing"
            detail = f"已过验收时间 {check_at.strftime('%H:%M')}，未发现产物"
        rows.append({
            "time": task.get("time"),
            "checkAt": check_at.strftime("%Y-%m-%d %H:%M"),
            "name": task.get("name"),
            "sourceStatus": source_status,
            "frequency": freq,
            "group": task.get("group") or "",
            "rawRequired": raw_required,
            "path": " / ".join(rel(p) for p in paths),
            "matchedRoot": rel(matched_root) if matched_root else "",
            "state": state,
            "detail": detail,
            "latest": rel(latest) if latest else "",
        })
    due_missing = [r for r in rows if r["state"] == "missing"]
    return {
        "schema": "73wiki-longxia-schedule-watch-v1",
        "date": date,
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "syncDelayMinutes": delay,
        "isTradeDay": is_trade_day,
        "missingFromUserCount": config.get("missingFromUserCount"),
        "declaredTotal": config.get("declaredTotal"),
        "summary": {
            "total": len(rows),
            "ok": sum(1 for r in rows if r["state"] == "ok"),
            "notDue": sum(1 for r in rows if r["state"] == "not_due"),
            "missing": len(due_missing),
            "notScheduled": sum(1 for r in rows if r["state"] == "not_scheduled"),
            "disabled": sum(1 for r in rows if r["state"] == "disabled"),
            "notRequired": sum(1 for r in rows if r["state"] == "not_required"),
        },
        "rows": rows,
        "dueMissing": due_missing,
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 龙虾定时任务验收",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 验收规则：任务时间 + {payload['syncDelayMinutes']} 分钟。",
        f"- 当前登记 {payload['summary']['total']} 个；声明总数 {payload.get('declaredTotal') or payload['summary']['total']}；待补 {payload.get('missingFromUserCount')} 个。",
        f"- 汇总：ok {payload['summary']['ok']}；未到验收 {payload['summary']['notDue']}；缺失 {payload['summary']['missing']}；非当日任务 {payload['summary']['notScheduled']}；不要求RAW {payload['summary'].get('notRequired', 0)}；停用 {payload['summary'].get('disabled', 0)}",
        "",
        "| 时间 | 验收时间 | 分组 | 任务 | 频率 | 源状态 | RAW要求 | 状态 | 路径 | 说明 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in payload["rows"]:
        lines.append(f"| {row['time'] or '-'} | {row['checkAt']} | {row.get('group','')} | {row['name']} | {row['frequency']} | {row['sourceStatus']} | {'是' if row.get('rawRequired') else '否'} | {row['state']} | `{row['path']}` | {row['detail']} |")
    lines.extend(["", "## 已到点但缺失", ""])
    if payload["dueMissing"]:
        lines.extend(f"- {row['name']}：{row['detail']}，路径 `{row['path']}`" for row in payload["dueMissing"])
    else:
        lines.append("- 无。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--now", default="")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.date, args.now or None)
    if args.write:
        out = OUT_DIR / args.date
        out.mkdir(parents=True, exist_ok=True)
        (out / "longxia-schedule-watch.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "longxia-schedule-watch.md").write_text(render(payload), encoding="utf-8")
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / f"{args.date}-龙虾定时任务验收.md").write_text(render(payload), encoding="utf-8")
    print(json.dumps({"ok": True, "date": args.date, "summary": payload["summary"], "dueMissing": [r["name"] for r in payload["dueMissing"]]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
