#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A-share trading calendar helper for 73神话.

The local calendar file is the source of truth. If a year is not covered, the
helper falls back to weekdays and marks the result as fallback so reports can
surface the gap instead of silently treating holidays as trading days.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CALENDAR_PATH = ROOT / "data/facts/a_share_trading_calendar.json"


def _read_calendar() -> dict[str, Any]:
    try:
        data = json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


def parse_day(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _year_config(day: date) -> dict[str, Any]:
    years = _read_calendar().get("years", {})
    config = years.get(str(day.year), {}) if isinstance(years, dict) else {}
    return config if isinstance(config, dict) else {}


def trading_day_info(value: str | date) -> dict[str, Any]:
    day = parse_day(value)
    config = _year_config(day)
    day_text = day.isoformat()
    explicit_open = set(config.get("open", []) or [])
    explicit_closed = set(config.get("closed", []) or [])
    source = config.get("source") or "weekday_fallback"

    if day_text in explicit_open:
        is_trade_day = True
        reason = "calendar_open_override"
        fallback = False
    elif day_text in explicit_closed:
        is_trade_day = False
        reason = "calendar_closed_override"
        fallback = False
    elif config:
        is_trade_day = day.weekday() < 5
        reason = "calendar_weekday_rule"
        fallback = False
    else:
        is_trade_day = day.weekday() < 5
        reason = "weekday_fallback_no_year_calendar"
        fallback = True

    return {
        "date": day_text,
        "isTradeDay": is_trade_day,
        "reason": reason,
        "fallback": fallback,
        "calendarPath": str(CALENDAR_PATH.relative_to(ROOT)),
        "source": source,
    }


def is_trade_day(value: str | date) -> bool:
    return bool(trading_day_info(value)["isTradeDay"])


def next_trade_day(value: str | date, include_self: bool = False) -> date:
    current = parse_day(value)
    if not include_self:
        current += timedelta(days=1)
    while not is_trade_day(current):
        current += timedelta(days=1)
    return current


def add_trade_days(value: str | date, count: int) -> date:
    current = parse_day(value)
    added = 0
    while added < count:
        current = next_trade_day(current)
        added += 1
    return current


def calendar_note(value: str | date) -> str:
    info = trading_day_info(value)
    if info["fallback"]:
        return f"缺 {parse_day(value).year} A股交易日历，已临时按周一至周五回退；需补 {info['calendarPath']}。"
    return f"A股交易日历：{info['calendarPath']}；来源：{info['source']}；规则：{info['reason']}。"


def main() -> int:
    parser = argparse.ArgumentParser(description="73神话 A股交易日历查询")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--next", action="store_true", help="Print next trading day after --date")
    parser.add_argument("--add", type=int, default=0, help="Add N trading days from --date")
    args = parser.parse_args()

    payload = trading_day_info(args.date)
    if args.next:
        payload["nextTradeDay"] = next_trade_day(args.date).isoformat()
    if args.add:
        payload[f"D+{args.add}"] = add_trade_days(args.date, args.add).isoformat()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
