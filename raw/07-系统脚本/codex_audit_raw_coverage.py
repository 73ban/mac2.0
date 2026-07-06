#!/usr/bin/env python3
"""Audit monthly RAW trade-slip and review coverage.

Usage:
  python3 raw/07-系统脚本/codex_audit_raw_coverage.py --month 2026-06 --as-of 2026-06-28
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date as Date
from pathlib import Path

from codex_trading_calendar import is_trade_day


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.lower() == ".xlsx" or data.startswith(b"PK\x03\x04") or data.startswith(b"\xd0\xcf\x11\xe0"):
        return ""
    for encoding in ("utf-8", "gbk", "gb18030", "latin1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def date_from_path(path: Path, month: str) -> str | None:
    pattern = month.replace("-", r"[-.]?")
    match = re.search(rf"{pattern}[-.]?(\d{{2}})", str(path))
    if match:
        return f"{month}-{match.group(1)}"
    compact = month.replace("-", "")
    match = re.search(rf"{compact}(\d{{2}})", str(path))
    if match:
        return f"{month}-{match.group(1)}"
    return None


def is_weekend(iso_date: str) -> bool:
    return not is_trade_day(iso_date)


def is_template(path: Path, text: str) -> bool:
    if not text.strip():
        return path.suffix.lower() in {".md", ".txt"}
    markers = [
        "买入/卖出 [股票名称/代码]",
        "2026-06-29-盘后复盘RAW",
        "盘后复盘RAW",
        "[股票名称/代码]",
        "[买入/卖出]",
    ]
    return any(marker in text for marker in markers)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def collect_raw(month: str, as_of: str | None) -> dict[str, dict]:
    result: dict[str, dict] = defaultdict(lambda: {"trade_files": [], "review_files": [], "template_files": []})
    sources = [
        (ROOT / "raw/01-交割单", "trade_files"),
        (ROOT / "raw/02-每日复盘", "review_files"),
    ]
    for base, bucket in sources:
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            day = date_from_path(path, month)
            if not day:
                continue
            if as_of and day > as_of:
                continue
            rel = path.relative_to(ROOT).as_posix()
            text = read_text(path)
            if is_template(path, text):
                result[day]["template_files"].append(rel)
                continue
            result[day][bucket].append(rel)
    return dict(result)


def build(month: str, as_of: str | None) -> dict:
    raw = collect_raw(month, as_of)
    stats = load_json(ROOT / f"data/trading/{month}-trade-statistics-draft.json")
    overrides = load_json(ROOT / f"data/trading/{month}-manual-overrides.json")
    stats_days = stats.get("days", {})
    excluded = overrides.get("exclude_dates", {})
    days = {}

    for day in sorted(set(raw) | set(stats_days) | set(overrides.get("days", {})) | set(excluded)):
        raw_day = raw.get(day, {"trade_files": [], "review_files": [], "template_files": []})
        stat = stats_days.get(day, {})
        best = stat.get("best_pnl")
        status = "可统计" if best else "待核验"
        if day in excluded:
            status = "排除"
        elif is_weekend(day):
            status = "周末/非交易日"
        elif raw_day.get("template_files") and not raw_day.get("trade_files") and not raw_day.get("review_files"):
            status = "模板，不作证据"
        notes = []
        if day in excluded:
            notes.append(excluded[day])
        notes.extend(overrides.get("days", {}).get(day, {}).get("notes", []))
        days[day] = {
            "date": day,
            "status": status,
            "hasTrade": bool(raw_day.get("trade_files")),
            "hasReview": bool(raw_day.get("review_files")),
            "pnlLabel": best.get("label") if best else None,
            "pnl": best.get("value") if best else None,
            "tradeFiles": raw_day.get("trade_files", []),
            "reviewFiles": raw_day.get("review_files", []),
            "templateFiles": raw_day.get("template_files", []),
            "notes": notes,
        }

    return {
        "schema": "73wiki-raw-coverage-index-v1",
        "month": month,
        "asOf": as_of,
        "days": days,
        "summary": {
            "dates": len(days),
            "statable": sum(1 for x in days.values() if x["status"] == "可统计"),
            "pending": sum(1 for x in days.values() if x["status"] == "待核验"),
            "excluded": sum(1 for x in days.values() if x["status"] in {"排除", "周末/非交易日", "模板，不作证据"}),
        },
    }


def money(value: float | None) -> str:
    if value is None:
        return "待核验"
    return f"{value:+,.0f}"


def write_outputs(index: dict) -> None:
    month = index["month"]
    json_path = ROOT / f"data/trading/{month}-raw-coverage-index.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = []
    for day, item in index["days"].items():
        notes = "；".join(item["notes"])[:120] if item["notes"] else ""
        rows.append(
            "| {date} | {status} | {trade} | {review} | {label} | {pnl} | {notes} |".format(
                date=day,
                status=item["status"],
                trade="有" if item["hasTrade"] else "无",
                review="有" if item["hasReview"] else "无",
                label=item["pnlLabel"] or "待核验",
                pnl=money(item["pnl"]),
                notes=notes,
            )
        )

    md = "\n".join(
        [
            f"# {month} RAW交割单复盘覆盖索引",
            "",
            f"更新时间：{index['asOf'] or '未指定'}",
            "",
            "## 用途",
            "",
            "本页把 `raw/01-交割单`、`raw/02-每日复盘` 和月度统计 JSON 对齐，防止回答交易问题时漏查真实 raw。",
            "",
            "## 快照",
            "",
            "| 项目 | 数量 |",
            "|---|---:|",
            f"| 覆盖日期 | {index['summary']['dates']} |",
            f"| 可统计日期 | {index['summary']['statable']} |",
            f"| 待核验日期 | {index['summary']['pending']} |",
            f"| 排除/模板/非交易日 | {index['summary']['excluded']} |",
            "",
            "## 每日覆盖",
            "",
            "| 日期 | 状态 | 交割单 | 复盘 | 盈亏口径 | 盈亏 | 备注 |",
            "|---|---|---|---|---|---:|---|",
            *rows,
            "",
            "## 机器索引",
            "",
            f"- `data/trading/{month}-raw-coverage-index.json`",
            "",
            "## 使用规则",
            "",
            "- 交割单优先于复盘；复盘用于解释逻辑，不能覆盖成交事实。",
            "- 模板、周末导入目录、缺账户口径的日期不能硬算净值。",
            "- 后续新增交割单或复盘后，重新运行本脚本刷新索引。",
        ]
    )
    md_path = ROOT / "wiki/06-持仓与资金管理" / f"{month}-RAW交割单复盘覆盖索引.md"
    md_path.write_text(md + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "wiki": str(md_path), "summary": index["summary"]}, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", required=True)
    parser.add_argument("--as-of")
    args = parser.parse_args()
    write_outputs(build(args.month, args.as_of))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
