#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guard that daily review inputs and formal WIKI outputs are complete."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from codex_trading_calendar import is_trade_day


ROOT = Path(__file__).resolve().parents[2]
WIKI_STATS = ROOT / "wiki/09-统计与进化"
PENDING_DIR = ROOT / ".system/feishu-notify-pending"
STATUS_PATH = ROOT / ".system/review-publish-guard.json"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def exists_any(paths: list[Path]) -> tuple[bool, list[str]]:
    exists = False
    for path in paths:
        if path.is_file():
            exists = True
            break
        if path.is_dir() and any(item.is_file() for item in path.iterdir()):
            exists = True
            break
    return exists, [rel(path) for path in paths]


def build_status(date: str) -> dict[str, Any]:
    trade_required = is_trade_day(date)
    checks = []
    specs = [
        ("交割单RAW", True, [ROOT / f"raw/01-交割单/{date}/交割单.md", ROOT / f"raw/01-交割单/{date}", ROOT / f"raw/01-交割单/{date}-交割单.md"]),
        ("口述复盘RAW", True, [ROOT / f"raw/02-每日复盘/{date}-飞书复盘RAW.md", ROOT / f"raw/10-飞书交易沟通/{date[:4]}/{date[5:7]}/{date[8:10]}"]),
        ("每日复盘RAW", True, [ROOT / f"raw/02-每日复盘/{date}-复盘.md"]),
        ("正式WIKI复盘", True, [ROOT / f"wiki/09-统计与进化/{date}-复盘.md"]),
        ("正式WIKI交割单", True, [ROOT / f"wiki/06-持仓与资金管理/{date}-交割单.md"]),
    ]
    for label, required, paths in specs:
        ok, path_texts = exists_any(paths)
        checks.append({"label": label, "required": required and trade_required, "ok": ok or not (required and trade_required), "paths": path_texts})
    missing = [item for item in checks if item["required"] and not item["ok"]]
    return {
        "schema": "73wiki-review-publish-guard-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": date,
        "tradeRequired": trade_required,
        "ok": not missing,
        "checks": checks,
        "missing": missing,
    }


def render(status: dict[str, Any]) -> str:
    lines = [
        f"# {status['date']} 复盘强制发布检查",
        "",
        f"- 生成时间：{status['generatedAt']}",
        f"- 是否交易日要求：{status['tradeRequired']}",
        f"- 总体：{'PASS' if status['ok'] else 'FAIL'}",
        "",
        "| 项目 | 必需 | 状态 | 检查路径 |",
        "|---|---|---|---|",
    ]
    for item in status["checks"]:
        lines.append(f"| {item['label']} | {item['required']} | {'OK' if item['ok'] else '缺失'} | {'<br>'.join(f'`{x}`' for x in item['paths'])} |")
    if status["missing"]:
        lines.extend(["", "## 必须补齐", ""])
        for item in status["missing"]:
            lines.append(f"- {item['label']}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="复盘强制发布检查")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    status = build_status(args.date)
    if args.write:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        report = WIKI_STATS / f"{args.date}-复盘强制发布检查.md"
        report.write_text(render(status), encoding="utf-8")
        notify = PENDING_DIR / f"{args.date}-复盘强制发布缺口.md"
        if not status["ok"]:
            notify.parent.mkdir(parents=True, exist_ok=True)
            notify.write_text(render(status), encoding="utf-8")
        elif notify.exists():
            notify.unlink()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
