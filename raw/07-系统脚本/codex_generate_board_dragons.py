#!/usr/bin/env python3
"""Generate board four-dragon candidates from fact-layer RAW."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw/04-市场数据"
RAW_ANALYSIS = ROOT / "raw/11-Codex分析产物"
WIKI_WARROOM = ROOT / "wiki/07-作战室"


ALIASES = {
    "减速器": ["减速器"],
    "外骨骼机器人": ["外骨骼"],
    "PEEK材料": ["PEEK"],
    "汽车芯片": ["汽车芯片"],
    "先进封装": ["先进封装"],
    "MCU芯片": ["MCU"],
    "EDA概念": ["EDA"],
    "光通信": ["光通信", "CPO", "通信"],
    "光刻机": ["光刻", "光刻机", "半导体"],
    "CXO概念": ["CXO", "医药", "创新药"],
    "基因概念": ["基因", "医药", "创新药"],
    "培育钻石": ["培育钻石", "钻石"],
    "贵金属": ["黄金", "贵金属"],
    "工业气体": ["工业气体", "特气", "电子气体", "氦气", "六氟化钨"],
    "氟概念": ["氟", "六氟化钨", "氟化工"],
    "MLCC概念": ["MLCC", "电容"],
}

THEME_BOARDS = [
    {"排名": "主题", "代码": "", "名称": "人形机器人", "涨跌幅": ""},
    {"排名": "主题", "代码": "", "名称": "芯片半导体", "涨跌幅": ""},
    {"排名": "主题", "代码": "", "名称": "创新药", "涨跌幅": ""},
    {"排名": "主题", "代码": "", "名称": "黄金贵金属", "涨跌幅": ""},
]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace("%", "").replace("+", "").strip())
    except Exception:
        return 0.0


def number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0


def time_score(value: Any) -> int:
    text = str(value or "15:00:00")
    match = re.match(r"(\d{2}):(\d{2}):(\d{2})", text)
    if not match:
        return 999999
    h, m, s = map(int, match.groups())
    return h * 3600 + m * 60 + s


def stock_text(row: dict[str, Any]) -> str:
    return ".".join(
        str(row.get(key, ""))
        for key in ["名称", "涨停原因", "原因揭秘", "短线主题", "交易题材", "概念标签"]
    )


def board_keywords(name: str) -> list[str]:
    theme_aliases = {
        "人形机器人": ["人形机器人", "机器人概念", "机器人"],
        "芯片半导体": ["芯片", "半导体", "CPO", "存储芯片", "先进封装", "光刻", "MCU", "EDA"],
        "创新药": ["创新药", "CXO", "医药", "基因"],
        "黄金贵金属": ["黄金", "贵金属"],
    }
    base = name.replace("概念", "").strip()
    words = [name, base]
    words.extend(theme_aliases.get(name, ALIASES.get(name, [])))
    seen = []
    for word in words:
        if word and word not in seen:
            seen.append(word)
    return seen


def match_board(row: dict[str, Any], board_name: str) -> bool:
    text = stock_text(row)
    return any(word and word in text for word in board_keywords(board_name))


def display_stock(row: dict[str, Any]) -> str:
    return f"{row.get('名称','')}({row.get('代码') or row.get('股票代码','')})"


def member_codes_for_board(board: dict[str, Any], board_members: dict[str, Any]) -> set[str]:
    if not board_members:
        return set()
    code = str(board.get("代码") or board.get("板块代码") or "").strip()
    name = str(board.get("名称") or board.get("板块名称") or "").strip()
    raw = board_members.get("板块成分股") if isinstance(board_members, dict) else {}
    if not isinstance(raw, dict):
        return set()
    item = raw.get(code) if code else None
    if not item and name:
        for candidate in raw.values():
            if isinstance(candidate, dict) and candidate.get("板块名称") == name:
                item = candidate
                break
    if not isinstance(item, dict):
        return set()
    return {str(x).zfill(6) for x in item.get("成分股", []) if str(x).strip()}


def stock_boards_for_code(code: str, stock_boards: dict[str, Any]) -> list[str]:
    raw = stock_boards.get("股票板块") if isinstance(stock_boards, dict) else {}
    item = raw.get(code) if isinstance(raw, dict) else None
    if isinstance(item, dict) and isinstance(item.get("板块"), list):
        return [str(x) for x in item["板块"]]
    return []


def match_board_by_stock_map(row: dict[str, Any], board_name: str, stock_boards: dict[str, Any]) -> bool:
    code = str(row.get("代码") or row.get("股票代码") or "").zfill(6)
    boards = stock_boards_for_code(code, stock_boards)
    if not boards:
        return False
    keywords = board_keywords(board_name)
    return any(board_name == board or any(word and word in board for word in keywords) for board in boards)


def pick_four_dragons(
    board: dict[str, Any],
    records: list[dict[str, Any]],
    turnover: dict[str, dict[str, Any]],
    board_members: dict[str, Any],
    stock_boards: dict[str, Any],
) -> dict[str, Any]:
    board_name = str(board.get("名称") or board.get("板块名称") or "")
    board_code = str(board.get("代码") or board.get("板块代码") or "").strip()
    member_codes = member_codes_for_board(board, board_members)
    if member_codes:
        matched = [row for row in records if str(row.get("代码") or row.get("股票代码") or "").zfill(6) in member_codes]
        match_method = "板块成分股映射"
    elif board_code:
        mapped = [row for row in records if match_board_by_stock_map(row, board_name, stock_boards)]
        if mapped:
            matched = mapped
            match_method = "个股板块归属"
        else:
            matched = [row for row in records if match_board(row, board_name)]
            match_method = "关键词兜底"
    else:
        matched = [row for row in records if match_board(row, board_name)]
        match_method = "主题关键词聚合"
    if not matched:
        return {
            "板块": board_name,
            "匹配方法": "无匹配",
            "匹配涨停票数量": 0,
            "先锋龙": None,
            "资金龙": None,
            "中军": None,
            "趋势龙": None,
            "候选池": [],
            "缺口": "未在板块成分股、个股板块归属或涨停原因中匹配到涨停票；可能该板块上涨由非涨停成分股推动。",
        }

    def turnover_value(row: dict[str, Any]) -> float:
        code = str(row.get("代码") or row.get("股票代码") or "")
        if code in turnover:
            return number(turnover[code].get("成交额亿")) * 10000
        return number(row.get("涨停成交额_万"))

    def fund_value(row: dict[str, Any], key: str = "主力净额万元") -> float:
        funds = row.get("资金流向")
        if not isinstance(funds, dict):
            return 0.0
        return number(funds.get(key))

    def seal_value(row: dict[str, Any]) -> float:
        return number(row.get("封单金额")) or number(row.get("最大封单额_万")) * 10000

    pioneer = sorted(
        matched,
        key=lambda row: (
            time_score(row.get("首次涨停")),
            0 if row.get("板型") == "一字板" else 1,
            -seal_value(row),
        ),
    )[0]
    capital = sorted(
        matched,
        key=lambda row: (
            -fund_value(row),
            -fund_value(row, "超大单净额万元"),
            -turnover_value(row),
            -number(row.get("封单金额")),
        ),
    )[0]
    middle = sorted(
        matched,
        key=lambda row: (
            -turnover_value(row),
            -max(fund_value(row), 0),
            -number(turnover.get(str(row.get("代码") or row.get("股票代码") or ""), {}).get("流通市值亿")),
            -seal_value(row),
        ),
    )[0]
    trend = sorted(
        matched,
        key=lambda row: (
            -number(row.get("几板")),
            -number(row.get("几天")),
            -number(row.get("连板天数")),
            time_score(row.get("首次涨停")),
        ),
    )[0]

    def reason(row: dict[str, Any], kind: str) -> str:
        code = str(row.get("代码") or row.get("股票代码") or "")
        extra = turnover.get(code, {})
        parts = []
        if kind == "先锋龙":
            parts.append(f"首次涨停{row.get('首次涨停', '')}")
            parts.append(f"板型{row.get('板型', '')}")
            parts.append(f"封单{round(seal_value(row) / 100000000, 2)}亿")
        elif kind == "资金龙":
            if row.get("资金流向"):
                parts.append(f"主力净额{row['资金流向'].get('主力净额万元')}万")
                parts.append(f"超大单{row['资金流向'].get('超大单净额万元')}万")
            if extra.get("成交额亿") is not None:
                parts.append(f"成交额{extra.get('成交额亿')}亿")
            elif row.get("涨停成交额_万") is not None:
                parts.append(f"涨停成交额{row.get('涨停成交额_万')}万")
        elif kind == "中军":
            if extra.get("流通市值亿") is not None:
                parts.append(f"流通市值{extra.get('流通市值亿')}亿")
            if extra.get("成交额亿") is not None:
                parts.append(f"成交额{extra.get('成交额亿')}亿")
        elif kind == "趋势龙":
            parts.append(f"{row.get('几天', '')}天{row.get('几板', '')}板")
            parts.append(f"连板{row.get('连板天数', 1)}")
        if row.get("涨停原因"):
            parts.append(f"原因：{row.get('涨停原因')}")
        return "；".join(str(part) for part in parts if part)

    return {
        "板块": board_name,
        "匹配方法": match_method,
        "匹配涨停票数量": len(matched),
        "先锋龙": {"个股": display_stock(pioneer), "理由": reason(pioneer, "先锋龙")},
        "资金龙": {"个股": display_stock(capital), "理由": reason(capital, "资金龙")},
        "中军": {"个股": display_stock(middle), "理由": reason(middle, "中军")},
        "趋势龙": {"个股": display_stock(trend), "理由": reason(trend, "趋势龙")},
        "候选池": [
            {
                "个股": display_stock(row),
                "涨停原因": row.get("涨停原因", ""),
                "首次涨停": row.get("首次涨停", ""),
                "连板天数": row.get("连板天数", 1),
                "板型": row.get("板型", ""),
                "主力净额万元": fund_value(row),
                "超大单净额万元": fund_value(row, "超大单净额万元"),
                "涨停成交额万元": number(row.get("涨停成交额_万")),
            }
            for row in sorted(matched, key=lambda item: (-number(item.get("连板天数")), time_score(item.get("首次涨停"))))[:12]
        ],
        "缺口": "",
    }


def render_md(trade_date: str, board_rows: list[dict[str, Any]], dragons: list[dict[str, Any]], data_gaps: list[str]) -> str:
    lines = [
        f"# {trade_date} 板块四龙候选",
        "",
        "生成方：Codex Pro",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 口径",
        "",
        "- 先锋龙：板块内最先点火、最早封住的票；一字板优先，同时间看封单，不用连板高度替代。",
        "- 资金龙：板块内主力净额优先、超大单辅助、成交额验证，代表资金承接最集中的票。",
        "- 中军龙：板块内容量最大、最能代表大资金承载能力的票。",
        "- 趋势龙：板块内走势持续性最好、几天几板或趋势结构最强的票。",
        "- 四龙允许重合，不强行凑不同股票。",
        "",
        "## 板块涨幅前10",
        "",
        "| 排名 | 板块代码 | 板块 | 涨跌幅 |",
        "|---:|---|---|---:|",
    ]
    for row in board_rows[:10]:
        lines.append(f"| {row.get('排名','')} | {row.get('代码','')} | {row.get('名称','')} | {row.get('涨跌幅','')} |")
    lines.extend(["", "## 四龙候选", ""])
    for item in dragons:
        lines.extend(
            [
                f"### {item['板块']}",
                "",
                f"- 匹配涨停票数量：{item.get('匹配涨停票数量', 0)}",
            ]
        )
        for kind in ["先锋龙", "资金龙", "中军", "趋势龙"]:
            value = item.get(kind)
            if value:
                label = "中军龙" if kind == "中军" else kind
                lines.append(f"- {label}：{value['个股']}，{value['理由']}")
            else:
                label = "中军龙" if kind == "中军" else kind
                lines.append(f"- {label}：待补")
        if item.get("匹配方法"):
            lines.append(f"- 匹配方法：{item['匹配方法']}")
        if item.get("候选池"):
            pool = "、".join(row["个股"] for row in item["候选池"][:8])
            lines.append(f"- 候选池：{pool}")
        if item.get("缺口"):
            lines.append(f"- 缺口：{item['缺口']}")
        lines.append("")
    lines.extend(["## 数据缺口", ""])
    for gap in data_gaps:
        lines.append(f"- {gap}")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    trade_date = args.date

    board = read_json(RAW / "板块强度" / trade_date / "tdx-board-strength.json", {})
    daily = read_json(RAW / "每日涨停全景" / trade_date / "tdx-daily-limit.json", {})
    turnover_payload = read_json(RAW / "通达信成交额排名" / trade_date / "tdx-成交额Top100.json", {})
    records = daily.get("记录") or []
    turnover_rows = turnover_payload.get("数据") or []
    turnover = {str(row.get("股票代码")): row for row in turnover_rows if row.get("股票代码")}
    board_rows = board.get("涨幅Top10") or []

    if not records:
        raise SystemExit(f"Missing daily limit records for {trade_date}")
    if not board_rows:
        topics = Counter()
        for row in records:
            for part in re.split(r"[.、,，/\\s]+", str(row.get("涨停原因", ""))):
                if part and len(part) >= 2:
                    topics[part] += 1
        board_rows = [{"排名": i, "代码": "", "名称": name, "涨跌幅": ""} for i, (name, _) in enumerate(topics.most_common(10), 1)]

    board_members = read_json(RAW / "板块成分股" / trade_date / "tdx-board-members.json", {})
    stock_boards = read_json(RAW / "板块成分股" / trade_date / "tdx-stock-boards.json", {})
    selected_boards = list(board_rows[:10]) + THEME_BOARDS
    dragons = [pick_four_dragons(row, records, turnover, board_members, stock_boards) for row in selected_boards]
    data_gaps = []
    if board.get("缺口"):
        data_gaps.extend(board["缺口"] if isinstance(board["缺口"], list) else [board["缺口"]])
    if not turnover_rows:
        data_gaps.append("缺少成交额Top100，资金龙和中军龙只能用涨停成交额粗判。")
    if not board_members:
        data_gaps.append("缺少板块成分股映射，四龙只能使用个股板块归属或关键词兜底。")
    if not stock_boards:
        data_gaps.append("缺少个股板块归属，主题聚合只能使用关键词兜底。")
    data_gaps.append("四龙为Codex候选，不是买入建议；次日必须用竞价、封单、板块延续和D+表现验证。")

    payload = {
        "数据格式": "73wiki-board-four-dragons-v1",
        "交易日期": trade_date,
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "板块涨幅前10": board_rows[:10],
        "四龙候选": dragons,
        "数据缺口": data_gaps,
    }
    if args.write:
        WIKI_WARROOM.mkdir(parents=True, exist_ok=True)
        out_json = WIKI_WARROOM / f"{trade_date}-板块四龙候选.json"
        out_md = WIKI_WARROOM / f"{trade_date}-板块四龙候选.md"
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out_md.write_text(render_md(trade_date, board_rows, dragons, data_gaps), encoding="utf-8")
        raw_dir = RAW_ANALYSIS / trade_date
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / out_json.name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (raw_dir / out_md.name).write_text(render_md(trade_date, board_rows, dragons, data_gaps), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
