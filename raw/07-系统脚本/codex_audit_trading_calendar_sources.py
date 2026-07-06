#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit whether the local A-share calendar has official source evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CALENDAR = ROOT / "data/facts/a_share_trading_calendar.json"
WIKI_CONFIG = ROOT / "wiki/10-系统配置"


def load() -> dict[str, Any]:
    try:
        return json.loads(CALENDAR.read_text(encoding="utf-8"))
    except Exception:
        return {}


def audit(year: str) -> dict[str, Any]:
    data = load()
    year_data = (data.get("years") or {}).get(year, {})
    review = data.get("officialReview") or {}
    source = str(year_data.get("source") or "")
    urls = year_data.get("officialUrls") or []
    has_official = bool(urls) and any(domain in " ".join(urls) for domain in ("sse.com.cn", "szse.cn", "csrc.gov.cn"))
    return {
        "schema": "73wiki-trading-calendar-source-audit-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "year": year,
        "calendarPath": str(CALENDAR.relative_to(ROOT)),
        "status": "official_verified" if has_official else "pending_official_exchange_notice",
        "source": source,
        "officialUrls": urls,
        "review": review,
        "closedCount": len(year_data.get("closed") or []),
        "openOverrideCount": len(year_data.get("open") or []),
        "requiredAction": "" if has_official else "补沪深交易所或证监会年度休市公告URL，再复核 closed/open 列表。",
    }


def render(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {payload['year']} A股交易日历官方来源审计",
            "",
            f"- 生成时间：{payload['generatedAt']}",
            f"- 状态：{payload['status']}",
            f"- 日历文件：`{payload['calendarPath']}`",
            f"- 休市覆盖：{payload['closedCount']} 天",
            f"- 开市覆盖：{payload['openOverrideCount']} 天",
            f"- 来源说明：{payload['source']}",
            f"- 官方URL：{', '.join(payload['officialUrls']) if payload['officialUrls'] else '未登记'}",
            "",
            "## 处理",
            "",
            f"- {payload['requiredAction'] or '已具备官方来源证据。'}",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="交易日历官方来源审计")
    parser.add_argument("--year", default=datetime.now().strftime("%Y"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = audit(args.year)
    if args.write:
        WIKI_CONFIG.mkdir(parents=True, exist_ok=True)
        (WIKI_CONFIG / f"{args.year}-A股交易日历官方来源审计.md").write_text(render(payload), encoding="utf-8")
        (WIKI_CONFIG / f"{args.year}-A股交易日历官方来源审计.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "official_verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
