#!/usr/bin/env python3
"""Generate due D+ validation tasks from the core candidate queue.

Usage:
  python3 raw/07-系统脚本/codex_generate_dplus_tasks.py --date 2026-06-29
  python3 raw/07-系统脚本/codex_generate_dplus_tasks.py --date 2026-06-30 --force
  python3 raw/07-系统脚本/codex_generate_dplus_tasks.py --all --force
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date as date_cls
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
QUEUE_PATH = ROOT / "wiki/09-统计与进化/核心候选个股D+验证队列.md"
OUT_JSON = ROOT / "data/facts/dplus_due_tasks.json"
RESULTS_JSONL = ROOT / "data/facts/dplus_validation_results.jsonl"
OVERVIEW_PATH = ROOT / "wiki/09-统计与进化/D+验证待回填总览.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def write(path: Path, content: str, force: bool = False) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def clean_cell(value: str) -> str:
    return value.strip().strip("`").strip()


def parse_queue() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in read(QUEUE_PATH).splitlines():
        if not (line.startswith("| ") and "`wiki/" in line):
            continue
        cells = [clean_cell(c) for c in line.strip("|").split("|")]
        if len(cells) < 11:
            continue
        code, name, role, evidence, d1, d3, d5, d10, d20, d30, card = cells[:11]
        if not re.fullmatch(r"\d{6}", code):
            continue
        rows.append(
            {
                "code": code,
                "name": name,
                "role": role,
                "evidenceDate": evidence,
                "D+1": d1,
                "D+3": d3,
                "D+5": d5,
                "D+10": d10,
                "D+20": d20,
                "D+30": d30,
                "card": card,
            }
        )
    return rows


def due_for(date: str, queue: list[dict[str, str]]) -> list[dict[str, str]]:
    due: list[dict[str, str]] = []
    nodes = ["D+1", "D+3", "D+5", "D+10", "D+20", "D+30"]
    for item in queue:
        matched = [node for node in nodes if item.get(node) == date]
        if not matched:
            continue
        due.append(
            {
                "date": date,
                "code": item["code"],
                "name": item["name"],
                "nodes": matched,
                "node": "/".join(matched),
                "role": item["role"],
                "evidenceDate": item["evidenceDate"],
                "card": item["card"],
                "status": "pending",
            }
        )
    return due


def all_due_dates(queue: list[dict[str, str]]) -> list[str]:
    dates: set[str] = set()
    for item in queue:
        for node in ["D+1", "D+3", "D+5", "D+10", "D+20", "D+30"]:
            value = item.get(node, "")
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                dates.add(value)
    return sorted(dates)


def build_task_page(date: str, due: list[dict[str, str]]) -> str:
    rows = "\n".join(
        f"| {x['code']} | {x['name']} | {x['node']} | {x['role']} | {x['evidenceDate']} | `{x['card']}` |"
        for x in due
    ) or "| - | - | - | - | - | - |"

    sections: list[str] = []
    for x in due:
        sections.append(
            f"""## {x['code']} {x['name']}

```yaml
date: {date}
code: {x['code']}
name: {x['name']}
validation_node: {x['node']}
price_action:
theme_action:
relative_strength:
volume_action:
decision:
rule_update:
```

验证重点：

- 是否强于对应板块。
- 是否验证 `{x['role']}` 的核心候选判断。
- 若弱于主线，应降低自动核心池权重。
"""
        )
    sections_text = "\n".join(sections) if sections else "## 今日无到期项\n\n- 无需回填。"
    results = load_results()
    result_rows = []
    for item in due:
        result = results.get((date, item["code"], item["node"]))
        if not result:
            continue
        evidence = result.get("evidence", [""])
        evidence_text = evidence[0] if isinstance(evidence, list) and evidence else ""
        result_rows.append(
            f"| {item['code']} | {item['name']} | {item['node']} | {result.get('changePercent', '')} | {result.get('priceAction', result.get('result', ''))} | {result.get('decision', '')} | {evidence_text} |"
        )
    auto_section = ""
    if result_rows:
        auto_section = "\n".join(
            [
                "## 自动回填结果",
                "",
                "| 代码 | 名称 | 节点 | 涨跌幅% | 结论 | 处理 | 证据 |",
                "|---|---|---|---:|---|---|---|",
                *result_rows,
                "",
            ]
        )

    return f"""# {date} D+验证任务

