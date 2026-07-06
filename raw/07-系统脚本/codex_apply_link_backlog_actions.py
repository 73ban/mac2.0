#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply low-risk actions from the wikilink backlog."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "wiki"
REPORT_DIR = WIKI / "09-统计与进化"
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(#[^\]|]+)?(\|[^\]]+)?\]\]")

MANUAL_TARGETS = {
    "策略/L4执行控制层": "04-L4交易模式与执行/L4执行控制层/每日5问执行检查清单",
    "L4 执行控制层": "04-L4交易模式与执行/L4执行控制层/每日5问执行检查清单",
    "深圳华强-000062": "03-L3个股档案/深圳华强",
    "合百集团-000417": "03-L3个股档案/合百集团",
    "中钨高新-000657": "03-L3个股档案/中钨高新",
    "股票/深圳华强": "03-L3个股档案/深圳华强",
    "股票/合百集团": "03-L3个股档案/合百集团",
    "股票/中钨高新": "03-L3个股档案/中钨高新",
    "个股档案/深圳华强-000062": "03-L3个股档案/深圳华强",
    "个股档案/合百集团-000417": "03-L3个股档案/合百集团",
    "个股档案/中钨高新-000657": "03-L3个股档案/中钨高新",
    "概念/确定性-仓位匹配": "04-L4交易模式与执行/确定性框架",
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_backlog(date: str) -> dict[str, Any]:
    path = REPORT_DIR / f"{date}-Wiki链接修复剩余工作单.json"
    return read_json(path)


def target_exists(target: str) -> bool:
    return (WIKI / f"{target}.md").exists() or (WIKI / target).exists()


def plain_text_for(link: str, alias: str) -> str:
    if alias:
        return alias[1:]
    value = link.removeprefix("sources/").removeprefix("queries/").strip("\\")
    if value.endswith(".md"):
        value = value[:-3]
    return value


def action_rows(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    rows = []
    for row in payload.get("rows", []):
        link = row.get("link", "")
        action = row.get("action", "")
        if action == "疑似伪链接，建议改普通文本":
            rows.append({**row, "mode": "plain"})
        elif link in MANUAL_TARGETS and target_exists(MANUAL_TARGETS[link]):
            rows.append({**row, "mode": "retarget", "target": MANUAL_TARGETS[link]})
        if len(rows) >= limit:
            break
    return rows


def apply_to_file(path: Path, rows: list[dict[str, Any]], write: bool) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path.relative_to(ROOT)), "changed": 0, "missingFile": True, "changes": []}
    text = path.read_text(encoding="utf-8", errors="ignore")
    by_link = {row["link"]: row for row in rows}
    changes: list[dict[str, str]] = []

    def repl(match: re.Match[str]) -> str:
        link, anchor, alias = match.group(1).strip(), match.group(2) or "", match.group(3) or ""
        row = by_link.get(link)
        if not row:
            return match.group(0)
        if row["mode"] == "plain":
            replacement = plain_text_for(link, alias)
            changes.append({"mode": "plain", "from": match.group(0), "to": replacement})
            return replacement
        target = row["target"]
        replacement = f"[[{target}{anchor}{alias}]]"
        changes.append({"mode": "retarget", "from": match.group(0), "to": replacement})
        return replacement

    new_text = WIKILINK_RE.sub(repl, text)
    if write and new_text != text:
        path.write_text(new_text, encoding="utf-8")
    return {"path": str(path.relative_to(ROOT)), "changed": len(changes), "missingFile": False, "changes": changes}


def run(date: str, limit: int, write: bool) -> dict[str, Any]:
    payload = load_backlog(date)
    rows = action_rows(payload, limit)
    by_page: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_page.setdefault(row["page"], []).append(row)
    reports = [apply_to_file(ROOT / page, items, write) for page, items in sorted(by_page.items())]
    changed = sum(item["changed"] for item in reports)
    modes = Counter(change["mode"] for item in reports for change in item.get("changes", []))
    out = {
        "schema": "73wiki-link-backlog-actions-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": date,
        "write": write,
        "limit": limit,
        "candidateRows": len(rows),
        "changed": changed,
        "byMode": dict(modes),
        "reports": [item for item in reports if item["changed"] or item.get("missingFile")],
    }
    return out


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} Wiki链接二次处理报告",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 写入模式：{payload['write']}",
        f"- 候选记录：{payload['candidateRows']}",
        f"- 实际改动：{payload['changed']}",
        "",
        "## 按动作",
        "",
        "| 动作 | 数量 |",
        "|---|---:|",
    ]
    for key, count in payload.get("byMode", {}).items():
        label = "伪链接转普通文本" if key == "plain" else "重定向到真实页面"
        lines.append(f"| {label} | {count} |")
    lines.extend(["", "## 明细", ""])
    for item in payload.get("reports", []):
        lines.append(f"### `{item['path']}`")
        if item.get("missingFile"):
            lines.append("- 文件不存在，跳过。")
        for change in item.get("changes", [])[:30]:
            lines.append(f"- {change['mode']}：`{change['from']}` -> `{change['to']}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="执行低风险 Wiki 链接二次处理")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = run(args.date, args.limit, args.write)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "写入" if args.write else "预演"
    (REPORT_DIR / f"{args.date}-Wiki链接二次处理-{suffix}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPORT_DIR / f"{args.date}-Wiki链接二次处理-{suffix}.md").write_text(render(payload), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "reports"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
