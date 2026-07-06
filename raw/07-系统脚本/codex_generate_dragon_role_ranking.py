#!/usr/bin/env python3
"""Generate stock-level dragon role ranking from fact-layer RAW."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw/04-市场数据"
RAW_ANALYSIS = ROOT / "raw/11-Codex分析产物"
WAR = ROOT / "wiki/07-作战室"

NOISE_BOARDS = {
    "昨日上榜",
    "昨日涨停",
    "昨日首板",
    "昨日连板",
    "最近多板",
    "最近异动",
    "近期新高",
    "昨日断板",
    "基金重仓",
    "陆股通重仓",
    "MSCI成份",
    "微小盘股",
    "大盘股",
    "高股息股",
    "高分红股",
    "专项贷款",
}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def number(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(str(value).replace("%", "").replace("+", "").replace(",", "").strip())
    except Exception:
        return 0.0


def code_of(row: dict[str, Any]) -> str:
    return str(row.get("代码") or row.get("股票代码") or "").zfill(6)


def name_of(row: dict[str, Any]) -> str:
    return str(row.get("名称") or row.get("股票名称") or "")


def time_value(value: Any) -> int:
    match = re.match(r"(\d{2}):(\d{2}):(\d{2})", str(value or "15:00:00"))
    if not match:
        return 999999
    hour, minute, second = map(int, match.groups())
    return hour * 3600 + minute * 60 + second


def fund(row: dict[str, Any], key: str = "主力净额万元") -> float:
    funds = row.get("资金流向")
    if not isinstance(funds, dict):
        return 0.0
    return number(funds.get(key))


def seal_money(row: dict[str, Any]) -> float:
    return number(row.get("封单金额")) or number(row.get("最大封单额_万")) * 10000


def limit_amount(row: dict[str, Any]) -> float:
    return number(row.get("涨停成交额_万"))


def clean_boards(code: str, stock_boards: dict[str, Any], limit: int = 6) -> list[str]:
    raw = stock_boards.get("股票板块") if isinstance(stock_boards, dict) else {}
    item = raw.get(code) if isinstance(raw, dict) else None
    boards = item.get("板块", []) if isinstance(item, dict) else []
    if not isinstance(boards, list):
        return []
    useful = [str(x) for x in boards if str(x) and str(x) not in NOISE_BOARDS]
    return useful[:limit]


def rank_map(rows: list[dict[str, Any]], key_func) -> dict[str, int]:
    ranked = sorted(rows, key=key_func, reverse=True)
    return {code_of(row): index for index, row in enumerate(ranked, 1)}


def role_label(count: int) -> str:
    if count >= 4:
        return "四龙合体"
    if count == 3:
        return "三龙共振"
    if count == 2:
        return "双龙共振"
    return "单龙观察"


def md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return lines


def build(date: str) -> dict[str, Any]:
    daily = read_json(RAW / "每日涨停全景" / date / "tdx-daily-limit.json", {}).get("记录") or []
    turnover = read_json(RAW / "通达信成交额排名" / date / "tdx-成交额Top100.json", {}).get("数据") or []
    hot = read_json(RAW / "通达信热榜" / date / "tdx-hot-top100.json", {}).get("data") or []
    stock_boards = read_json(RAW / "板块成分股" / date / "tdx-stock-boards.json", {})

    turnover_map = {str(row.get("股票代码") or row.get("代码") or "").zfill(6): row for row in turnover}
    hot_map = {str(row.get("股票代码") or row.get("代码") or "").zfill(6): row for row in hot}
    seal_rank = rank_map(daily, seal_money)
    fund_rank = rank_map(daily, fund)
    super_rank = rank_map(daily, lambda row: fund(row, "超大单净额万元"))
    limit_amount_rank = rank_map(daily, limit_amount)

    records = []
    for row in daily:
        code = code_of(row)
        turn = turnover_map.get(code, {})
        hot_row = hot_map.get(code, {})
        roles: list[str] = []
        reasons: list[str] = []
        first_time = time_value(row.get("首次涨停"))

        if row.get("板型") == "一字板" or first_time <= time_value("09:45:00"):
            roles.append("先锋龙")
            reasons.append(f"首次涨停{row.get('首次涨停', '')}，封单排名{seal_rank.get(code, '')}")

        if number(row.get("连板天数")) >= 2 or number(row.get("几板")) >= 2:
            roles.append("趋势龙")
            reasons.append(f"{row.get('几天', '')}天{row.get('几板', '')}板，连板{row.get('连板天数', '')}")

        if fund_rank.get(code, 999) <= 20 or super_rank.get(code, 999) <= 20 or fund(row) >= 30000:
            roles.append("资金龙")
            reasons.append(f"主力净额{fund(row):.0f}万，超大单{fund(row, '超大单净额万元'):.0f}万")

        turnover_amount = number(turn.get("成交额亿"))
        if (turnover_amount >= 30 and fund(row) > 0) or limit_amount(row) >= 50000 or (
            number(turn.get("流通市值亿")) >= 200 and fund(row) >= 10000
        ):
            roles.append("中军龙")
            if turnover_amount:
                reasons.append(f"成交额{turnover_amount:g}亿，流通市值{turn.get('流通市值亿', '')}亿")
            else:
                reasons.append(f"涨停成交额{limit_amount(row):.0f}万")

        if not roles:
            continue

        role_count = len(set(roles))
        records.append(
            {
                "代码": code,
                "名称": name_of(row),
                "角色": list(dict.fromkeys(roles)),
                "角色数量": role_count,
                "标签": role_label(role_count),
                "涨停原因": row.get("涨停原因", ""),
                "原因揭秘": row.get("原因揭秘", ""),
                "板块归属": clean_boards(code, stock_boards),
                "首次涨停": row.get("首次涨停", ""),
                "板型": row.get("板型", ""),
                "连板天数": row.get("连板天数", ""),
                "几天": row.get("几天", ""),
                "几板": row.get("几板", ""),
                "封单亿": round(seal_money(row) / 100000000, 2),
                "主力净额万": round(fund(row), 2),
                "超大单万": round(fund(row, "超大单净额万元"), 2),
                "涨停成交额万": round(limit_amount(row), 2),
                "成交额亿": turnover_amount or "",
                "热榜排名": hot_row.get("排名", ""),
                "排序分": role_count * 1000000
                + max(0, 100000 - first_time)
                + max(fund(row), 0)
                + limit_amount(row) / 10
                + turnover_amount * 100,
                "入选理由": "；".join(reasons),
            }
        )

    records.sort(key=lambda item: item["排序分"], reverse=True)
    return {
        "数据格式": "73wiki-dragon-role-ranking-v1",
        "交易日期": date,
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "口径": {
            "先锋龙": "一字板或早盘快速封板，代表最先点火，不用封单大小替代时间。",
            "趋势龙": "连板或几天几板结构成立。",
            "资金龙": "主力净额、超大单净额排名靠前。",
            "中军龙": "大成交额、大流通市值或涨停成交额足够大，且有资金承接。",
        },
        "排序": records,
        "数据缺口": [
            "中军龙使用成交额Top100和涨停成交额粗判，仍需次日竞价和盘口承接验证。",
            "板块归属来自tdx-stock-boards，宽泛概念只做辅助，不作为唯一买入依据。",
        ],
    }


def render_md(payload: dict[str, Any]) -> str:
    date = payload["交易日期"]
    records = payload["排序"]
    groups = {
        "四龙合体": [row for row in records if row["角色数量"] >= 4],
        "三龙共振": [row for row in records if row["角色数量"] == 3],
        "双龙共振": [row for row in records if row["角色数量"] == 2],
    }

    def rows(items: list[dict[str, Any]], limit: int = 40) -> list[list[Any]]:
        return [
            [
                index,
                row["代码"],
                row["名称"],
                "、".join(row["角色"]),
                row["涨停原因"],
                row["首次涨停"],
                f"{row['几天']}天{row['几板']}板",
                row["主力净额万"],
                row["超大单万"],
                row["成交额亿"],
                row["热榜排名"],
                "、".join(row["板块归属"][:4]),
            ]
            for index, row in enumerate(items[:limit], 1)
        ]

    lines = [
        f"# {date} 板块四龙排序",
        "",
        "生成方：Codex Pro",
        f"生成时间：{payload['生成时间']}",
        "",
        "## 口径",
        "",
        "- 四龙固定为：先锋龙、趋势龙、资金龙、中军龙。",
        "- 本表是个股角色共振排序；不替代板块四龙候选表。",
        "- 中军龙不是第五类，是原“中军”的正式命名：大容量 + 大资金认可 + 次日能承接分歧。",
        "",
    ]
    for name, items in groups.items():
        lines.extend(
            [
                f"## {name}",
                "",
                *md_table(
                    ["排名", "代码", "名称", "角色", "涨停原因", "首次涨停", "结构", "主力净额万", "超大单万", "成交额亿", "热榜", "板块归属"],
                    rows(items),
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## 全量排序Top50",
            "",
            *md_table(
                ["排名", "代码", "名称", "角色", "涨停原因", "首次涨停", "结构", "主力净额万", "超大单万", "成交额亿", "热榜", "板块归属"],
                rows(records, 50),
            ),
            "",
            "## 数据缺口",
            "",
        ]
    )
    for gap in payload["数据缺口"]:
        lines.append(f"- {gap}")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    text = render_md(payload)
    if args.write:
        WAR.mkdir(parents=True, exist_ok=True)
        out_md = WAR / f"{args.date}-板块四龙排序.md"
        out_json = WAR / f"{args.date}-板块四龙排序.json"
        out_md.write_text(text, encoding="utf-8")
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raw_dir = RAW_ANALYSIS / args.date
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / out_md.name).write_text(text, encoding="utf-8")
        (raw_dir / out_json.name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "date": args.date,
                "records": len(payload["排序"]),
                "wiki_outputs": [
                    str((WAR / f"{args.date}-板块四龙排序.md").relative_to(ROOT)),
                    str((WAR / f"{args.date}-板块四龙排序.json").relative_to(ROOT)),
                ],
                "raw_outputs": [
                    str((RAW_ANALYSIS / args.date / f"{args.date}-板块四龙排序.md").relative_to(ROOT)),
                    str((RAW_ANALYSIS / args.date / f"{args.date}-板块四龙排序.json").relative_to(ROOT)),
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
