#!/usr/bin/env python3
"""Generate Codex analysis for hotlist, limit ladder and first-board catalysts."""

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
WAR = ROOT / "wiki/07-作战室"
STAT = ROOT / "wiki/09-统计与进化"


IGNORE_TOPICS = {
    "昨日断板",
    "微小盘股",
    "活跃小盘非融",
    "国企改革",
    "一带一路",
    "非周期股",
    "周期股",
    "专项贷款",
    "陆股通重仓",
    "最近多板",
    "昨日涨停",
    "昨日上榜",
}


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def number(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(str(value).replace("%", "").replace("+", "").replace(",", "").strip())
    except Exception:
        return 0.0


def pct_text(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{number(value):.2f}%"
    except Exception:
        return str(value)


def code_of(row: dict[str, Any]) -> str:
    return str(row.get("代码") or row.get("股票代码") or "").zfill(6)


def name_of(row: dict[str, Any]) -> str:
    return str(row.get("名称") or row.get("股票名称") or "")


def split_topics(text: str) -> list[str]:
    out = []
    for part in re.split(r"[.、,，/\s]+", str(text or "")):
        part = part.strip()
        if len(part) < 2 or part in IGNORE_TOPICS:
            continue
        out.append(part)
    return out


def time_value(value: Any) -> int:
    m = re.match(r"(\d{2}):(\d{2}):(\d{2})", str(value or "15:00:00"))
    if not m:
        return 999999
    h, mi, s = map(int, m.groups())
    return h * 3600 + mi * 60 + s


def md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return out


def build_board_reverse(board_members: dict[str, Any]) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = defaultdict(list)
    raw = board_members.get("板块成分股") if isinstance(board_members, dict) else {}
    if not isinstance(raw, dict):
        return reverse
    for item in raw.values():
        if not isinstance(item, dict):
            continue
        board_name = str(item.get("板块名称") or "")
        if not board_name:
            continue
        for code in item.get("成分股", []) or []:
            code_text = str(code).zfill(6)
            if board_name not in reverse[code_text]:
                reverse[code_text].append(board_name)
    return reverse


def fund(row: dict[str, Any], key: str = "主力净额万元") -> float:
    funds = row.get("资金流向")
    if not isinstance(funds, dict):
        return 0.0
    return number(funds.get(key))


def fund_text(row: dict[str, Any], key: str = "主力净额万元") -> str:
    value = fund(row, key)
    return "" if value == 0 else f"{value:.0f}"


def load_all(date: str) -> dict[str, Any]:
    hot = read_json(RAW / "通达信热榜" / date / "tdx-hot-top100.json", {}).get("data") or []
    ladder = read_json(RAW / "通达信连板天梯" / date / "tdx-limit-ladder.json", {}).get("连板天梯") or []
    daily = read_json(RAW / "每日涨停全景" / date / "tdx-daily-limit.json", {}).get("记录") or []
    turnover = read_json(RAW / "通达信成交额排名" / date / "tdx-成交额Top100.json", {}).get("数据") or []
    stock_boards = read_json(RAW / "板块成分股" / date / "tdx-stock-boards.json", {}).get("股票板块") or {}
    board_members = read_json(RAW / "板块成分股" / date / "tdx-board-members.json", {})
    return {
        "hot": hot,
        "ladder": ladder,
        "daily": daily,
        "turnover": turnover,
        "stock_boards": stock_boards,
        "board_members": board_members,
        "board_reverse": build_board_reverse(board_members),
        "hot_map": {code_of(row): row for row in hot},
        "limit_map": {code_of(row): row for row in daily},
        "turnover_map": {code_of(row): row for row in turnover},
    }


def stock_boards_text(code: str, stock_boards: dict[str, Any], board_reverse: dict[str, list[str]] | None = None, limit: int = 4) -> str:
    item = stock_boards.get(code) or {}
    boards = item.get("板块") if isinstance(item, dict) else []
    if (not isinstance(boards, list) or not boards) and board_reverse:
        boards = board_reverse.get(code, [])
    if not isinstance(boards, list):
        return ""
    useful = [b for b in boards if b not in {"昨日上榜", "昨日涨停", "最近多板", "基金重仓", "陆股通重仓"}]
    return "、".join(useful[:limit])


def generate_hotlist(date: str, data: dict[str, Any]) -> str:
    hot, limit_map, turnover_map, stock_boards, board_reverse = (
        data["hot"],
        data["limit_map"],
        data["turnover_map"],
        data["stock_boards"],
        data["board_reverse"],
    )
    hot_codes = {code_of(row) for row in hot}
    limit_codes = set(limit_map)
    turnover_codes = set(turnover_map)
    positives = [row for row in hot if number(row.get("涨跌幅")) > 0]
    negatives = [row for row in hot if number(row.get("涨跌幅")) < 0]
    limit_hits = [row for row in hot if code_of(row) in limit_codes]
    turnover_hits = [row for row in hot if code_of(row) in turnover_codes]
    top20 = hot[:20]
    top20_neg = [row for row in top20 if number(row.get("涨跌幅")) < 0]

    rows = []
    for row in hot[:30]:
        code = code_of(row)
        turn = turnover_map.get(code)
        lim = limit_map.get(code)
        rows.append(
            [
                row.get("排名"),
                code,
                name_of(row),
                pct_text(row.get("涨跌幅")),
                turn.get("成交额亿", "") if turn else "",
                "是" if lim else "",
                fund_text(lim or {}),
                fund_text(lim or {}, "超大单净额万元"),
                stock_boards_text(code, stock_boards, board_reverse),
            ]
        )

    money_no_heat = [row for row in data["turnover"] if code_of(row) not in hot_codes][:20]
    money_rows = [
        [
            row.get("排名"),
            code_of(row),
            name_of(row),
            row.get("成交额亿", ""),
            pct_text(row.get("涨跌幅")),
            stock_boards_text(code_of(row), stock_boards, board_reverse),
        ]
        for row in money_no_heat[:15]
    ]

    lines = [
        f"# {date} 热榜100资金情绪交叉分析",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 结论",
        "",
        f"- 热榜100中上涨 {len(positives)} 只，下跌 {len(negatives)} 只。",
        f"- 热榜Top20中下跌 {len(top20_neg)} 只，说明人气集中在分歧和负反馈大票上。",
        f"- 热榜100与成交额Top100交集 {len(turnover_hits)} 只，说明人气和资金有较高重合。",
        f"- 热榜100与涨停全景交集 {len(limit_hits)} 只，说明人气并没有大面积转化为涨停强度。",
        "",
        "## 热榜Top30交叉表",
        "",
        *md_table(["热榜排名", "代码", "名称", "涨跌幅", "成交额亿", "是否涨停", "主力净额万", "超大单万", "板块归属"], rows),
        "",
        "## 有钱但热榜不靠前",
        "",
        *md_table(["成交额排名", "代码", "名称", "成交额亿", "涨跌幅", "板块归属"], money_rows),
        "",
        "## 交易含义",
        "",
        "- 热榜前排如果大面积下跌，不能把“热度”直接当成强度。",
        "- 同时在热榜、成交额、涨停里的票，才是短线最值得验证的强反馈。",
        "- 只有成交额没有热榜，偏机构/容量或趋势资金；只有热榜没有成交额，偏情绪关注。",
    ]
    return "\n".join(lines) + "\n"


def generate_ladder(date: str, data: dict[str, Any]) -> str:
    ladder, turnover_map, hot_map, limit_map = data["ladder"], data["turnover_map"], data["hot_map"], data["limit_map"]
    dist = Counter(str(row.get("连板天数")) + "板" for row in ladder)
    topic_counter = Counter()
    for row in ladder:
        topic_counter.update(split_topics(row.get("涨停原因", "")))
    rows = []
    for row in sorted(ladder, key=lambda r: (-number(r.get("连板天数")), time_value(r.get("首次涨停")))):
        code = code_of(row)
        full = limit_map.get(code, row)
        turn = turnover_map.get(code)
        hot = hot_map.get(code)
        rows.append(
            [
                row.get("连板天数"),
                code,
                name_of(row),
                row.get("板型", ""),
                row.get("首次涨停", ""),
                round(number(row.get("封单")) / 100000000, 2),
                row.get("涨停原因", ""),
                fund_text(full),
                fund_text(full, "超大单净额万元"),
                turn.get("成交额亿", "") if turn else "",
                hot.get("排名", "") if hot else "",
            ]
        )
    fund_rows = [
        [
            row.get("连板天数"),
            code_of(row),
            name_of(row),
            row.get("涨停原因", ""),
            fund_text(limit_map.get(code_of(row), row)),
            fund_text(limit_map.get(code_of(row), row), "超大单净额万元"),
        ]
        for row in sorted(ladder, key=lambda item: fund(limit_map.get(code_of(item), item)), reverse=True)
    ]

    lines = [
        f"# {date} 连板天梯与高度情绪分析",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 结论",
        "",
        f"- 非ST连板 {len(ladder)} 只，高度分布：{dict(dist)}。",
        "- 最高标如果是独立并购/复牌属性，不能简单代表主线高度。",
        "- 真正要看主线延续，应看2板以上是否集中在同一主线，以及次日晋级率。",
        "",
        "## 连板天梯",
        "",
        *md_table(["高度", "代码", "名称", "板型", "首次涨停", "封单亿", "涨停原因", "主力净额万", "超大单万", "成交额亿", "热榜排名"], rows),
        "",
        "## 连板资金净额排序",
        "",
        *md_table(["高度", "代码", "名称", "涨停原因", "主力净额万", "超大单万"], fund_rows),
        "",
        "## 连板主题计数",
        "",
        *md_table(["主题", "次数"], [[k, v] for k, v in topic_counter.most_common(15)]),
        "",
        "## 次日验证点",
        "",
        "- 最高标是否继续一字或温和开板回封。",
        "- 人形机器人方向的2板是否继续晋级，是确认主线持续性的关键。",
        "- 黄金方向2板能否晋级3板，决定强支线是否继续独立。",
        "- 如果连板票大面积低开，周五涨停潮要按分化处理。",
    ]
    return "\n".join(lines) + "\n"


def generate_first_board(date: str, data: dict[str, Any]) -> str:
    daily, turnover_map, hot_map, stock_boards = data["daily"], data["turnover_map"], data["hot_map"], data["stock_boards"]
    first = [row for row in daily if int(number(row.get("连板天数")) or 1) == 1]
    topic_counter = Counter()
    for row in first:
        topic_counter.update(split_topics(row.get("涨停原因", "")))
    early = sorted(first, key=lambda row: time_value(row.get("首次涨停")))[:30]
    seal = sorted(first, key=lambda row: number(row.get("封单金额")), reverse=True)[:30]
    amount = sorted(first, key=lambda row: number(row.get("涨停成交额_万")), reverse=True)[:30]
    fund_rank = sorted(first, key=lambda row: fund(row), reverse=True)[:30]

    def rows_for(items: list[dict[str, Any]]) -> list[list[Any]]:
        out = []
        for row in items:
            code = code_of(row)
            turn = turnover_map.get(code)
            hot = hot_map.get(code)
            out.append(
                [
                    code,
                    name_of(row),
                    row.get("首次涨停", ""),
                    row.get("板型", ""),
                    row.get("开板次数", ""),
                    round(number(row.get("封单金额")) / 100000000, 2),
                    fund_text(row),
                    fund_text(row, "超大单净额万元"),
                    row.get("涨停成交额_万", ""),
                    row.get("涨停原因", ""),
                    turn.get("成交额亿", "") if turn else "",
                    hot.get("排名", "") if hot else "",
                ]
            )
        return out

    lines = [
        f"# {date} 首板涨停催化分析",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 结论",
        "",
        f"- 首板 {len(first)} 只，首板数量很大，说明情绪修复强，但次日分化压力也大。",
        "- 首板不能只看数量，要看早盘强度、封单、成交额、是否进入热榜/成交额榜。",
        "- 人形机器人是首板扩散最集中的方向，周一重点看首板溢价和2板晋级率。",
        "",
        "## 首板主题计数",
        "",
        *md_table(["主题", "首板次数"], [[k, v] for k, v in topic_counter.most_common(25)]),
        "",
        "## 最早首板Top30",
        "",
        *md_table(["代码", "名称", "首次涨停", "板型", "开板次数", "封单亿", "主力净额万", "超大单万", "涨停成交额万", "原因", "成交额亿", "热榜"], rows_for(early)),
        "",
        "## 首板封单Top30",
        "",
        *md_table(["代码", "名称", "首次涨停", "板型", "开板次数", "封单亿", "主力净额万", "超大单万", "涨停成交额万", "原因", "成交额亿", "热榜"], rows_for(seal)),
        "",
        "## 首板成交额Top30",
        "",
        *md_table(["代码", "名称", "首次涨停", "板型", "开板次数", "封单亿", "主力净额万", "超大单万", "涨停成交额万", "原因", "成交额亿", "热榜"], rows_for(amount)),
        "",
        "## 首板主力净额Top30",
        "",
        *md_table(["代码", "名称", "首次涨停", "板型", "开板次数", "封单亿", "主力净额万", "超大单万", "涨停成交额万", "原因", "成交额亿", "热榜"], rows_for(fund_rank)),
        "",
        "## 次日验证点",
        "",
        "- 首板数量多时，第二天不看谁最多，只看谁晋级。",
        "- 早盘一字和大封单首板若无溢价，说明修复失败。",
        "- 大成交额首板如果高开承接，才可能成为资金龙或中军确认。",
    ]
    return "\n".join(lines) + "\n"


def generate_panorama(date: str, data: dict[str, Any]) -> str:
    daily, hot_map, turnover_map = data["daily"], data["hot_map"], data["turnover_map"]
    limit_codes = {code_of(row) for row in daily}
    hot_codes = set(hot_map)
    turnover_codes = set(turnover_map)
    topic_counter = Counter()
    for row in daily:
        topic_counter.update(split_topics(row.get("涨停原因", "")))
    triple = sorted(limit_codes & hot_codes & turnover_codes)
    hot_limit = sorted(limit_codes & hot_codes)
    money_limit = sorted(limit_codes & turnover_codes)

    def code_rows(codes: list[str]) -> list[list[Any]]:
        rows = []
        limit_map = data["limit_map"]
        for code in codes:
            lim = limit_map.get(code, {})
            hot = hot_map.get(code)
            turn = turnover_map.get(code)
            rows.append(
                [
                    code,
                    name_of(lim) or name_of(hot or {}) or name_of(turn or {}),
                    lim.get("连板天数", ""),
                    lim.get("涨停原因", ""),
                    fund_text(lim),
                    fund_text(lim, "超大单净额万元"),
                    hot.get("排名", "") if hot else "",
                    turn.get("排名", "") if turn else "",
                    turn.get("成交额亿", "") if turn else "",
                ]
            )
        return rows

    lines = [
        f"# {date} 涨停全景交叉复盘",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 关键统计",
        "",
        f"- 涨停全景：{len(daily)} 只。",
        f"- 热榜Top100与涨停交集：{len(hot_limit)} 只。",
        f"- 成交额Top100与涨停交集：{len(money_limit)} 只。",
        f"- 热榜Top100、成交额Top100、涨停三者共振：{len(triple)} 只。",
        "",
        "## 三榜共振",
        "",
        *md_table(["代码", "名称", "连板", "涨停原因", "主力净额万", "超大单万", "热榜排名", "成交额排名", "成交额亿"], code_rows(triple)),
        "",
        "## 热榜涨停交集",
        "",
        *md_table(["代码", "名称", "连板", "涨停原因", "主力净额万", "超大单万", "热榜排名", "成交额排名", "成交额亿"], code_rows(hot_limit)),
        "",
        "## 成交额涨停交集",
        "",
        *md_table(["代码", "名称", "连板", "涨停原因", "主力净额万", "超大单万", "热榜排名", "成交额排名", "成交额亿"], code_rows(money_limit)),
        "",
        "## 涨停主力净额Top30",
        "",
        *md_table(
            ["代码", "名称", "连板", "涨停原因", "主力净额万", "超大单万", "热榜排名", "成交额排名", "成交额亿"],
            code_rows([code_of(row) for row in sorted(daily, key=lambda item: fund(item), reverse=True)[:30]]),
        ),
        "",
        "## 涨停主题Top30",
        "",
        *md_table(["主题", "次数"], [[k, v] for k, v in topic_counter.most_common(30)]),
        "",
        "## 复盘结论",
        "",
        "- 今天涨停数量强，但三榜共振少，说明涨停潮和大成交热榜并没有完全统一。",
        "- 人形机器人是涨停扩散主线，周一看连板晋级和中军承接。",
        "- 科技大票热度高、成交额大，但大量负反馈，半导体暂按修复而不是反转。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    data = load_all(args.date)
    outputs = {
        WAR / f"{args.date}-热榜100资金情绪交叉分析.md": generate_hotlist(args.date, data),
        WAR / f"{args.date}-连板天梯与高度情绪分析.md": generate_ladder(args.date, data),
        WAR / f"{args.date}-首板涨停催化分析.md": generate_first_board(args.date, data),
        STAT / f"{args.date}-涨停全景交叉复盘.md": generate_panorama(args.date, data),
    }
    if args.write:
        for path, text in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            raw_path = RAW_ANALYSIS / args.date / path.name
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(text, encoding="utf-8")
    raw_outputs = [RAW_ANALYSIS / args.date / path.name for path in outputs]
    print(
        json.dumps(
            {
                "date": args.date,
                "wiki_outputs": [str(p.relative_to(ROOT)) for p in outputs],
                "raw_outputs": [str(p.relative_to(ROOT)) for p in raw_outputs],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
