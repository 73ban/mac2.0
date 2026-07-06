#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lint pending Feishu notifications before they are sent.

The goal is not style. It blocks messages that ask the user to calibrate
without saying what is being judged, why Codex judged that way, and how the
user should reply.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SYSTEM = ROOT / ".system"
PENDING = SYSTEM / "feishu-notify-pending"
QUARANTINE = SYSTEM / "feishu-notify-quarantine"
OUT_JSON = SYSTEM / "feishu-protocol-lint.json"
OUT_MD = ROOT / "wiki/09-统计与进化/飞书通知清晰度检查.md"


QUESTION_TITLES = ("待判断", "待校准", "请校准", "人工校准")
NO_REPLY_TITLES = ("Watchdog", "缺口", "提醒", "报告", "回执")
BROAD_BAD_PATTERNS = (
    r"同花顺热榜\s*Top\s*100",
    r"淘股吧热榜\s*100",
    r"三榜热度合并",
    r"每日公告全量",
    r"盘前纪要",
    r"财经早餐",
    r"周复盘",
    r"事件合集",
)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def is_question(path: Path, text: str) -> bool:
    name = path.name
    return any(key in name or key in text[:120] for key in QUESTION_TITLES)


def is_no_reply(path: Path, text: str) -> bool:
    name = path.name
    return any(key in name or key in text[:120] for key in NO_REPLY_TITLES) or "无需回复" in text


def item_count(text: str) -> int:
    return len(re.findall(r"(?m)^\s*\d{1,2}[.、]\s+", text))


def lint_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    errors: list[str] = []
    warnings: list[str] = []
    question = is_question(path, text)

    if question:
        required_groups = [
            ("判断对象", ("判断对象", "你要判断")),
            ("回复格式", ("回复格式", "你只需要", "请优先回复")),
            ("当前判断", ("我当前判断", "当前结论", "我的当前结论")),
            ("判断逻辑", ("我的判断逻辑", "判断理由", "为什么")),
            ("不确定点", ("我不确定", "风险/不确定", "风险词", "不确定点")),
        ]
        for label, options in required_groups:
            if not any(option in text for option in options):
                errors.append(f"缺少{label}")
        count = item_count(text)
        if count == 0:
            errors.append("没有可编号校准条目")
        elif count > 10:
            errors.append(f"校准条目过多：{count}，最多10条")
        if re.search("|".join(BROAD_BAD_PATTERNS), text, re.I):
            if "作战室候选" in text or "持仓处理方案" in text:
                pass
            elif "单条" not in text and "不是判断整包" not in text:
                errors.append("把热榜/整包材料当成待判断对象，容易误导")
    elif is_no_reply(path, text):
        if "无需回复" not in text and "不用回复" not in text:
            warnings.append("通知型消息建议显式写明无需回复")

    return {
        "file": rel(path),
        "question": question,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# 飞书通知清晰度检查",
        "",
        f"- 检查时间：{payload['generatedAt']}",
        f"- 待发送：{payload['total']}",
        f"- 合格：{payload['okCount']}",
        f"- 隔离：{payload['quarantinedCount']}",
        "",
        "| 文件 | 结果 | 问题 |",
        "|---|---|---|",
    ]
    for item in payload["items"]:
        issues = "；".join(item["errors"] + item["warnings"]) or "-"
        lines.append(f"| `{item['file']}` | {'ok' if item['ok'] else 'blocked'} | {issues.replace('|', '/')} |")
    if not payload["items"]:
        lines.append("| - | 无待发送飞书 | - |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="飞书通知清晰度检查")
    parser.add_argument("--quarantine", action="store_true", help="move invalid pending files to quarantine")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    files = sorted(PENDING.glob("*.md")) if PENDING.exists() else []
    items = [lint_file(path) for path in files]
    quarantined = []
    if args.quarantine:
        QUARANTINE.mkdir(parents=True, exist_ok=True)
        for item in items:
            if item["ok"]:
                continue
            source = ROOT / item["file"]
            if source.exists():
                target = QUARANTINE / source.name
                shutil.move(str(source), str(target))
                item["quarantined_to"] = rel(target)
                quarantined.append(item["file"])

    payload = {
        "schema": "73wiki-feishu-protocol-lint-v1",
        "generatedAt": now_text(),
        "total": len(items),
        "okCount": sum(1 for item in items if item["ok"]),
        "quarantinedCount": len(quarantined),
        "items": items,
    }
    if args.write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.write_text(render_md(payload), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "items"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
