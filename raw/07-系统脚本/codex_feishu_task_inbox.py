#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build an executable Codex task inbox from Feishu-synced RAW messages."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_CHAT = ROOT / "raw" / "10-飞书交易沟通"
RAW_FEISHU_INPUT = ROOT / "raw" / "09-短线知识" / "飞书输入"
OUT_ROOT = RAW_CHAT / "任务指令"
WIKI_STATS = ROOT / "wiki" / "09-统计与进化"
FACTS = ROOT / "data" / "facts" / "feishu_codex_tasks.jsonl"


TASK_MARKERS = ("【Codex任务】", "【codex任务】", "#Codex任务", "#codex任务", "Codex任务：", "codex任务：")


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def clean(value: Any, limit: int = 300) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def iter_sources(limit_files: int = 600) -> list[Path]:
    paths: list[Path] = []
    for root in (RAW_CHAT, RAW_FEISHU_INPUT):
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            if not path.is_file():
                continue
            rel_path = rel(path)
            if "/任务指令/" in rel_path or rel_path.endswith("/README.md"):
                continue
            if path.name in {"codex-task-inbox.md"}:
                continue
            paths.append(path)
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return paths[:limit_files]


def extract_block(text: str) -> str:
    for marker in TASK_MARKERS:
        idx = text.find(marker)
        if idx >= 0:
            return text[idx:].strip()
    return ""


def parse_fields(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in block.splitlines():
        stripped = line.strip().lstrip("-").strip()
        if not stripped or "：" not in stripped and ":" not in stripped:
            continue
        key, value = re.split(r"[:：]", stripped, maxsplit=1)
        key = key.strip()
        value = value.strip()
        if key in {"优先级", "任务", "要求", "截止", "输出", "背景", "范围"}:
            fields[key] = value
    return fields


def classify_task(text: str) -> str:
    if re.search(r"持仓|买|卖|作战室|Top5|盘中|竞价", text):
        return "trading"
    if re.search(r"脚本|自动化|定时|Watchdog|接口|抓取|落盘|raw|RAW|git", text, re.I):
        return "system"
    if re.search(r"wiki|个股卡|题材卡|模式|错误库|资料", text, re.I):
        return "wiki"
    return "general"


def existing_ids() -> set[str]:
    ids: set[str] = set()
    if not FACTS.exists():
        return ids
    for line in FACTS.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if item.get("taskId"):
            ids.add(str(item["taskId"]))
    return ids


def collect(date: str) -> list[dict[str, Any]]:
    seen = existing_ids()
    tasks: list[dict[str, Any]] = []
    for path in iter_sources():
        text = path.read_text(encoding="utf-8", errors="ignore")
        block = extract_block(text)
        if not block:
            continue
        fields = parse_fields(block)
        task_text = fields.get("任务") or clean(block, 220)
        task_id = f"feishu-task:{sha(block)}"
        status = "seen" if task_id in seen else "new"
        item = {
            "schema": "73wiki-feishu-codex-task-v1",
            "taskId": task_id,
            "date": date,
            "detectedAt": now_text(),
            "status": status,
            "priority": fields.get("优先级") or "未标注",
            "category": classify_task(block),
            "task": task_text,
            "requirements": fields.get("要求") or "",
            "deadline": fields.get("截止") or "",
            "output": fields.get("输出") or "",
            "sourcePath": rel(path),
            "rawBlock": block[:2000],
        }
        tasks.append(item)
    return tasks


def append_new(tasks: list[dict[str, Any]]) -> int:
    seen = existing_ids()
    added = 0
    FACTS.parent.mkdir(parents=True, exist_ok=True)
    with FACTS.open("a", encoding="utf-8") as handle:
        for item in reversed(tasks):
            if item["taskId"] in seen:
                continue
            item = dict(item)
            item["status"] = "pending"
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            seen.add(item["taskId"])
            added += 1
    return added


def render_md(date: str, tasks: list[dict[str, Any]], added: int) -> str:
    lines = [
        f"# {date} 飞书Codex任务收件箱",
        "",
        f"- 生成时间：{now_text()}",
        f"- 本轮新增：{added}",
        "- 规则：只有包含 `【Codex任务】` 或 `#Codex任务` 的飞书同步文本，才进入执行队列。",
        "",
        "| 状态 | 优先级 | 分类 | 任务 | 要求 | 来源 |",
        "|---|---|---|---|---|---|",
    ]
    if not tasks:
        lines.append("| - | - | - | 暂无飞书任务 | - | - |")
    for item in tasks[:50]:
        lines.append(
            f"| {item['status']} | {item['priority']} | {item['category']} | {clean(item['task'], 80)} | {clean(item['requirements'], 100)} | `{item['sourcePath']}` |"
        )
    lines.extend(
        [
            "",
            "## 飞书下任务格式",
            "",
            "```text",
            "【Codex任务】",
            "优先级：高",
            "任务：检查今天龙虾哪些任务没落盘，并修复验收规则",
            "要求：写入wiki，必要时提交git",
            "输出：飞书回复+wiki沉淀",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(date: str, tasks: list[dict[str, Any]], added: int) -> None:
    out = OUT_ROOT / date
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "73wiki-feishu-codex-task-inbox-v1",
        "date": date,
        "generatedAt": now_text(),
        "added": added,
        "tasks": tasks,
    }
    (out / "codex-task-inbox.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = render_md(date, tasks, added)
    (out / "codex-task-inbox.md").write_text(md, encoding="utf-8")
    (WIKI_STATS / f"{date}-飞书Codex任务收件箱.md").write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="飞书Codex任务收件箱")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    tasks = collect(args.date)
    added = append_new(tasks) if args.write else 0
    if args.write:
        write_outputs(args.date, tasks, added)
    print(json.dumps({"ok": True, "date": args.date, "taskCount": len(tasks), "added": added}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
