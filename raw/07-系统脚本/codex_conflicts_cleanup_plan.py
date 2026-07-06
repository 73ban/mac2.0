#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a cleanup plan for .conflicts without deleting files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONFLICTS = ROOT / ".conflicts"
REPORT_DIR = ROOT / "wiki/10-系统配置"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def size_of(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def build(days: int) -> dict[str, Any]:
    cutoff = datetime.now() - timedelta(days=days)
    rows = []
    total = 0
    if CONFLICTS.exists():
        for path in sorted(CONFLICTS.iterdir()):
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            size = size_of(path)
            eligible = mtime < cutoff
            if eligible:
                total += size
            rows.append(
                {
                    "path": rel(path),
                    "mtime": mtime.strftime("%Y-%m-%d %H:%M:%S"),
                    "sizeBytes": size,
                    "eligible": eligible,
                    "reason": f"超过{days}天未变更" if eligible else "观察期内保留",
                }
            )
    return {
        "schema": "73wiki-conflicts-cleanup-plan-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "observeDays": days,
        "root": rel(CONFLICTS),
        "items": rows,
        "eligibleCount": sum(1 for row in rows if row["eligible"]),
        "eligibleBytes": total,
        "deleteCommandPolicy": "本脚本不删除；确认后再由用户明确授权删除清单内路径。",
    }


def render(payload: dict[str, Any]) -> str:
    mb = payload["eligibleBytes"] / 1024 / 1024
    lines = [
        "# .conflicts 隔离区清理计划",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 观察期：{payload['observeDays']} 天",
        f"- 可清理项：{payload['eligibleCount']}",
        f"- 可释放空间：{mb:.1f} MB",
        "- 状态：仅生成清单，不自动删除。",
        "",
        "| 路径 | 最后变更 | 大小MB | 是否可清理 | 原因 |",
        "|---|---|---:|---|---|",
    ]
    for row in payload["items"]:
        lines.append(f"| `{row['path']}` | {row['mtime']} | {row['sizeBytes'] / 1024 / 1024:.1f} | {row['eligible']} | {row['reason']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=".conflicts 清理计划")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.days)
    if args.write:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (REPORT_DIR / "隔离区清理计划.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (REPORT_DIR / "隔离区清理计划.md").write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