更新时间：{date}

## 定位

本页由 `raw/07-系统脚本/codex_generate_dplus_tasks.py` 从 [[核心候选个股D+验证队列]] 生成。  
它不是预测页，而是盘后事实回填页。

## 今日到期项

| 代码 | 名称 | 节点 | 主线定位 | 证据日 | 骨架卡 |
|---|---|---|---|---|---|
{rows}

## 回填模板

```yaml
date: {date}
code:
name:
validation_node:
price_action: 强于预期 | 符合预期 | 弱于预期 | 证伪
theme_action: 主线强化 | 分歧修复 | 轮动 | 退潮 | 无反馈
relative_strength: 强于板块 | 跟随板块 | 弱于板块
volume_action: 放量承接 | 缩量强势 | 放量滞涨 | 缩量走弱
decision: 升级 | 保留观察 | 降级 | 归档
rule_update:
```

{sections_text}

{auto_section}

## 回写要求

- [[核心候选个股D+验证队列]]
- [[20万小资金统计与进化仪表盘]]
- 相关正式核心候选档案
- 若验证失败，写入错误库或自动打分修正规则
"""


def update_json_many(items: dict[str, list[dict[str, str]]]) -> None:
    existing: dict[str, object] = {"version": 1, "dates": {}}
    if OUT_JSON.exists():
        try:
            existing = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {"version": 1, "dates": {}}
    dates = existing.setdefault("dates", {})
    if not isinstance(dates, dict):
        dates = {}
        existing["dates"] = dates
    for date, due in items.items():
        dates[date] = due
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_due_json() -> dict:
    if not OUT_JSON.exists():
        return {"version": 1, "dates": {}}
    try:
        data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "dates": {}}
    if not isinstance(data, dict) or not isinstance(data.get("dates"), dict):
        return {"version": 1, "dates": {}}
    return data


def load_results() -> dict[tuple[str, str, str], dict]:
    results: dict[tuple[str, str, str], dict] = {}
    if not RESULTS_JSONL.exists():
        return results
    for line in RESULTS_JSONL.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = (str(item.get("date", "")), str(item.get("code", "")), str(item.get("node", "")))
        if all(key):
            results[key] = item
    return results


def rows_for_tasks(tasks: list[dict], *, include_result: bool = False) -> str:
    if not tasks:
        return "| - | - | - | - | - | - |"
    rows = []
    for item in tasks:
        if include_result:
            rows.append(
                f"| {item.get('date', '-')} | {item.get('code', '-')} | {item.get('name', '-')} | {item.get('node', '-')} | {item.get('result', item.get('priceAction', '-'))} | {item.get('decision', '-')} |"
            )
        else:
            rows.append(
                f"| {item.get('date', '-')} | {item.get('code', '-')} | {item.get('name', '-')} | {item.get('node', '-')} | {item.get('role', '-')} | 待盘后回填 |"
            )
    return "\n".join(rows)


def build_overview(today: str) -> str:
    due_data = load_due_json()
    results = load_results()
    resolved: list[dict] = []
    overdue: list[dict] = []
    due_today: list[dict] = []
    future_counts: dict[str, list[dict]] = defaultdict(list)

    for due_date, tasks in sorted(due_data.get("dates", {}).items()):
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            key = (str(task.get("date", due_date)), str(task.get("code", "")), str(task.get("node", "")))
            result = results.get(key)
            merged = dict(task)
            merged["date"] = due_date
            if result or task.get("status") == "resolved":
                if result:
                    merged.update(result)
                resolved.append(merged)
                continue
            if due_date < today:
                overdue.append(merged)
            elif due_date == today:
                due_today.append(merged)
            else:
                future_counts[due_date].append(merged)

    future_rows = []
    for due_date, tasks in sorted(future_counts.items()):
        names = "、".join(f"{x.get('name', '')}{x.get('node', '')}" for x in tasks[:5])
        if len(tasks) > 5:
            names += f" 等{len(tasks)}项"
        future_rows.append(f"| {due_date} | {len(tasks)} | {names or '-'} |")
    future_table = "\n".join(future_rows) or "| - | 0 | - |"

    return f"""# D+验证待回填总览

