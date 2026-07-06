#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backtest message catalyst scores with next-trading-day market evidence."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "raw/07-系统脚本"
SCORE_DIR = ROOT / "raw/11-Codex分析产物/消息催化评分"
OUT_DIR = ROOT / "raw/11-Codex分析产物/消息催化回测"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|8\d{5})(?!\d)")


def load_calendar_module():
    spec = importlib.util.spec_from_file_location("codex_trading_calendar", SCRIPTS / "codex_trading_calendar.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load trading calendar")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_texts(paths: list[Path]) -> str:
    chunks = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            if path.suffix.lower() == ".json":
                chunks.append(json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False))
            else:
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
    return "\n".join(chunks)


def market_text(date: str, kind: str) -> tuple[str, list[str]]:
    roots = {
        "limit": [ROOT / f"raw/04-市场数据/每日涨停全景/{date}", ROOT / f"raw/04-市场数据/首板涨停催化/{date}"],
        "hot": [ROOT / f"raw/04-市场数据/同花顺热榜/{date}", ROOT / f"raw/04-市场数据/通达信热榜/{date}"],
        "board": [ROOT / f"raw/04-市场数据/板块强度/{date}", ROOT / f"raw/04-市场数据/板块四龙排序/{date}"],
    }.get(kind, [])
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".json"})
    return read_texts(files), [str(path.relative_to(ROOT)) for path in files[:20]]


def validate_row(row: dict[str, Any], next_day: str) -> dict[str, Any]:
    codes = row.get("impactCodes") or []
    keywords = row.get("keywords") or []
    title = row.get("title", "")
    if not codes:
        codes = sorted(set(CODE_RE.findall(title)))
    limit_text, limit_sources = market_text(next_day, "limit")
    hot_text, hot_sources = market_text(next_day, "hot")
    board_text, board_sources = market_text(next_day, "board")
    has_next_data = bool(limit_text or hot_text or board_text)
    if not has_next_data:
        status = "pending_next_day_data"
        hit_count = 0
        evidence = []
    else:
        limit_hits = [code for code in codes if code in limit_text]
        hot_hits = [code for code in codes if code in hot_text]
        keyword_hits = [key for key in keywords if key and (key in limit_text or key in hot_text or key in board_text)]
        hit_count = len(set(limit_hits + hot_hits)) + len(set(keyword_hits))
        evidence = []
        if limit_hits:
            evidence.append(f"涨停命中：{', '.join(limit_hits[:8])}")
        if hot_hits:
            evidence.append(f"热榜命中：{', '.join(hot_hits[:8])}")
        if keyword_hits:
            evidence.append(f"题材扩散：{', '.join(keyword_hits[:8])}")
        if row.get("score", 0) >= 75:
            status = "validated" if hit_count else "failed_high_score"
        elif row.get("score", 0) >= 55:
            status = "partial" if hit_count else "not_validated"
        else:
            status = "low_score_observed" if hit_count else "low_score_no_signal"
    return {
        "source": row.get("source"),
        "title": title,
        "score": row.get("score"),
        "impactCodes": codes,
        "nextDay": next_day,
        "status": status,
        "hitCount": hit_count,
        "evidence": evidence,
        "sources": {
            "limit": limit_sources,
            "hot": hot_sources,
            "board": board_sources,
        },
    }


def build(date: str) -> dict[str, Any]:
    calendar = load_calendar_module()
    next_day = calendar.next_trade_day(date).isoformat()
    score_payload = read_json(SCORE_DIR / date / "message-catalyst-score.json")
    rows = [validate_row(row, next_day) for row in score_payload.get("rows", [])[:80]]
    summary = {
        "total": len(rows),
        "validated": sum(1 for row in rows if row["status"] == "validated"),
        "partial": sum(1 for row in rows if row["status"] == "partial"),
        "failedHighScore": sum(1 for row in rows if row["status"] == "failed_high_score"),
        "pending": sum(1 for row in rows if row["status"] == "pending_next_day_data"),
    }
    return {
        "schema": "73wiki-message-catalyst-backtest-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": date,
        "nextTradeDay": next_day,
        "summary": summary,
        "rows": rows,
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 消息催化评分次日回测",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 次一交易日：{payload['nextTradeDay']}",
        f"- 总数：{payload['summary']['total']}",
        f"- 已验证：{payload['summary']['validated']}",
        f"- 部分验证：{payload['summary']['partial']}",
        f"- 高分未验证：{payload['summary']['failedHighScore']}",
        f"- 待次日数据：{payload['summary']['pending']}",
        "",
        "| 分数 | 来源 | 标题 | 状态 | 证据 |",
        "|---:|---|---|---|---|",
    ]
    for row in payload["rows"][:80]:
        evidence = "；".join(row.get("evidence") or []) or "-"
        lines.append(f"| {row.get('score')} | {row.get('source')} | {str(row.get('title', '')).replace('|', '/')} | {row.get('status')} | {evidence} |")
    if not payload["rows"]:
        lines.append("| - | - | 无评分记录 | - | - |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="消息催化评分次日回测")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    if args.write:
        out = OUT_DIR / args.date
        out.mkdir(parents=True, exist_ok=True)
        (out / "message-catalyst-backtest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "message-catalyst-backtest.md").write_text(render(payload), encoding="utf-8")
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / f"{args.date}-消息催化评分次日回测.md").write_text(render(payload), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
