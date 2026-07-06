#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ATTRIBUTIONS = ROOT / "data/facts/trade_mode_attributions.jsonl"
FACTS_OUT = ROOT / "data/facts/trade_mode_dplus_results.jsonl"
OUT_ROOT = ROOT / "raw/11-Codex分析产物/交易模式D+验证"
WIKI_STATS = ROOT / "wiki/09-统计与进化"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def symbol_for(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    if code.startswith("8"):
        return f"bj{code}"
    return f"sz{code}"


def number(value: Any) -> float | None:
    text = str(value or "").replace(",", "").strip()
    if not text or text in {"-", "—"}:
        return None
    try:
        out = float(text)
    except Exception:
        return None
    if math.isnan(out) or out <= 0:
        return None
    return out


def fetch_kline(code: str, days: int = 90) -> list[dict[str, Any]]:
    symbol = symbol_for(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{days},qfq"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    rows = payload.get("data", {}).get(symbol, {}).get("qfqday") or payload.get("data", {}).get(symbol, {}).get("day") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            out.append(
                {
                    "date": str(row[0]),
                    "open": float(row[1]),
                    "close": float(row[2]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "volume": float(row[5]) if len(row) > 5 else None,
                }
            )
        except Exception:
            continue
    return out


def bars_after(bars: list[dict[str, Any]], trade_date: str) -> list[dict[str, Any]]:
    return [bar for bar in bars if str(bar.get("date") or "") > trade_date]


def pct(base: float | None, value: float | None) -> float | None:
    if not base or value is None:
        return None
    return round((value - base) / base * 100, 2)


def classify_return(value: float | None) -> str:
    if value is None:
        return "missing"
    if value >= 9.5:
        return "limit_like"
    if value >= 5:
        return "strong"
    if value >= 0:
        return "positive"
    if value > -5:
        return "weak"
    return "fail"


def build_rows(attributions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cache: dict[str, list[dict[str, Any]]] = {}
    out: list[dict[str, Any]] = []
    for item in attributions:
        code = re.sub(r"\D", "", str(item.get("code") or ""))[-6:]
        trade_date = str(item.get("date") or "")
        if not code or not trade_date:
            continue
        if code not in cache:
            try:
                cache[code] = fetch_kline(code)
            except Exception:
                cache[code] = []
        future = bars_after(cache[code], trade_date)
        entry = number(item.get("price"))
        nodes: dict[str, dict[str, Any]] = {}
        for idx, node in ((0, "D+1"), (2, "D+3"), (4, "D+5")):
            bar = future[idx] if idx < len(future) else None
            close_return = pct(entry, bar.get("close") if bar else None)
            high_return = pct(entry, bar.get("high") if bar else None)
            nodes[node] = {
                "date": bar.get("date") if bar else "",
                "close": bar.get("close") if bar else None,
                "high": bar.get("high") if bar else None,
                "close_return_pct": close_return,
                "high_return_pct": high_return,
                "bucket": classify_return(close_return),
            }
        out.append(
            {
                "schema": "73wiki-trade-mode-dplus-result-v1",
                "result_id": f"trade-mode-dplus:{item.get('attribution_id')}",
                "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "date": trade_date,
                "code": code,
                "name": item.get("name") or "",
                "action": item.get("action") or "",
                "entry_price": entry,
                "primary_mode": item.get("primary_mode") or "待人工归因",
                "secondary_modes": item.get("secondary_modes") or [],
                "mode_source": item.get("mode_source") or "",
                "mode_confidence": item.get("confidence") or "",
                "trade_source": item.get("source") or "",
                "nodes": nodes,
            }
        )
    return out


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_mode[row["primary_mode"]].append(row)

    def mode_stats(items: list[dict[str, Any]]) -> dict[str, Any]:
        stats: dict[str, Any] = {"samples": len(items)}
        for node in ("D+1", "D+3", "D+5"):
            available = [row for row in items if row["nodes"][node]["close_return_pct"] is not None]
            returns = [row["nodes"][node]["close_return_pct"] for row in available]
            hit = [x for x in returns if x >= 0]
            strong = [x for x in returns if x >= 5]
            fail = [x for x in returns if x <= -5]
            stats[node] = {
                "available": len(available),
                "hit": len(hit),
                "strong": len(strong),
                "fail": len(fail),
                "hit_rate": round(len(hit) / len(available) * 100, 2) if available else None,
                "strong_rate": round(len(strong) / len(available) * 100, 2) if available else None,
                "fail_rate": round(len(fail) / len(available) * 100, 2) if available else None,
                "avg_return": round(sum(returns) / len(returns), 2) if returns else None,
            }
        return stats

    return {
        "byMode": {mode: mode_stats(items) for mode, items in sorted(by_mode.items())},
        "total": len(rows),
    }


def render_md(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        f"# {date.today().isoformat()} 交易模式D+验证按模式统计",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 逐笔样本：{len(rows)}",
        "- 口径：以逐笔交易归因的成交价为基准，统计后续第1/3/5个交易日收盘收益；这是模式验证，不是买卖建议。",
        "",
        "## 按主模式统计",
        "",
        "| 主模式 | 样本 | D+1可算 | D+1命中率 | D+1均值 | D+3可算 | D+3命中率 | D+3均值 | D+5可算 | D+5命中率 | D+5均值 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, stats in sorted(summary["byMode"].items(), key=lambda kv: kv[1]["samples"], reverse=True):
        d1, d3, d5 = stats["D+1"], stats["D+3"], stats["D+5"]
        def fmt(value: Any) -> str:
            return "待数据" if value is None else str(value)
        lines.append(
            f"| {mode} | {stats['samples']} | {d1['available']} | {fmt(d1['hit_rate'])} | {fmt(d1['avg_return'])} | "
            f"{d3['available']} | {fmt(d3['hit_rate'])} | {fmt(d3['avg_return'])} | "
            f"{d5['available']} | {fmt(d5['hit_rate'])} | {fmt(d5['avg_return'])} |"
        )
    lines += [
        "",
        "## 最近样本明细",
        "",
        "| 日期 | 股票 | 主模式 | 入场价 | D+1 | D+3 | D+5 |",
        "|---|---|---|---:|---|---|---|",
    ]
    for row in sorted(rows, key=lambda x: (x["date"], x["code"]), reverse=True)[:80]:
        def node_text(node: str) -> str:
            item = row["nodes"][node]
            if item["close_return_pct"] is None:
                return "待数据"
            return f"{item['date']} {item['close_return_pct']}%"
        lines.append(
            f"| {row['date']} | {row['name']} {row['code']} | {row['primary_mode']} | {row['entry_price'] or ''} | "
            f"{node_text('D+1')} | {node_text('D+3')} | {node_text('D+5')} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    attributions = read_jsonl(ATTRIBUTIONS)
    rows = build_rows(attributions)
    summary = summarize(rows)
    today = date.today().isoformat()
    out_dir = OUT_ROOT / today
    payload = {
        "schema": "73wiki-trade-mode-dplus-bridge-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "row_count": len(rows),
        "summary": summary,
        "rows": rows,
    }
    if args.write:
        out_dir.mkdir(parents=True, exist_ok=True)
        write_text(out_dir / "trade-mode-dplus.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        md = render_md(rows, summary)
        write_text(out_dir / "trade-mode-dplus.md", md)
        write_text(WIKI_STATS / f"{today}-交易模式D+验证按模式统计.md", md)
        write_text(FACTS_OUT, "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""))
    print(json.dumps({"ok": True, "rows": len(rows), "output": str((out_dir / 'trade-mode-dplus.md').relative_to(ROOT)) if args.write else ""}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
