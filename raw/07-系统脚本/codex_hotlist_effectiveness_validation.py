#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw/04-市场数据/三榜热度合并"
OUT = ROOT / "raw/11-Codex分析产物/三榜有效性验证"
FACTS = ROOT / "data/facts/hotlist_effectiveness_results.jsonl"
WIKI = ROOT / "wiki/09-统计与进化/三榜热度有效性验证.md"


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + ("\n" if rows else ""), encoding="utf-8")


def symbol(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return "sh" + code
    if code.startswith("8"):
        return "bj" + code
    return "sz" + code


def fetch_bars(code: str) -> list[dict[str, Any]]:
    sym = symbol(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,80,qfq"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:
        return []
    rows = data.get("data", {}).get(sym, {}).get("qfqday") or data.get("data", {}).get(sym, {}).get("day") or []
    out = []
    for row in rows:
        try:
            out.append({"date": row[0], "close": float(row[2]), "high": float(row[3])})
        except Exception:
            continue
    return out


def future_return(code: str, date: str, base_close: float | None = None) -> dict[str, Any]:
    bars = fetch_bars(code)
    by_date = {x["date"]: x for x in bars}
    base = base_close or (by_date.get(date) or {}).get("close")
    future = [x for x in bars if x["date"] > date]
    out = {}
    for idx, node in ((0, "D+1"), (2, "D+3"), (4, "D+5")):
        bar = future[idx] if idx < len(future) else None
        out[node] = None if not bar or not base else round((bar["close"] - base) / base * 100, 2)
    return out


def source_bucket(row: dict[str, Any]) -> str:
    sources = " ".join(row.get("来源榜单") or [])
    has_ths = "同花顺" in sources
    has_tdx = "通达信" in sources
    has_tgb = "淘股吧" in sources
    count = sum([has_ths, has_tdx, has_tgb])
    if count >= 3:
        return "三榜共振"
    if has_ths and has_tgb:
        return "同花顺+淘股吧"
    if has_ths:
        return "同花顺单/主"
    if has_tgb:
        return "淘股吧单/主"
    if has_tdx:
        return "通达信单/主"
    return "未知来源"


def collect(limit_per_day: int = 30) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(RAW.glob("*/三榜热度合并.json")):
        payload = read_json(path, {})
        date = payload.get("日期") or path.parent.name
        for row in (payload.get("股票") or [])[:limit_per_day]:
            code = re.sub(r"\D", "", str(row.get("代码") or ""))[-6:]
            if not code:
                continue
            returns = future_return(code, date)
            rows.append({
                "schema": "73wiki-hotlist-effectiveness-result-v1",
                "date": date,
                "code": code,
                "name": row.get("名称") or "",
                "rank": row.get("综合排名"),
                "source_bucket": source_bucket(row),
                "source_count": row.get("来源数量"),
                "themes": row.get("概念标签") or [],
                "D+1": returns.get("D+1"),
                "D+3": returns.get("D+3"),
                "D+5": returns.get("D+5"),
            })
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by = defaultdict(list)
    for row in rows:
        by[row["source_bucket"]].append(row)
    out = []
    for bucket, items in by.items():
        vals = [x["D+1"] for x in items if x.get("D+1") is not None]
        out.append({
            "bucket": bucket,
            "samples": len(items),
            "available": len(vals),
            "hit_rate": round(sum(1 for x in vals if x >= 0) / len(vals) * 100, 2) if vals else None,
            "avg_d1": round(sum(vals) / len(vals), 2) if vals else None,
        })
    return sorted(out, key=lambda x: x["bucket"])


def main() -> int:
    rows = collect()
    write_jsonl(FACTS, rows)
    summary = summarize(rows)
    today = datetime.now().strftime("%Y-%m-%d")
    OUT.joinpath(today).mkdir(parents=True, exist_ok=True)
    (OUT / today / "hotlist-effectiveness.json").write_text(json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 三榜热度有效性验证",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 样本数：{len(rows)}",
        "- 口径：三榜合并每日Top30，按D+1收盘收益初步验证。",
        "",
        "| 来源分组 | 样本 | 可算 | D+1命中 | D+1均值 |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(f"| {row['bucket']} | {row['samples']} | {row['available']} | {row['hit_rate']} | {row['avg_d1']} |")
    lines += ["", "## 最近样本", "", "| 日期 | 股票 | 来源 | 排名 | D+1 | D+3 | D+5 |", "|---|---|---|---:|---:|---:|---:|"]
    for row in sorted(rows, key=lambda x: (x["date"], int(x.get("rank") or 999)), reverse=True)[:80]:
        lines.append(f"| {row['date']} | {row['name']} {row['code']} | {row['source_bucket']} | {row.get('rank')} | {row.get('D+1')} | {row.get('D+3')} | {row.get('D+5')} |")
    md = "\n".join(lines) + "\n"
    (OUT / today / "hotlist-effectiveness.md").write_text(md, encoding="utf-8")
    WIKI.write_text(md, encoding="utf-8")
    print(json.dumps({"ok": True, "rows": len(rows), "output": str(WIKI.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
