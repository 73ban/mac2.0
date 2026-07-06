#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 tdxrs 补历史复盘市场环境里的量价底座。

边界：
- 只拉指数/个股 K 线、成交额、指数上涨下跌家数、D+窗口。
- 不生成主线判断、交易建议、错误定性。
- 涨停全景、连板天梯、热榜、龙虎榜、政策新闻仍由其他事实源补充。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = ROOT / "raw" / "04-市场数据" / "历史复盘环境"
CODE_RE = re.compile(
    r"(?<!\d)(?:"
    r"00[0-3]\d{3}|"
    r"30[0-2]\d{3}|"
    r"60[0-5]\d{3}|"
    r"68[89]\d{3}|"
    r"43\d{4}|"
    r"83\d{4}|"
    r"87\d{4}|"
    r"92\d{4}"
    r")(?!\d)"
)

INDEXES = [
    {"证券代码": "000001", "证券名称": "上证指数", "市场": "沪市"},
    {"证券代码": "399001", "证券名称": "深证成指", "市场": "深市"},
    {"证券代码": "399006", "证券名称": "创业板指", "市场": "深市"},
    {"证券代码": "000688", "证券名称": "科创50", "市场": "沪市"},
    {"证券代码": "899050", "证券名称": "北证50", "市场": "北交所"},
]


def load_tdxrs():
    try:
        from tdxrs import TdxHqClient  # type: ignore
        from tdxrs.constants import KLINE_DAILY, MARKET_BJ, MARKET_SH, MARKET_SZ  # type: ignore
    except Exception as exc:
        raise SystemExit(
            "未安装 tdxrs。请先执行："
            ".system/venv-tdxrs/bin/python -m pip install tdxrs"
        ) from exc
    return TdxHqClient, KLINE_DAILY, MARKET_SH, MARKET_SZ, MARKET_BJ


def infer_market(code: str) -> int:
    _, _, market_sh, market_sz, market_bj = load_tdxrs()
    if code.startswith(("60", "68", "9")):
        return market_sh
    if code.startswith(("8", "4", "92")):
        return market_bj
    return market_sz


def market_from_name(name: str) -> int:
    _, _, market_sh, market_sz, market_bj = load_tdxrs()
    if name == "沪市":
        return market_sh
    if name == "北交所":
        return market_bj
    return market_sz


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def find_source_files(date: str) -> list[Path]:
    roots = [
        ROOT / "raw" / "01-交割单",
        ROOT / "raw" / "02-每日复盘",
        ROOT / "raw" / "10-飞书交易沟通",
        ROOT / "wiki" / "06-持仓与资金管理",
        ROOT / "wiki" / "09-统计与进化",
    ]
    result: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob(f"*{date}*.md"):
            if ".stversions" in path.parts:
                continue
            result.append(path)
    return sorted(set(result))


def collect_codes(date: str, explicit: list[str], limit: int) -> tuple[list[str], list[str]]:
    codes = []
    sources = []
    for code in explicit:
        if CODE_RE.fullmatch(code) and code not in codes:
            codes.append(code)
            sources.append("命令行指定")
    for path in find_source_files(date):
        text = read_text(path)
        found = sorted(set(CODE_RE.findall(text)))
        if found:
            rel = str(path.relative_to(ROOT))
            sources.append(rel)
        for code in found:
            if code not in codes:
                codes.append(code)
        if len(codes) >= limit:
            break
    return codes[:limit], sources


def to_float(value: Any) -> float | None:
    try:
        return round(float(value), 4)
    except Exception:
        return None


def pct(close_value: Any, prev_close: Any) -> float | None:
    try:
        close_f = float(close_value)
        prev_f = float(prev_close)
        if prev_f == 0:
            return None
        return round((close_f / prev_f - 1) * 100, 2)
    except Exception:
        return None


def normalize_bar(row: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, Any]:
    result = {
        "日期": row.get("datetime") or f"{row.get('year')}-{row.get('month')}-{row.get('day')}",
        "开盘价": to_float(row.get("open")),
        "收盘价": to_float(row.get("close")),
        "最高价": to_float(row.get("high")),
        "最低价": to_float(row.get("low")),
        "成交量": to_float(row.get("vol")),
        "成交额": to_float(row.get("amount")),
        "涨跌幅": pct(row.get("close"), prev.get("close") if prev else None),
    }
    if "up_count" in row:
        result["上涨家数"] = row.get("up_count")
    if "down_count" in row:
        result["下跌家数"] = row.get("down_count")
    return result


def pick_windows(rows: list[dict[str, Any]], target_date: str, windows: list[int]) -> dict[str, Any]:
    dates = [str(row.get("datetime")) for row in rows]
    if target_date not in dates:
        return {"找到目标日期": False, "目标日期": target_date, "窗口": []}
    idx = dates.index(target_date)
    selected = []
    for offset in windows:
        pos = idx + offset
        if 0 <= pos < len(rows):
            prev = rows[pos - 1] if pos > 0 else None
            selected.append({"窗口": f"D+{offset}", **normalize_bar(rows[pos], prev)})
    target_close = rows[idx].get("close")
    for item in selected:
        try:
            item["相对目标日涨跌幅"] = round((float(item["收盘价"]) / float(target_close) - 1) * 100, 2)
        except Exception:
            item["相对目标日涨跌幅"] = None
    return {"找到目标日期": True, "目标日期": target_date, "窗口": selected}


def fetch_index(client: Any, date: str, windows: list[int], count: int) -> list[dict[str, Any]]:
    _, kline_daily, _, _, _ = load_tdxrs()
    output = []
    for meta in INDEXES:
        market = market_from_name(meta["市场"])
        try:
            rows = client.get_index_bars(kline_daily, market, meta["证券代码"], 0, count)
            picked = pick_windows(rows, date, windows)
            output.append({**meta, **picked})
        except Exception as exc:
            output.append({**meta, "找到目标日期": False, "错误": str(exc), "窗口": []})
    return output


