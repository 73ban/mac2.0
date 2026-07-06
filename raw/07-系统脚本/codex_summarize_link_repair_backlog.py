#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Summarize unresolved wikilinks from priority repair reports."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "wiki/09-统计与进化"
GENERATED_REPORT_MARKERS = (
    "Wiki链接修复报告",
    "Wiki链接二次处理",
    "Wiki链接修复剩余工作单",
    "安全WikiLint报告",
)


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def classify(link: str, status: str) -> str:
    if status == "ambiguous":
        return "歧义待人工选目标"
    if len(link) > 40 or link.startswith(("好的", "sources/", "queries/")) or "..." in link:
        return "疑似伪链接，建议改普通文本"
    if "/" in link and link.split("/", 1)[0] in {"股票", "概念", "策略", "错误", "题材", "来源", "个股档案", "交割单"}:
        return "缺目标页，需补页或改路径"
    return "缺目标页，需确认是否补页"


def build(date: str) -> dict[str, Any]:
    rows = []
    seen: set[tuple[str, str, str]] = set()
    for path in sorted(REPORT_DIR.glob(f"{date}-*Wiki链接修复报告.json")):
        if "优先目录Wiki链接修复报告" in path.name:
            continue
        payload = read_json(path)
        for report in payload.get("reports", []):
            page = report.get("path", "")
            if any(marker in Path(page).name for marker in GENERATED_REPORT_MARKERS):
                continue
            for item in report.get("unresolved", []):
                key = (page, item.get("link", ""), item.get("status", ""))
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "page": page,
                    "link": item.get("link", ""),
                    "status": item.get("status", ""),
                    "action": classify(item.get("link", ""), item.get("status", "")),
                    "report": str(path.relative_to(ROOT)),
                })
    by_action = Counter(row["action"] for row in rows)
    by_link = Counter(row["link"] for row in rows)
    return {
        "schema": "73wiki-link-repair-backlog-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": date,
        "total": len(rows),
        "byAction": dict(by_action),
        "topLinks": by_link.most_common(80),
        "rows": rows[:1000],
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} Wiki链接修复剩余工作单",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 未解链接记录：{payload['total']}",
        "",
        "## 按处理动作",
        "",
        "| 动作 | 数量 |",
        "|---|---:|",
    ]
    for key, count in payload["byAction"].items():
        lines.append(f"| {key} | {count} |")
    lines.extend(["", "## 高频目标", "", "| 目标 | 次数 |", "|---|---:|"])
    for link, count in payload["topLinks"][:50]:
        lines.append(f"| `[[{link}]]` | {count} |")
    lines.extend(["", "## 明细", "", "| 页面 | 链接 | 状态 | 动作 |", "|---|---|---|---|"])
    for row in payload["rows"][:300]:
        lines.append(f"| `{row['page']}` | `[[{row['link']}]]` | {row['status']} | {row['action']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="链接修复剩余工作单")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    if args.write:
        (REPORT_DIR / f"{args.date}-Wiki链接修复剩余工作单.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (REPORT_DIR / f"{args.date}-Wiki链接修复剩余工作单.md").write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
