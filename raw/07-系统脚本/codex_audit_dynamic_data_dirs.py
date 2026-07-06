#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit dynamic RAW directories by latest file time and sample files."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WIKI_CONFIG = ROOT / "wiki/10-系统配置"

DYNAMIC_DIRS = [
    ("财联社CS财经", "raw/05-研报新闻/财联社"),
    ("同花顺热榜", "raw/04-市场数据/同花顺热榜"),
    ("通达信热榜", "raw/04-市场数据/通达信热榜"),
    ("每日涨停全景", "raw/04-市场数据/每日涨停全景"),
    ("首板涨停催化", "raw/04-市场数据/首板涨停催化"),
    ("板块强度", "raw/04-市场数据/板块强度"),
    ("板块成分股", "raw/04-市场数据/板块成分股"),
    ("龙虎榜全量", "raw/04-市场数据/龙虎榜全量"),
    ("公告", "raw/05-研报新闻/公告"),
    ("互动问答", "raw/05-研报新闻/互动问答"),
    ("飞书复盘RAW", "raw/02-每日复盘"),
    ("交割单RAW", "raw/01-交割单"),
]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def file_info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": rel(path),
        "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "sizeBytes": stat.st_size,
    }


def audit_dir(label: str, rel_dir: str, date: str) -> dict[str, Any]:
    root = ROOT / rel_dir
    if not root.exists():
        return {"label": label, "dir": rel_dir, "exists": False, "todayCount": 0, "latest": None, "samples": []}
    files = []
    today_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in {".stversions"} and not name.startswith(".")]
        for name in filenames:
            path = Path(dirpath) / name
            if ".sync-conflict-" in name:
                continue
            files.append(path)
            if date in str(path):
                today_files.append(path)
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    today_files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    latest = file_info(files[0]) if files else None
    return {
        "label": label,
        "dir": rel_dir,
        "exists": True,
        "todayCount": len(today_files),
        "latest": latest,
        "samples": [file_info(path) for path in today_files[:5]],
    }


def build(date: str) -> dict[str, Any]:
    rows = [audit_dir(label, rel_dir, date) for label, rel_dir in DYNAMIC_DIRS]
    return {
        "schema": "73wiki-dynamic-data-dir-audit-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": date,
        "summary": {
            "dirs": len(rows),
            "exists": sum(1 for row in rows if row["exists"]),
            "todayArrived": sum(1 for row in rows if row["todayCount"] > 0),
        },
        "rows": rows,
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 动态数据目录抽查",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 目录数：{payload['summary']['dirs']}",
        f"- 存在目录：{payload['summary']['exists']}",
        f"- 今日有文件：{payload['summary']['todayArrived']}",
        "",
        "| 数据源 | 目录 | 今日文件 | 最新文件 | 最新时间 | 样本 |",
        "|---|---|---:|---|---|---|",
    ]
    for row in payload["rows"]:
        latest = row.get("latest") or {}
        samples = "<br>".join(f"`{item['path']}`" for item in row.get("samples", [])[:3]) or "-"
        lines.append(f"| {row['label']} | `{row['dir']}` | {row['todayCount']} | `{latest.get('path', '-')}` | {latest.get('mtime', '-')} | {samples} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="动态数据目录抽查")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    if args.write:
        WIKI_CONFIG.mkdir(parents=True, exist_ok=True)
        (WIKI_CONFIG / f"{args.date}-动态数据目录抽查.md").write_text(render(payload), encoding="utf-8")
        (WIKI_CONFIG / f"{args.date}-动态数据目录抽查.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