更新时间：{today}

## 定位

本页是 D+ 验证的总控面板。每日任务页由 `raw/07-系统脚本/codex_generate_dplus_tasks.py` 自动生成，真实结果必须盘后回填。

数据源：

- [[核心候选个股D+验证队列]]
- `data/facts/dplus_due_tasks.json`
- `data/facts/dplus_validation_results.jsonl`
- `wiki/09-统计与进化/YYYY-MM-DD-D+验证任务.md`

## 当前摘要

```yaml
as_of: {today}
resolved_count: {len(resolved)}
overdue_pending_count: {len(overdue)}
due_today_count: {len(due_today)}
future_pending_count: {sum(len(v) for v in future_counts.values())}
```

## 已回填

| 到期日 | 代码 | 名称 | 节点 | 结论 | 处理 |
|---|---|---|---|---|---|
{rows_for_tasks(sorted(resolved, key=lambda x: (x.get('date', ''), x.get('code', ''))), include_result=True)}

## 已到期待回填

截至 {today}，已到期但还没有事实结论的 D+任务：

| 到期日 | 代码 | 名称 | 节点 | 定位 | 处理 |
|---|---|---|---|---|---|
{rows_for_tasks(sorted(overdue, key=lambda x: (x.get('date', ''), x.get('code', ''))))}

## 今日到期待回填

| 到期日 | 代码 | 名称 | 节点 | 定位 | 处理 |
|---|---|---|---|---|---|
{rows_for_tasks(sorted(due_today, key=lambda x: x.get('code', '')))}

## 未来到期压力

| 到期日 | 任务数 | 重点 |
|---|---:|---|
{future_table}

## 回填优先级

1. 先补已到期项。
2. 再处理今日到期项。
3. 每个结果只写事实和结论，不写行情作文。
4. 失败样本必须回写自动核心池打分规则、个股候选档案、题材生命周期、模式胜率或错误库。

## 自动生成命令

```bash
python3 raw/07-系统脚本/codex_generate_dplus_tasks.py --all --force --overview
```

## 当前原则

没有盘后事实，不做验证结论。D+验证不是为了证明 AI 对，而是为了找到 AI 错在哪里。
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--all", action="store_true", help="generate every due date found in the queue")
    parser.add_argument("--force", action="store_true", help="overwrite existing task page")
    parser.add_argument("--overview", action="store_true", help="refresh D+ validation overview page")
    parser.add_argument("--today", default=date_cls.today().isoformat(), help="as-of date for overview, YYYY-MM-DD")
    args = parser.parse_args()

    queue = parse_queue()
    if not args.all and not args.date:
        parser.error("one of --date or --all is required")

    dates = all_due_dates(queue) if args.all else [args.date]
    due_by_date: dict[str, list[dict[str, str]]] = {}
    written_count = 0
    skipped_count = 0
    for date in dates:
        if not date:
            continue
        due = due_for(date, queue)
        due_by_date[date] = due
        task_path = ROOT / f"wiki/09-统计与进化/{date}-D+验证任务.md"
        if write(task_path, build_task_page(date, due), force=args.force):
            written_count += 1
        else:
            skipped_count += 1
    update_json_many(due_by_date)
    if args.overview:
        OVERVIEW_PATH.write_text(build_overview(args.today), encoding="utf-8")

    print(f"dates={len(due_by_date)}")
    print(f"queue={len(queue)}")
    print(f"due_total={sum(len(v) for v in due_by_date.values())}")
    print(f"written={written_count}")
    print(f"skipped={skipped_count}")
    print(f"json={OUT_JSON.relative_to(ROOT)}")
    if args.overview:
        print(f"overview={OVERVIEW_PATH.relative_to(ROOT)}")
    for date, due in due_by_date.items():
        print(f"- {date}: {len(due)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