def fetch_stocks(client: Any, codes: list[str], date: str, windows: list[int], count: int) -> list[dict[str, Any]]:
    _, kline_daily, _, _, _ = load_tdxrs()
    output = []
    for code in codes:
        try:
            rows = client.get_security_bars(kline_daily, infer_market(code), code, 0, count)
            picked = pick_windows(rows, date, windows)
            output.append({"证券代码": code, **picked})
        except Exception as exc:
            output.append({"证券代码": code, "找到目标日期": False, "错误": str(exc), "窗口": []})
    return output


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['数据日期']} 历史市场环境 tdxrs 量价底座",
        "",
        f"- 生成时间：{payload['生成时间']}",
        "- 数据源：tdxrs",
        "- 定位：只补指数/个股量价、指数上涨下跌家数、D+窗口，不替代热榜、涨停原因、龙虎榜、政策新闻。",
        f"- 自动识别股票数：{payload['股票数量']}",
        "",
        "## 指数环境",
        "",
        "| 指数 | D+0收盘 | D+0涨跌幅 | D+0成交额 | 上涨家数 | 下跌家数 | D+1 | D+3 | D+5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in payload["指数"]:
        by_window = {row["窗口"]: row for row in item.get("窗口", [])}
        d0 = by_window.get("D+0", {})
        lines.append(
            "| {name} | {close} | {pct} | {amount} | {up} | {down} | {d1} | {d3} | {d5} |".format(
                name=item.get("证券名称"),
                close=d0.get("收盘价", ""),
                pct="" if d0.get("涨跌幅") is None else f"{d0.get('涨跌幅')}%",
                amount=d0.get("成交额", ""),
                up=d0.get("上涨家数", ""),
                down=d0.get("下跌家数", ""),
                d1=by_window.get("D+1", {}).get("相对目标日涨跌幅", ""),
                d3=by_window.get("D+3", {}).get("相对目标日涨跌幅", ""),
                d5=by_window.get("D+5", {}).get("相对目标日涨跌幅", ""),
            )
        )
    lines += [
        "",
        "## 股票量价窗口",
        "",
        "| 股票代码 | D+0收盘 | D+0涨跌幅 | D+0成交额 | D+1 | D+3 | D+5 | D+10 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in payload["股票"]:
        by_window = {row["窗口"]: row for row in item.get("窗口", [])}
        d0 = by_window.get("D+0", {})
        lines.append(
            "| {code} | {close} | {pct} | {amount} | {d1} | {d3} | {d5} | {d10} |".format(
                code=item.get("证券代码"),
                close=d0.get("收盘价", ""),
                pct="" if d0.get("涨跌幅") is None else f"{d0.get('涨跌幅')}%",
                amount=d0.get("成交额", ""),
                d1=by_window.get("D+1", {}).get("相对目标日涨跌幅", ""),
                d3=by_window.get("D+3", {}).get("相对目标日涨跌幅", ""),
                d5=by_window.get("D+5", {}).get("相对目标日涨跌幅", ""),
                d10=by_window.get("D+10", {}).get("相对目标日涨跌幅", ""),
            )
        )
    lines += [
        "",
        "## 数据缺口",
        "",
        "- 本文件没有涨停全景、连板天梯、热榜、龙虎榜、政策新闻。",
        "- 历史复盘归因必须继续补这些事实层，不能只用本文件定性。",
        "",
        "## 股票来源文件",
        "",
    ]
    for source in payload.get("股票来源文件", []):
        lines.append(f"- `{source}`")
    return "\n".join(lines) + "\n"


def write_payload(date: str, payload: dict[str, Any], output_root: Path) -> None:
    out_dir = output_root / date
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "tdxrs-历史量价底座.json"
    md_path = out_dir / "tdxrs-历史量价底座.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_md(payload), encoding="utf-8")
    print(f"写入：{json_path}")
    print(f"写入：{md_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="tdxrs 历史复盘市场环境量价底座")
    parser.add_argument("--dates", required=True, help="逗号分隔日期，例如 2026-05-21,2026-05-25")
    parser.add_argument("--codes", default="", help="额外股票代码，逗号分隔")
    parser.add_argument("--limit", type=int, default=80, help="每个日期最多自动识别股票数")
    parser.add_argument("--count", type=int, default=220, help="每只证券拉取最近日K数量")
    parser.add_argument("--windows", default="0,1,3,5,10", help="D+窗口，逗号分隔")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="输出根目录")
    args = parser.parse_args()

    dates = [x.strip() for x in args.dates.split(",") if x.strip()]
    codes = [x.strip() for x in args.codes.split(",") if x.strip()]
    windows = [int(x.strip()) for x in args.windows.split(",") if x.strip()]

    TdxHqClient, _, _, _, _ = load_tdxrs()
    client = TdxHqClient()
    try:
        client.connect_to_any()
    except Exception as exc:
        raise SystemExit(f"tdxrs 连接失败：{exc}") from exc

    for date in dates:
        stock_codes, sources = collect_codes(date, codes, args.limit)
        payload = {
            "数据日期": date,
            "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "数据源": "tdxrs",
            "接口边界": "只补指数/个股量价、指数上涨下跌家数、D+窗口；不替代热榜、涨停原因、龙虎榜、政策新闻。",
            "股票数量": len(stock_codes),
            "股票来源文件": sources,
            "指数": fetch_index(client, date, windows, args.count),
            "股票": fetch_stocks(client, stock_codes, date, windows, args.count),
        }
        write_payload(date, payload, Path(args.output_root))


if __name__ == "__main__":
    main()
