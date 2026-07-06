#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate Feishu calibration events with next-trading-day market evidence."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "raw/07-系统脚本"
EVENTS = ROOT / "data/facts/feishu_calibration_events.jsonl"
OUT_JSONL = ROOT / "data/facts/feishu_calibration_validation_results.jsonl"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|8\d{5})(?!\d)")


def load_calendar_module():
    spec = importlib.util.spec_from_file_location("codex_trading_calendar", SCRIPTS / "codex_trading_calendar.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load trading calendar")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def append_unique(path: Path, rows: list[dict[str, Any]], key: str) -> int:
    existing = {row.get(key) for row in iter_jsonl(path)}
    added = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            if row.get(key) in existing:
                continue
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            existing.add(row.get(key))
            added += 1
    return added


def read_market(date: str) -> tuple[str, list[str]]:
    roots = [
        ROOT / f"raw/04-市场数据/每日涨停全景/{date}",
        ROOT / f"raw/04-市场数据/首板涨停催化/{date}",
        ROOT / f"raw/04-市场数据/同花顺热榜/{date}",
        ROOT / f"raw/04-市场数据/通达信热榜/{date}",
        ROOT / f"raw/04-市场数据/板块强度/{date}",
        ROOT / f"raw/04-市场数据/板块四龙排序/{date}",
    ]
    files = []
    chunks = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".json"}:
                continue
            files.append(str(path.relative_to(ROOT)))
            try:
                if path.suffix.lower() == ".json":
                    chunks.append(json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False))
                else:
                    chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
    return "\n".join(chunks), files[:30]


def compact(value: str, limit: int = 80) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def validate(event: dict[str, Any], today: str | None = None) -> dict[str, Any]:
    calendar = load_calendar_module()
    source_date = event.get("date") or str(event.get("created_at", ""))[:10]
    next_day = calendar.next_trade_day(source_date).isoformat()
    target_text = "\n".join(str(event.get(key, "")) for key in ("target", "message_text", "reference_text"))
    codes = sorted(set(CODE_RE.findall(target_text)))
    market, sources = read_market(next_day)
    if today and next_day > today:
        status = "pending_trade_day"
        evidence = "验证交易日未到"
    elif not market:
        status = "pending_market_data"
        evidence = "次一交易日市场数据未到齐"
    else:
        code_hits = [code for code in codes if code in market]
        text_hits = [word for word in ("涨停", "连板", "热榜", "板块", "晋级") if word in target_text and word in market]
        hit = bool(code_hits or text_hits)
        action = event.get("action")
        if action == "up":
            status = "validated" if hit else "not_validated"
        elif action == "down":
            status = "validated" if not hit else "contradicted"
        else:
            status = "observed" if hit else "not_validated"
        evidence = "；".join([
            f"代码命中 {', '.join(code_hits[:8])}" if code_hits else "",
            f"文本命中 {', '.join(text_hits[:8])}" if text_hits else "",
        ]).strip("；") or "未见次日涨停/热榜/板块证据"
    return {
        "schema": "feishu-calibration-validation-result-v1",
        "result_id": f"{event.get('job_id', compact(target_text, 20))}:{next_day}",
        "job_id": event.get("job_id"),
        "source_date": source_date,
        "next_trade_day": next_day,
        "target": compact(event.get("target") or event.get("message_text")),
        "action": event.get("action"),
        "user_judgement": event.get("user_judgement"),
        "status": status,
        "evidence": evidence,
        "sources": sources,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def build(today: str) -> dict[str, Any]:
    events = [row for row in iter_jsonl(EVENTS) if row.get("needs_validation") or row.get("status") in {"pending_validation", "recorded"}]
    rows = [validate(event, today=today) for event in events]
    return {
        "schema": "73wiki-feishu-calibration-autovalidation-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "today": today,
        "total": len(rows),
        "summary": {
            "validated": sum(1 for row in rows if row["status"] == "validated"),
            "contradicted": sum(1 for row in rows if row["status"] == "contradicted"),
            "notValidated": sum(1 for row in rows if row["status"] == "not_validated"),
            "pending": sum(1 for row in rows if row["status"].startswith("pending")),
        },
        "rows": rows,
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        "# 飞书校准次日自动验证",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 统计截至：{payload['today']}",
        f"- 总数：{payload['total']}",
        f"- 已验证：{payload['summary']['validated']}",
        f"- 被市场反证：{payload['summary']['contradicted']}",
        f"- 未验证：{payload['summary']['notValidated']}",
        f"- 待数据：{payload['summary']['pending']}",
        "",
        "| 来源日 | 次交易日 | 对象 | 用户判断 | 状态 | 证据 |",
        "|---|---|---|---|---|---|",
    ]
    for row in payload["rows"]:
        lines.append(f"| {row['source_date']} | {row['next_trade_day']} | {row['target'].replace('|', '/')} | {row.get('user_judgement') or row.get('action')} | {row['status']} | {row['evidence'].replace('|', '/')} |")
    if not payload["rows"]:
        lines.append("| - | - | 无待验证校准 | - | - | - |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="飞书校准次日自动验证")
    parser.add_argument("--today", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.today)
    if args.write:
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / "飞书校准次日自动验证.md").write_text(render(payload), encoding="utf-8")
        (WIKI_STATS / f"{args.today}-飞书校准次日自动验证.md").write_text(render(payload), encoding="utf-8")
        added = append_unique(OUT_JSONL, payload["rows"], "result_id")
        payload["added"] = added
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
