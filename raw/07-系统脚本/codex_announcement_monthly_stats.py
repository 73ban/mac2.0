#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build monthly effectiveness stats for announcement events."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data/facts/announcement_event_validation_results.jsonl"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
OUT_JSON = ROOT / "data/facts/announcement_event_monthly_stats.json"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def month_of(row: dict[str, Any]) -> str:
    for key in ("到期日", "date", "验证日期", "生成时间"):
        value = str(row.get(key) or "")
        if len(value) >= 7 and value[4:5] == "-":
            return value[:7]
    return ""


def category(row: dict[str, Any]) -> str:
    text = str(row.get("公告类型") or row.get("公告类别") or row.get("事件类型") or row.get("规律标签") or "")
    if any(key in text for key in ("业绩", "预增", "扭亏", "快报")):
        return "业绩公告"
    if any(key in text for key in ("并购", "重组", "收购", "资产注入")):
        return "并购重组"
    if any(key in text for key in ("增持", "回购")):
        return "增持回购"
    if any(key in text for key in ("减持", "问询", "澄清", "监管", "风险")):
        return "风险公告"
    return text or "未分类"


def bucket(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get(key) or "") for key in ("反馈结论", "处理结论", "规律标签", "priceAction", "decision"))
    if any(key in text for key in ("涨停强反馈", "持续强反馈", "公告有效", "正反馈")):
        return "effective"
    if "一日游" in text:
        return "one_day"
    if any(key in text for key in ("负反馈", "强负反馈", "证伪", "风险强化")):
        return "negative"
    if any(key in text for key in ("弱反馈", "归档观察", "风险未扩散")):
        return "weak"
    return "unknown"


def summarize(rows: list[dict[str, Any]], month: str) -> dict[str, Any]:
    selected = [row for row in rows if month_of(row) == month]
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        by_category[category(row)].append(row)
        by_node[str(row.get("验证节点") or row.get("node") or "未标注")].append(row)

    def stats(items: list[dict[str, Any]]) -> dict[str, Any]:
        counts = Counter(bucket(row) for row in items)
        total = len(items)
        return {
            "total": total,
            "effective": counts["effective"],
            "weak": counts["weak"],
            "oneDay": counts["one_day"],
            "negative": counts["negative"],
            "unknown": counts["unknown"],
            "effectiveRate": round(counts["effective"] / total * 100, 2) if total else 0,
            "negativeRate": round(counts["negative"] / total * 100, 2) if total else 0,
            "oneDayRate": round(counts["one_day"] / total * 100, 2) if total else 0,
        }

    return {
        "schema": "73wiki-announcement-event-monthly-stats-v1",
        "month": month,
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": stats(selected),
        "byCategory": {key: stats(value) for key, value in sorted(by_category.items())},
        "byNode": {key: stats(value) for key, value in sorted(by_node.items())},
        "samples": selected[:200],
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['month']} 公告事件有效性统计",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        "",
        "## 总览",
        "",
        "| 总样本 | 有效 | 弱反馈 | 一日游 | 负反馈 | 有效率 | 负反馈率 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    s = payload["summary"]
    lines.append(f"| {s['total']} | {s['effective']} | {s['weak']} | {s['oneDay']} | {s['negative']} | {s['effectiveRate']}% | {s['negativeRate']}% |")
    lines.extend(["", "## 按公告类型", "", "| 类型 | 样本 | 有效 | 一日游 | 负反馈 | 有效率 |", "|---|---:|---:|---:|---:|---:|"])
    for key, row in payload["byCategory"].items():
        lines.append(f"| {key} | {row['total']} | {row['effective']} | {row['oneDay']} | {row['negative']} | {row['effectiveRate']}% |")
    lines.extend(["", "## 按验证节点", "", "| 节点 | 样本 | 有效 | 弱反馈 | 一日游 | 负反馈 |", "|---|---:|---:|---:|---:|---:|"])
    for key, row in payload["byNode"].items():
        lines.append(f"| {key} | {row['total']} | {row['effective']} | {row['weak']} | {row['oneDay']} | {row['negative']} |")
    lines.extend(["", "## 使用规则", "", "- 公告 D+0 强不等于可升级，必须看 D+1/D+3/D+5 持续性。", "- 并购、业绩、增持回购、风险公告分开统计，不能混成一个胜率。"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="公告事件月度有效性统计")
    parser.add_argument("--month", default=datetime.now().strftime("%Y-%m"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = summarize(read_jsonl(RESULTS), args.month)
    if args.write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        all_stats = {}
        if OUT_JSON.exists():
            try:
                all_stats = json.loads(OUT_JSON.read_text(encoding="utf-8"))
            except Exception:
                all_stats = {}
        all_stats[args.month] = payload
        OUT_JSON.write_text(json.dumps(all_stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / f"{args.month}-公告事件有效性统计.md").write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
