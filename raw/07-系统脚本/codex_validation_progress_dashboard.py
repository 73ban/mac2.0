#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a unified validation progress dashboard."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WIKI_STATS = ROOT / "wiki/09-统计与进化"


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def summarize_jsonl(label: str, path: Path, status_key: str = "status") -> dict[str, Any]:
    rows = iter_jsonl(path)
    counter = Counter(str(row.get(status_key) or "unknown") for row in rows)
    return {
        "label": label,
        "path": str(path.relative_to(ROOT)),
        "total": len(rows),
        "byStatus": dict(counter),
    }


def summarize_message_backtests() -> dict[str, Any]:
    root = ROOT / "raw/11-Codex分析产物/消息催化回测"
    rows = []
    for path in sorted(root.glob("*/message-catalyst-backtest.json")):
        payload = read_json(path)
        summary = payload.get("summary", {})
        rows.append({
            "date": payload.get("date") or path.parent.name,
            "path": str(path.relative_to(ROOT)),
            "total": summary.get("total", 0),
            "validated": summary.get("validated", 0),
            "partial": summary.get("partial", 0),
            "failedHighScore": summary.get("failedHighScore", 0),
            "pending": summary.get("pending", 0),
        })
    return {
        "label": "消息催化评分回测",
        "path": "raw/11-Codex分析产物/消息催化回测",
        "total": sum(row["total"] for row in rows),
        "byStatus": {
            "validated": sum(row["validated"] for row in rows),
            "partial": sum(row["partial"] for row in rows),
            "failed_high_score": sum(row["failedHighScore"] for row in rows),
            "pending": sum(row["pending"] for row in rows),
        },
        "rows": rows[-20:],
    }


def build(date: str) -> dict[str, Any]:
    sections = [
        summarize_jsonl("通用D+验证", ROOT / "data/facts/dplus_validation_results.jsonl"),
        summarize_jsonl("作战室候选票D+0", ROOT / "data/facts/warroom_candidate_validation_results.jsonl", "decision"),
        summarize_jsonl("作战室候选票D+后续", ROOT / "data/facts/warroom_candidate_dplus_validation_results.jsonl"),
        summarize_jsonl("飞书校准验证", ROOT / "data/facts/feishu_calibration_validation_results.jsonl"),
        summarize_jsonl("公告事件D+验证", ROOT / "data/facts/announcement_event_validation_results.jsonl"),
        summarize_message_backtests(),
    ]
    return {
        "schema": "73wiki-validation-progress-dashboard-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": date,
        "sections": sections,
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 验证闭环进度总览",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        "",
        "| 验证层 | 样本数 | 状态分布 | 数据源 |",
        "|---|---:|---|---|",
    ]
    for section in payload["sections"]:
        status = "；".join(f"{key}:{value}" for key, value in section.get("byStatus", {}).items()) or "-"
        lines.append(f"| {section['label']} | {section['total']} | {status} | `{section['path']}` |")
    lines.extend(["", "## 处理规则", "", "- 待验证不等于失败；只有次交易日市场数据到齐后才写结论。", "- 高分未验证、用户升权被市场反证、D+低于预期，优先进入规则修正。"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="验证闭环进度总览")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    if args.write:
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / f"{args.date}-验证闭环进度总览.md").write_text(render(payload), encoding="utf-8")
        (WIKI_STATS / f"{args.date}-验证闭环进度总览.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sections": [{k: v for k, v in section.items() if k != "rows"} for section in payload["sections"]]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
