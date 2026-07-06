#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create D+ validation queue for one-minute intraday watch alerts."""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from codex_trading_calendar import add_trade_days


ROOT = Path(__file__).resolve().parents[2]
FACTS = ROOT / "data" / "facts" / "intraday_minute_watch_alerts.jsonl"
RESULTS = ROOT / "data" / "facts" / "intraday_minute_watch_validation_results.jsonl"
OUT_ROOT = ROOT / "raw" / "11-Codex分析产物" / "盘中一分钟提醒验证"
WIKI_STATS = ROOT / "wiki" / "09-统计与进化"
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|8\d{5})(?!\d)")


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def append_jsonl_unique(path: Path, rows: list[dict[str, Any]], key: str) -> int:
    seen = {str(item.get(key)) for item in read_jsonl(path) if item.get(key)}
    added = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            row_key = str(row.get(key) or "")
            if not row_key or row_key in seen:
                continue
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            seen.add(row_key)
            added += 1
    return added


def unique_alerts(date: str) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in read_jsonl(FACTS):
        if item.get("date") != date or not item.get("signature"):
            continue
        category = str(item.get("category") or "")
        if "持仓" in category:
            group = "holding"
        elif "作战室" in category:
            group = "warroom"
        else:
            group = category
        key = f"{item.get('subject')}:{group}"
        old = out.get(key)
        if old is None or str(item.get("generatedAt") or "") >= str(old.get("generatedAt") or ""):
            out[key] = item
    return list(out.values())


def extract_code(text: str) -> str:
    match = CODE_RE.search(text or "")
    return match.group(0) if match else ""


def symbol_for(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    if code.startswith("8"):
        return f"bj{code}"
    return f"sz{code}"


def fetch_quote(code: str) -> dict[str, Any]:
    if not code:
        return {}
    try:
        req = urllib.request.Request(f"https://qt.gtimg.cn/q={symbol_for(code)}", headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=8).read().decode("gb18030", errors="ignore")
    except Exception:
        return {}
    match = re.search(r'="([^"]*)"', raw)
    if not match:
        return {}
    fields = match.group(1).split("~")
    if len(fields) < 35:
        return {}
    try:
        price = float(fields[3])
        prev = float(fields[4])
        change = (price - prev) / prev * 100 if prev else None
    except Exception:
        change = None
    return {"code": code, "name": fields[1], "price": fields[3], "changePercent": round(change, 2) if change is not None else None, "time": fields[30] if len(fields) > 30 else ""}


def classify(alert: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
    level = alert.get("level")
    category = str(alert.get("category") or "")
    change = quote.get("changePercent")
    status = "pending"
    verdict = "待后续验证"
    if change is not None:
        if "风险" in category and change <= -3:
            status, verdict = "hit", "风险提醒有效"
        elif "风险" in category and change >= 3:
            status, verdict = "miss", "风险提醒偏谨慎"
        elif "机会" in category and change >= 3:
            status, verdict = "hit", "机会提醒有效"
        elif "机会" in category and change < 0:
            status, verdict = "miss", "机会提醒失效"
        else:
            status, verdict = "watch", "反馈不强，继续D+1/D+3"
    return {
        "status": status,
        "verdict": verdict,
        "changePercent": change,
        "quote": quote,
        "level": level,
    }


def build(date: str) -> dict[str, Any]:
    alerts = unique_alerts(date)
    rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    for item in alerts:
        code = extract_code(str(item.get("subject") or ""))
        quote = fetch_quote(code)
        cls = classify(item, quote)
        d1 = add_trade_days(date, 1).isoformat()
        d3 = add_trade_days(date, 3).isoformat()
        d5 = add_trade_days(date, 5).isoformat()
        row = {
            "alertId": f"intraday:{date}:{item.get('signature')}",
            "date": date,
            "generatedAt": item.get("generatedAt"),
            "level": item.get("level"),
            "category": item.get("category"),
            "subject": item.get("subject"),
            "conclusion": item.get("conclusion"),
            "code": code,
            "D+1": d1,
            "D+3": d3,
            "D+5": d5,
            **cls,
        }
        rows.append(row)
        result_rows.append({"schema": "73wiki-intraday-alert-validation-v1", "resultId": f"{row['alertId']}:D0", "node": "D+0", **row})
    return {"schema": "73wiki-intraday-alert-validation-run-v1", "date": date, "generatedAt": now_text(), "count": len(rows), "rows": rows, "resultRows": result_rows}


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 盘中一分钟提醒验证",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 入队/验证样本：{payload['count']}",
        "",
        "| 等级 | 类别 | 对象 | D+0结论 | 涨跌幅 | D+1 | D+3 | D+5 |",
        "|---|---|---|---|---:|---|---|---|",
    ]
    for row in payload["rows"]:
        change = "" if row.get("changePercent") is None else f"{row['changePercent']:.2f}"
        lines.append(f"| {row['level']} | {row['category']} | {row['subject']} | {row['verdict']} | {change} | {row['D+1']} | {row['D+3']} | {row['D+5']} |")
    if not payload["rows"]:
        lines.append("| - | - | 暂无样本 | - | - | - | - | - |")
    lines.extend(["", "## 规则", "", "- S/A/B 都入验证队列，但只有 S/A 会推送。", "- 风险提醒和机会提醒分开统计，不能混在一起算准确率。"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="盘中一分钟提醒D+验证")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    added = 0
    if args.write:
        out = OUT_ROOT / args.date
        out.mkdir(parents=True, exist_ok=True)
        serializable = dict(payload)
        serializable.pop("resultRows", None)
        (out / "intraday-alert-validation.json").write_text(json.dumps(serializable, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md = render_md(payload)
        (out / "intraday-alert-validation.md").write_text(md, encoding="utf-8")
        (WIKI_STATS / f"{args.date}-盘中一分钟提醒验证.md").write_text(md, encoding="utf-8")
        added = append_jsonl_unique(RESULTS, payload["resultRows"], "resultId")
    print(json.dumps({"ok": True, "date": args.date, "count": payload["count"], "addedResults": added}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
