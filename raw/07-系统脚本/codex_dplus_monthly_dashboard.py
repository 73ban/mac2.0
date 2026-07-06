#!/usr/bin/env python3
"""Build monthly D+ validation accuracy dashboard.

This is the accounting layer above the existing D+ queue/autofill scripts.
It reads factual JSONL files, computes hit rates, writes a WIKI report, and
emits a small SVG trend chart without external dependencies.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FACTS = ROOT / "data/facts"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
OUT_DIR = ROOT / ".llm-wiki/dplus-monthly-dashboard"

PREDICTIONS = FACTS / "warroom_candidate_predictions.jsonl"
WARROOM_D0_RESULTS = FACTS / "warroom_candidate_validation_results.jsonl"
DPLUS_RESULTS = FACTS / "dplus_validation_results.jsonl"
SUMMARY_JSON = FACTS / "dplus_monthly_accuracy_summary.json"


POSITIVE_DECISIONS = {"加分", "升级", "保留观察"}
WEAK_DECISIONS = {"降权观察", "降级观察"}
FAIL_DECISIONS = {"扣分", "降级", "归档"}
POSITIVE_ACTIONS = {"强于预期", "符合预期"}
WEAK_ACTIONS = {"弱于预期"}
FAIL_ACTIONS = {"证伪"}


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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def month_of(value: str) -> str:
    match = re.match(r"(\d{4}-\d{2})-\d{2}", str(value or ""))
    return match.group(1) if match else ""


def classify(row: dict[str, Any]) -> str:
    decision = str(row.get("decision") or "")
    price_action = str(row.get("priceAction") or "")
    if decision in POSITIVE_DECISIONS or price_action in POSITIVE_ACTIONS:
        return "hit"
    if decision in WEAK_DECISIONS or price_action in WEAK_ACTIONS:
        return "weak"
    if decision in FAIL_DECISIONS or price_action in FAIL_ACTIONS:
        return "fail"
    return "missing"


def number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    except Exception:
        return None


def symbol_for(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    if code.startswith("8"):
        return f"bj{code}"
    return f"sz{code}"


def fetch_kline_symbol(symbol: str, days: int = 80) -> list[dict[str, Any]]:
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
                }
            )
        except Exception:
            continue
    return out


def pct_for_date(bars: list[dict[str, Any]], date: str) -> float | None:
    for index, bar in enumerate(bars):
        if bar.get("date") != date or index == 0:
            continue
        prev_close = number(bars[index - 1].get("close"))
        close = number(bar.get("close"))
        if not prev_close or close is None:
            return None
        return round((close - prev_close) / prev_close * 100, 2)
    return None


def load_benchmark_cache() -> dict[str, dict[str, float | None]]:
    symbols = {
        "sh000001": "上证指数",
        "sz399001": "深证成指",
        "sz399006": "创业板指",
    }
    cache: dict[str, dict[str, float | None]] = {}
    for symbol, name in symbols.items():
        try:
            bars = fetch_kline_symbol(symbol)
        except Exception:
            bars = []
        for bar in bars:
            date = str(bar.get("date") or "")
            if not date:
                continue
            cache.setdefault(date, {})[name] = pct_for_date(bars, date)
    return cache


def normalize_result(row: dict[str, Any], source: str, benchmark: dict[str, dict[str, float | None]]) -> dict[str, Any]:
    date = str(row.get("date") or "")
    change = number(row.get("changePercent"))
    bench = benchmark.get(date, {})
    sh = bench.get("上证指数")
    cyb = bench.get("创业板指")
    relative_sh = round(change - sh, 2) if change is not None and sh is not None else None
    relative_cyb = round(change - cyb, 2) if change is not None and cyb is not None else None
    return {
        "source": source,
        "date": date,
        "month": month_of(date),
        "code": str(row.get("code") or ""),
        "name": str(row.get("name") or ""),
        "node": str(row.get("node") or ""),
        "role": str(row.get("role") or ""),
        "score": number(row.get("score")),
        "permission": str(row.get("permission") or ""),
        "decision": str(row.get("decision") or ""),
        "priceAction": str(row.get("priceAction") or ""),
        "changePercent": change,
        "bucket": classify(row),
        "benchmark": {
            "上证指数": sh,
            "深证成指": bench.get("深证成指"),
            "创业板指": cyb,
        },
        "relativeToSH": relative_sh,
        "relativeToCYB": relative_cyb,
        "resultId": str(row.get("resultId") or ""),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["month"]:
            by_month[row["month"]].append(row)
        if row["date"]:
            by_day[row["date"]].append(row)

    def stats(items: list[dict[str, Any]]) -> dict[str, Any]:
        counts = Counter(item["bucket"] for item in items)
        total = len(items)
        hit = counts["hit"]
        weak = counts["weak"]
        fail = counts["fail"]
        missing = counts["missing"]
        usable = hit + weak
        rel_values = [item["relativeToSH"] for item in items if item["relativeToSH"] is not None]
        return {
            "total": total,
            "hit": hit,
            "weak": weak,
            "fail": fail,
            "missing": missing,
            "strictHitRate": round(hit / total * 100, 2) if total else 0,
            "usableRate": round(usable / total * 100, 2) if total else 0,
            "failRate": round(fail / total * 100, 2) if total else 0,
            "avgRelativeToSH": round(sum(rel_values) / len(rel_values), 2) if rel_values else None,
        }

    return {
        "byMonth": {month: stats(items) for month, items in sorted(by_month.items())},
        "byDay": {date: stats(items) for date, items in sorted(by_day.items())},
        "bySource": {source: stats([row for row in rows if row["source"] == source]) for source in sorted({row["source"] for row in rows})},
        "byNode": {node: stats([row for row in rows if row["node"] == node]) for node in sorted({row["node"] for row in rows})},
        "failByRole": Counter(row["role"] or "未标注" for row in rows if row["bucket"] == "fail").most_common(20),
    }


def render_svg(day_stats: dict[str, Any], month: str) -> str:
    items = [(date, stat) for date, stat in sorted(day_stats.items()) if date.startswith(month)]
    width, height = 900, 280
    left, top, right, bottom = 56, 24, 24, 48
    chart_w = width - left - right
    chart_h = height - top - bottom
    if not items:
        points = ""
    else:
        max_x = max(1, len(items) - 1)
        pts = []
        for idx, (_, stat) in enumerate(items):
            x = left + chart_w * idx / max_x
            y = top + chart_h * (1 - float(stat.get("usableRate", 0)) / 100)
            pts.append(f"{x:.1f},{y:.1f}")
        points = " ".join(pts)
    labels = []
    for idx, (date, stat) in enumerate(items):
        if len(items) > 12 and idx % 2:
            continue
        max_x = max(1, len(items) - 1)
        x = left + chart_w * idx / max_x
        labels.append(f'<text x="{x:.1f}" y="{height - 18}" font-size="10" text-anchor="middle">{date[5:]}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{left}" y="18" font-size="16" font-weight="700">{month} D+验证可用命中率趋势</text>
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_h}" stroke="#999"/>
  <line x1="{left}" y1="{top + chart_h}" x2="{left + chart_w}" y2="{top + chart_h}" stroke="#999"/>
  <text x="12" y="{top + 5}" font-size="11">100%</text>
  <text x="20" y="{top + chart_h / 2 + 4}" font-size="11">50%</text>
  <text x="28" y="{top + chart_h + 4}" font-size="11">0%</text>
  <line x1="{left}" y1="{top + chart_h / 2}" x2="{left + chart_w}" y2="{top + chart_h / 2}" stroke="#ddd" stroke-dasharray="4 4"/>
  <polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="3"/>
  {"".join(labels)}
</svg>
'''


def render_markdown(month: str, payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    month_stat = summary["byMonth"].get(month, {})
    source_rows = "\n".join(
        f"| {source} | {stat['total']} | {stat['hit']} | {stat['weak']} | {stat['fail']} | {stat['usableRate']}% | {stat['avgRelativeToSH'] if stat['avgRelativeToSH'] is not None else ''} |"
        for source, stat in summary["bySource"].items()
    ) or "| - | - | - | - | - | - | - |"
    day_rows = "\n".join(
        f"| {date} | {stat['total']} | {stat['hit']} | {stat['weak']} | {stat['fail']} | {stat['usableRate']}% | {stat['avgRelativeToSH'] if stat['avgRelativeToSH'] is not None else ''} |"
        for date, stat in summary["byDay"].items()
        if date.startswith(month)
    ) or "| - | - | - | - | - | - | - |"
    fail_rows = "\n".join(f"| {role} | {count} |" for role, count in summary["failByRole"]) or "| - | - |"
    return f"""# {month} D+验证月度准确率趋势

