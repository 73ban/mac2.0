#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DPLUS = ROOT / "data/facts/trade_mode_dplus_results.jsonl"
WIKI = ROOT / "wiki/09-统计与进化/我的交易模式画像.md"
OUT = ROOT / "raw/11-Codex分析产物/我的模式画像"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def r(row: dict[str, Any], node: str = "D+1") -> float | None:
    try:
        return float(((row.get("nodes") or {}).get(node) or {}).get("close_return_pct"))
    except Exception:
        return None


def main() -> int:
    rows = read_jsonl(DPLUS)
    by = defaultdict(list)
    by_month = defaultdict(list)
    for row in rows:
        by[str(row.get("primary_mode") or "待人工归因")].append(row)
        by_month[str(row.get("date") or "")[:7]].append(row)
    lines = [
        "# 我的交易模式画像",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 逐笔样本：{len(rows)}",
        "- 目标：半年后能回答我最赚钱的模式、最亏钱的模式、最容易冲动的模式。",
        "",
        "## 按模式",
        "",
        "| 模式 | 样本 | 可算 | D+1命中 | D+1失败 | D+1均值 | 当前判断 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for mode, items in sorted(by.items(), key=lambda kv: len(kv[1]), reverse=True):
        vals = [r(x) for x in items]
        vals = [x for x in vals if x is not None]
        hit = round(sum(1 for x in vals if x >= 0) / len(vals) * 100, 2) if vals else None
        fail = round(sum(1 for x in vals if x <= -5) / len(vals) * 100, 2) if vals else None
        avg = round(sum(vals) / len(vals), 2) if vals else None
        if len(vals) < 3:
            judge = "样本不足"
        elif avg >= 3 and (hit or 0) >= 55:
            judge = "优势候选"
        elif avg <= -3 or (fail or 0) >= 35:
            judge = "亏损来源"
        else:
            judge = "中性待拆分"
        lines.append(f"| {mode} | {len(items)} | {len(vals)} | {hit} | {fail} | {avg} | {judge} |")
    lines += ["", "## 按月份", "", "| 月份 | 样本 | D+1均值 | 主要模式 |", "|---|---:|---:|---|"]
    for month, items in sorted(by_month.items()):
        vals = [r(x) for x in items]
        vals = [x for x in vals if x is not None]
        avg = round(sum(vals) / len(vals), 2) if vals else None
        counts = defaultdict(int)
        for item in items:
            counts[str(item.get("primary_mode") or "待人工归因")] += 1
        top = "、".join([f"{k}({v})" for k, v in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:3]])
        lines.append(f"| {month} | {len(items)} | {avg} | {top} |")
    md = "\n".join(lines) + "\n"
    WIKI.write_text(md, encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")
    OUT.joinpath(today).mkdir(parents=True, exist_ok=True)
    (OUT / today / "user-mode-profile.md").write_text(md, encoding="utf-8")
    print(json.dumps({"ok": True, "rows": len(rows), "output": str(WIKI.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
