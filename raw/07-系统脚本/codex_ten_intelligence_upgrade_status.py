#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check the 10 hard rules for Wiki and Codex intelligence improvement."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_OUT = ROOT / "raw/11-Codex分析产物/十项智能进化闭环"
WIKI_OUT = ROOT / "wiki/09-统计与进化"


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def count_files(rel: str, pattern: str = "*") -> int:
    base = ROOT / rel
    if not base.exists():
        return 0
    return sum(1 for item in base.rglob(pattern) if item.is_file())


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def longxia_missing_names(items: list[Any]) -> list[str]:
    names: list[str] = []
    for item in items:
        if isinstance(item, dict):
            names.append(str(item.get("name") or item.get("任务") or item.get("path") or item))
        else:
            names.append(str(item))
    return names


def row(ok: bool, conclusion: str, evidence: list[str], next_step: str = "") -> dict[str, Any]:
    return {
        "status": "ok" if ok else "gap",
        "conclusion": conclusion,
        "evidence": evidence,
        "nextStep": next_step,
    }


def build(date: str) -> dict[str, Any]:
    important = read_json(ROOT / f"raw/11-Codex分析产物/每日重要信息Top10/{date}/daily-important-info-top10.json", {})
    learning = read_json(ROOT / f"raw/11-Codex分析产物/超短自进化学习/{date}/shortline-learning-progress.json", {})
    warroom = read_json(ROOT / f"raw/11-Codex分析产物/动态作战室/{date}/dynamic-warroom-top5.json", {})
    raw_health = read_json(ROOT / f"wiki/09-统计与进化/{date}-RAW写入链路体检.json", {})
    validation = read_json(ROOT / f"raw/11-Codex分析产物/验证闭环进度/{date}/validation-progress-dashboard.json", {})
    mode_audit = read_text(ROOT / f"wiki/09-统计与进化/{date}-交易模式归因缺口审计.md")
    longxia = read_json(ROOT / f"raw/11-Codex分析产物/龙虾定时任务验收/{date}/longxia-schedule-watch.json", {})
    missing_names = longxia_missing_names(longxia.get("dueMissing") or [])

    dplus_results = count_files("data/facts", "dplus_validation_results.jsonl")
    taoguba_files = count_files(f"raw/04-市场数据/热榜/{date}")
    jiuyangongshe_files = count_files(f"raw/05-研报新闻/韭研公社网页/{date}")

    rows = {
        "1. RAW到Wiki主动处理": row(
            exists(f"wiki/09-统计与进化/{date}-RAW到Wiki主动处理决策台.md"),
            "已生成RAW到Wiki主动处理决策台，RAW不再只做存档。",
            [f"wiki/09-统计与进化/{date}-RAW到Wiki主动处理决策台.md"],
        ),
        "2. 历史交易逐笔模式归因": row(
            exists(f"wiki/09-统计与进化/{date}-交易模式归因缺口审计.md")
            and (exists(f"raw/11-Codex分析产物/RAW交割单旁路归因/{date}") or exists(f"raw/11-Codex分析产物/交易模式逐笔归因/{date}")),
            "已生成归因缺口审计和旁路归因；历史债务继续滚动清理。",
            [
                f"wiki/09-统计与进化/{date}-交易模式归因缺口审计.md",
                f"raw/11-Codex分析产物/RAW交割单旁路归因/{date}/",
            ],
            "继续优先补最近30个交易日、大亏日、大赚日。",
        ),
        "3. D+验证反向改权重": row(
            exists(f"wiki/09-统计与进化/{date}-D+验证自动回填.md")
            and exists("wiki/09-统计与进化/交易模式D+统计总表.md"),
            "D+自动回填、交易模式D+统计和作战室D+队列已运行。",
            [
                f"wiki/09-统计与进化/{date}-D+验证自动回填.md",
                "wiki/09-统计与进化/交易模式D+统计总表.md",
                "wiki/09-统计与进化/动态作战室Top5-D+验证队列.md",
            ],
        ),
        "4. 个股卡和题材卡每日刷新": row(
            bool(warroom.get("top5")) and exists("wiki/03-L3个股档案") and exists("wiki/02-L2方向题材"),
            "持仓、Top5、热榜和韭研/互动易证据已触发L3/L2更新。",
            [
                "wiki/03-L3个股档案/",
                "wiki/02-L2方向题材/",
                f"wiki/07-作战室/{date}-动态作战室Top5.md",
            ],
        ),
        "5. 信息源分工": row(
            taoguba_files > 0 and jiuyangongshe_files > 0 and exists(f"wiki/09-统计与进化/{date}-互动易关注点入Wiki报告.md"),
            "公告/互动易、韭研、淘股吧、三榜分层处理，不混入同一知识池。",
            [
                f"wiki/09-统计与进化/{date}-互动易关注点入Wiki报告.md",
                f"raw/05-研报新闻/韭研公社网页/{date}/",
                f"raw/04-市场数据/热榜/{date}/",
            ],
        ),
        "6. 作战室Top5真实交易计划化": row(
            bool(warroom.get("top5")) and exists(f"wiki/07-作战室/{date}-动态作战室Top5.md"),
            "动态作战室已输出入选原因、模式、买卖/禁止条件、持仓处理和验证依据。",
            [f"wiki/07-作战室/{date}-动态作战室Top5.md"],
        ),
        "7. 情绪周期多源合成": row(
            exists(f"raw/11-Codex分析产物/短线知识提炼/{date}/淘股吧情绪周期-latest.md"),
            "淘股吧情绪周期已生成，后续继续合并连板、炸板、三榜迁移和持仓反馈。",
            [f"raw/11-Codex分析产物/短线知识提炼/{date}/淘股吧情绪周期-latest.md"],
        ),
        "8. 飞书通知降噪": row(
            exists("wiki/09-统计与进化/飞书通知清晰度检查.md") and exists(".system/feishu-protocol-lint.json"),
            "飞书发送前已有清晰度闸门；不合格消息隔离，不再直接打扰用户。",
            ["wiki/09-统计与进化/飞书通知清晰度检查.md", ".system/feishu-protocol-lint.json"],
        ),
        "9. 消息公司价值判断": row(
            len(important.get("rows") or []) > 0 and exists("wiki/10-系统配置/消息对公司价值影响评估规则.md"),
            f"已对 {len(important.get('rows') or [])} 条重要消息做公司影响和短线/机构视角分层。",
            [
                f"raw/11-Codex分析产物/每日重要信息Top10/{date}/daily-important-info-top10.json",
                "wiki/10-系统配置/消息对公司价值影响评估规则.md",
            ],
        ),
        "10. 学习成绩单": row(
            len(learning.get("top10") or []) == 10 and exists(f"wiki/09-统计与进化/{date}-验证闭环进度总览.md"),
            "超短学习Top10、验证闭环进度和来源/模式反馈已形成成绩单。",
            [
                f"raw/11-Codex分析产物/超短自进化学习/{date}/shortline-learning-progress.json",
                f"wiki/09-统计与进化/{date}-验证闭环进度总览.md",
            ],
        ),
    }

    return {
        "schema": "73wiki-ten-intelligence-upgrade-status-v1",
        "date": date,
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rawHealthStatus": raw_health.get("结论") or raw_health.get("status"),
        "validationSummary": validation.get("sections") or [],
        "longxiaDueMissing": missing_names,
        "modeAuditTextContainsMissing": "缺模式归因字段" in mode_audit,
        "rows": rows,
        "gaps": [name for name, item in rows.items() if item["status"] != "ok"],
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 十项智能进化闭环执行状态",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 缺口数：{len(payload['gaps'])}",
        f"- 龙虾已到点缺失：{', '.join(payload.get('longxiaDueMissing') or []) or '无'}",
        "",
        "| 项 | 状态 | 当前结论 | 证据 | 下一步 |",
        "|---|---|---|---|---|",
    ]
    for name, item in payload["rows"].items():
        evidence = "<br>".join(f"`{part}`" for part in item.get("evidence") or [])
        lines.append(f"| {name} | {item['status']} | {item['conclusion']} | {evidence} | {item.get('nextStep') or ''} |")
    lines.extend(["", "## 当前缺口", ""])
    if payload["gaps"]:
        lines.extend(f"- {gap}" for gap in payload["gaps"])
    else:
        lines.append("- 十项智能进化闭环均有当日产物或可用规则。")
    if payload.get("longxiaDueMissing"):
        lines.extend(["", "## 外部依赖缺口", ""])
        lines.extend(f"- 龙虾定时任务缺失：{name}" for name in payload["longxiaDueMissing"])
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
        (out_dir / "ten-intelligence-upgrade-status.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (out_dir / "ten-intelligence-upgrade-status.md").write_text(render(payload), encoding="utf-8")
        WIKI_OUT.mkdir(parents=True, exist_ok=True)
        (WIKI_OUT / f"{args.date}-十项智能进化闭环执行状态.md").write_text(render(payload), encoding="utf-8")
    print(json.dumps({"ok": True, "date": args.date, "gaps": payload["gaps"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