更新时间：{payload['generatedAt']}

## 总结

```yaml
样本数: {month_stat.get('total', 0)}
严格命中率: {month_stat.get('strictHitRate', 0)}%
可用命中率: {month_stat.get('usableRate', 0)}%
失败率: {month_stat.get('failRate', 0)}%
平均跑赢上证: {month_stat.get('avgRelativeToSH', '')}
```

![D+验证趋势](../../.llm-wiki/dplus-monthly-dashboard/{month}-dplus-accuracy.svg)

## 来源表现

| 来源 | 样本 | 命中 | 弱命中 | 失败 | 可用命中率 | 平均跑赢上证 |
|---|---:|---:|---:|---:|---:|---:|
{source_rows}

## 日期趋势

| 日期 | 样本 | 命中 | 弱命中 | 失败 | 可用命中率 | 平均跑赢上证 |
|---|---:|---:|---:|---:|---:|---:|
{day_rows}

## 失败角色 Top20

| 角色 | 失败次数 |
|---|---:|
{fail_rows}

## 口径

- 命中：涨停级反馈、强于预期或符合预期。
- 弱命中：小涨、弱于高分预期，保留观察但不升权。
- 失败：下跌、证伪、归档、扣分。
- 大盘对比：自动对比上证指数、深证成指、创业板指。
- 板块对比：需要 Mac 本机脚本或用户导入 RAW 在候选数据里稳定写入板块代码或板块名称后再自动接入。
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default=datetime.now().strftime("%Y-%m"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    benchmark = load_benchmark_cache()
    rows: list[dict[str, Any]] = []
    rows.extend(normalize_result(row, "warroom_d0", benchmark) for row in read_jsonl(WARROOM_D0_RESULTS))
    rows.extend(normalize_result(row, "dplus", benchmark) for row in read_jsonl(DPLUS_RESULTS))
    rows = [row for row in rows if row["date"]]
    predictions = read_jsonl(PREDICTIONS)
    payload = {
        "schema": "73wiki-dplus-monthly-dashboard-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "month": args.month,
        "predictionCount": len(predictions),
        "resultCount": len(rows),
        "summary": summarize(rows),
        "outputs": {
            "json": "data/facts/dplus_monthly_accuracy_summary.json",
            "md": f"wiki/09-统计与进化/{args.month}-D+验证月度准确率趋势.md",
            "svg": f".llm-wiki/dplus-monthly-dashboard/{args.month}-dplus-accuracy.svg",
        },
    }
    if not args.dry_run:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        write_json(SUMMARY_JSON, payload)
        write_json(OUT_DIR / "latest-dplus-monthly-dashboard.json", payload)
        write_json(OUT_DIR / f"{args.month}-dplus-monthly-dashboard.json", payload)
        svg = render_svg(payload["summary"]["byDay"], args.month)
        (OUT_DIR / f"{args.month}-dplus-accuracy.svg").write_text(svg, encoding="utf-8")
        md = render_markdown(args.month, payload)
        (OUT_DIR / "latest-dplus-monthly-dashboard.md").write_text(md, encoding="utf-8")
        (WIKI_STATS / f"{args.month}-D+验证月度准确率趋势.md").write_text(md, encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
