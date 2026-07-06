#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Summarize the 12 daily automation tasks for the 73wiki trading loop."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_OUT = ROOT / "raw/11-Codex分析产物/十二项自动化闭环"
WIKI_STATS = ROOT / "wiki/09-统计与进化"


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def file_state(rel_path: str) -> dict[str, Any]:
    path = ROOT / rel_path
    return {
        "path": rel_path,
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else 0,
        "mtime": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if path.exists() else "",
    }


def status(ok: bool, detail: str, outputs: list[str]) -> dict[str, Any]:
    return {"status": "ok" if ok else "gap", "detail": detail, "outputs": outputs}


def build(date: str) -> dict[str, Any]:
    important = read_json(ROOT / f"raw/11-Codex分析产物/每日重要信息Top10/{date}/daily-important-info-top10.json", {})
    learning = read_json(ROOT / f"raw/11-Codex分析产物/超短自进化学习/{date}/shortline-learning-progress.json", {})
    warroom = read_json(ROOT / f"raw/11-Codex分析产物/动态作战室/{date}/dynamic-warroom-top5.json", {})
    raw_health = read_json(ROOT / f"wiki/09-统计与进化/{date}-RAW写入链路体检.json", {})
    watchdog = read_json(ROOT / ".system/automation-watchdog.json", {})
    git_backup = ROOT / "wiki/10-系统配置/Git远程备份说明.md"

    rows = {
        "1. 数据源健康检查": status(
            bool(raw_health) and not raw_health.get("硬问题"),
            ("检查WeRSS、财联社、三榜、淘股吧、通达信、OCR等链路是否有有效写入。"
             + (("当前缺口：" + "；".join(raw_health.get("硬问题") or [])) if raw_health.get("硬问题") else "")),
            [f"wiki/09-统计与进化/{date}-RAW写入链路体检.md", ".system/automation-watchdog.json"],
        ),
        "2. RAW重要性分层": status(
            bool(important.get("rows")),
            f"已结构化判断 {len(important.get('rows') or [])} 条重要消息；Top10用于人工校准。",
            [f"raw/11-Codex分析产物/每日重要信息Top10/{date}/daily-important-info-top10.json"],
        ),
        "3. 个股卡自动更新": status(
            exists("wiki/03-L3个股档案/多氟多-002407.md") and bool(warroom.get("top5")),
            "动态作战室和互动易会把持仓/候选票的重要证据写入L3个股卡。",
            ["wiki/03-L3个股档案", f"wiki/07-作战室/{date}-动态作战室Top5.md"],
        ),
        "4. 概念卡自动更新": status(
            exists("wiki/02-L2方向题材") and bool(warroom.get("top5")),
            "动态作战室按题材聚合写入L2方向题材页；旧题材二次催化仍需持续增强。",
            ["wiki/02-L2方向题材"],
        ),
        "5. 持仓优先闭环": status(
            bool(warroom.get("holdingsAnalysis")),
            f"识别持仓 {len(warroom.get('holdings') or [])} 只，已优先生成明日处理逻辑。",
            [f"wiki/07-作战室/{date}-动态作战室Top5.md"],
        ),
        "6. 作战室Top5动态版本库": status(
            exists("data/facts/warroom_dynamic_change_events.jsonl") and bool(warroom.get("top5")),
            "Top5调入、调出、排名变化、原因、D+预测均有事实记录。",
            ["data/facts/warroom_dynamic_change_events.jsonl", "data/facts/warroom_candidate_predictions.jsonl"],
        ),
        "7. 每日消息Top10": status(
            len(important.get("top10") or []) == 10,
            "每日输出10条消息校准样本，并为底层更多消息保留公司影响判断。",
            [f"wiki/07-作战室/{date}-每日重要信息Top10.md"],
        ),
        "8. 超短知识学习Top10": status(
            len(learning.get("top10") or []) == 10,
            f"候选 {((learning.get('summary') or {}).get('candidates')) or 0} 条；当天不足时回看近5日补足。",
            [f"raw/11-Codex分析产物/超短自进化学习/{date}/shortline-learning-progress.json"],
        ),
        "9. 交易模式库扩容": status(
            exists("wiki/04-L4交易模式与执行/模式词典总表.md") or exists("wiki/04-L4交易模式与执行/模式别名归一化表.md"),
            "模式词典、别名归一化、模式卡结构检查已纳入短线模式扫描。",
            ["wiki/04-L4交易模式与执行/模式别名归一化表.md", "wiki/04-L4交易模式与执行/模式词典总表.md"],
        ),
        "10. D+验证硬规则": status(
            exists("wiki/09-统计与进化/交易模式D+统计总表.md") and exists("wiki/09-统计与进化/动态作战室Top5-D+验证队列.md"),
            "交易模式、作战室候选、消息判断都进入D+1/D+3/D+5验证队列。",
            ["wiki/09-统计与进化/交易模式D+统计总表.md", "wiki/09-统计与进化/动态作战室Top5-D+验证队列.md"],
        ),
        "11. 通知系统降噪": status(
            exists("wiki/09-统计与进化/飞书通知清晰度检查.md"),
            "飞书只保留告警、消息校准、学习校准、22:30作战室等必要通知。",
            ["wiki/09-统计与进化/飞书通知清晰度检查.md", ".system/feishu-notification-policy.json"],
        ),
        "12. Git本地版本/远程备份": status(
            exists(".git") and git_backup.exists(),
            "本地Git已启用；远程备份需用户提供GitHub/Gitee远程仓库URL后才能push。",
            ["wiki/10-系统配置/Git远程备份说明.md"],
        ),
    }
    return {
        "schema": "73wiki-twelve-task-execution-status-v1",
        "date": date,
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "watchdog": {
            "status": watchdog.get("status"),
            "criticalCount": watchdog.get("criticalCount"),
            "warningCount": watchdog.get("warningCount"),
        },
        "rows": rows,
        "gaps": [name for name, row in rows.items() if row["status"] != "ok"],
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 十二项自动化闭环执行状态",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- Watchdog：{payload['watchdog'].get('status')}；硬故障 {payload['watchdog'].get('criticalCount')}；软告警 {payload['watchdog'].get('warningCount')}",
        f"- 缺口数：{len(payload['gaps'])}",
        "",
        "| 项目 | 状态 | 当前结论 | 产物 |",
        "|---|---|---|---|",
    ]
    for name, row in payload["rows"].items():
        outputs = "<br>".join(f"`{item}`" for item in row.get("outputs") or [])
        lines.append(f"| {name} | {row['status']} | {row['detail']} | {outputs} |")
    lines.extend(["", "## 当前缺口", ""])
    if payload["gaps"]:
        lines.extend(f"- {item}" for item in payload["gaps"])
    else:
        lines.append("- 12项闭环均有当日产物或可用规则。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    if args.write:
        out_dir = RAW_OUT / args.date
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "twelve-task-execution-status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out_dir / "twelve-task-execution-status.md").write_text(render(payload), encoding="utf-8")
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / f"{args.date}-十二项自动化闭环执行状态.md").write_text(render(payload), encoding="utf-8")
    print(json.dumps({"ok": True, "date": args.date, "gaps": payload["gaps"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
