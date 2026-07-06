#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tdxrs 竞价/盘口快照采集。

tdxrs 当前没有独立“集合竞价明细”接口，本脚本按可验证数据落 RAW：
- 09:15/09:20/09:24:50/09:25:05/09:30 多时点实时行情五档快照
- 09:25 后逐笔成交样本
- 09:30 后当日分时样本
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = ROOT / "raw" / "04-市场数据" / "tdxrs竞价快照"
DEFAULT_SESSION_LABELS = ["09:15", "09:20", "09:24:50", "09:25:05", "09:30"]
CODE_RE = re.compile(r"(?<!\d)(?:[0368]\d{5}|4\d{5}|92\d{4})(?!\d)")


def load_tdxrs():
    try:
        from tdxrs import TdxHqClient  # type: ignore
        from tdxrs.constants import MARKET_BJ, MARKET_SH, MARKET_SZ  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime guard
        raise SystemExit(
            "未安装 tdxrs。请先执行："
            ".system/venv-tdxrs/bin/python -m pip install tdxrs"
        ) from exc
    return TdxHqClient, MARKET_SH, MARKET_SZ, MARKET_BJ


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def normalize_code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    match = CODE_RE.search(text)
    return match.group(0) if match else None


def infer_market(code: str) -> int:
    _, MARKET_SH, MARKET_SZ, MARKET_BJ = load_tdxrs()
    if code.startswith(("60", "68", "9")):
        return MARKET_SH
    if code.startswith(("8", "4", "92")):
        return MARKET_BJ
    return MARKET_SZ


def market_name(market: int) -> str:
    if market == 1:
        return "沪市"
    if market == 2:
        return "北交所"
    return "深市"


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def pick_name(row: dict[str, Any]) -> str:
    for key in ("名称", "股票名称", "证券名称", "name", "股票", "简称"):
        value = row.get(key)
        if value:
            return str(value).strip()
    return ""


def pick_code(row: dict[str, Any]) -> str | None:
    for key in ("代码", "股票代码", "证券代码", "code", "symbol"):
        code = normalize_code(row.get(key))
        if code:
            return code
    for value in row.values():
        code = normalize_code(value)
        if code:
            return code
    return None


def add_stock(stocks: dict[str, dict[str, Any]], code: str, name: str, source: str) -> None:
    if code not in stocks:
        stocks[code] = {
            "证券代码": code,
            "证券名称": name,
            "市场": market_name(infer_market(code)),
            "来源": [],
        }
    if name and not stocks[code].get("证券名称"):
        stocks[code]["证券名称"] = name
    if source not in stocks[code]["来源"]:
        stocks[code]["来源"].append(source)


def collect_from_json(path: Path, stocks: dict[str, dict[str, Any]], source: str) -> None:
    data = read_json(path)
    if data is None:
        return
    for row in iter_dicts(data):
        code = pick_code(row)
        if code:
            add_stock(stocks, code, pick_name(row), source)


def collect_from_text(path: Path, stocks: dict[str, dict[str, Any]], source: str) -> None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
    for code in sorted(set(CODE_RE.findall(text))):
        add_stock(stocks, code, "", source)


def dated_source_path(base: Path, date: str, filename: str) -> Path | None:
    exact = base / date / filename
    if exact.exists():
        return exact
    candidates: list[Path] = []
    if base.exists():
        for child in base.iterdir():
            if not child.is_dir():
                continue
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", child.name):
                continue
            if child.name <= date and (child / filename).exists():
                candidates.append(child / filename)
    return sorted(candidates)[-1] if candidates else None


def collect_watchlist(date: str, explicit_codes: list[str], limit: int) -> list[dict[str, Any]]:
    stocks: dict[str, dict[str, Any]] = {}
    for raw_code in explicit_codes:
        code = normalize_code(raw_code)
        if code:
            add_stock(stocks, code, "", "命令行指定")

    candidate_files: list[Path | None] = [
        ROOT / "raw" / "03-每日计划" / f"{date}-竞价监控清单.md",
        ROOT / "wiki" / "07-作战室" / f"{date}-作战室候选票评分表.md",
        dated_source_path(ROOT / "raw" / "04-市场数据" / "同花顺热榜", date, "ths-hot-top100.json"),
        dated_source_path(ROOT / "raw" / "04-市场数据" / "通达信热榜", date, "tdx-hot-top100.json"),
        dated_source_path(ROOT / "raw" / "04-市场数据" / "通达信成交额排名", date, "tdx-成交额Top100.json"),
        dated_source_path(ROOT / "raw" / "04-市场数据" / "每日涨停全景", date, "tdx-daily-limit.json"),
        dated_source_path(ROOT / "raw" / "04-市场数据" / "通达信连板天梯", date, "tdx-limit-ladder.json"),
    ]
    for path in candidate_files:
        if path is None or not path.exists():
            continue
        rel = str(path.relative_to(ROOT))
        if path.suffix.lower() == ".json":
            collect_from_json(path, stocks, rel)
        else:
            collect_from_text(path, stocks, rel)

    result = list(stocks.values())
    source_priority = {
        "命令行指定": 0,
        "raw/03-每日计划": 1,
        "wiki/07-作战室": 2,
        "每日涨停全景": 3,
        "通达信连板天梯": 4,
        "同花顺热榜": 5,
        "通达信热榜": 6,
        "通达信成交额排名": 7,
    }

    def rank(item: dict[str, Any]) -> tuple[int, str]:
        sources = item.get("来源") or []
        score = min(
            (value for key, value in source_priority.items() if any(key in s for s in sources)),
            default=99,
        )
        return score, item["证券代码"]

    result.sort(key=rank)
    return result[:limit]


def pct(value: Any, base: Any) -> float | None:
    try:
        value_f = float(value)
        base_f = float(base)
        if base_f == 0:
            return None
        return round((value_f / base_f - 1) * 100, 2)
    except Exception:
        return None


def number(value: Any) -> float | None:
    try:
        return round(float(value), 4)
    except Exception:
        return None


def quote_to_chinese(raw: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    buy_levels = []
    sell_levels = []
    for index in range(1, 6):
        buy_levels.append(
            {
                "档位": f"买{index}",
                "价格": number(raw.get(f"bid{index}")),
                "挂单量": number(raw.get(f"bid_vol{index}")),
            }
        )
        sell_levels.append(
            {
                "档位": f"卖{index}",
                "价格": number(raw.get(f"ask{index}")),
                "挂单量": number(raw.get(f"ask_vol{index}")),
            }
        )
    latest = raw.get("price")
    prev_close = raw.get("last_close")
    buy_total = sum(float(x.get("挂单量") or 0) for x in buy_levels)
    sell_total = sum(float(x.get("挂单量") or 0) for x in sell_levels)
    return {
        "证券代码": meta["证券代码"],
        "证券名称": meta.get("证券名称", ""),
        "市场": meta.get("市场", market_name(raw.get("market", infer_market(meta["证券代码"])))),
        "来源": meta.get("来源", []),
        "最新价": number(latest),
        "昨收价": number(prev_close),
        "开盘价": number(raw.get("open")),
        "最高价": number(raw.get("high")),
        "最低价": number(raw.get("low")),
        "涨跌幅": pct(latest, prev_close),
        "成交量": number(raw.get("vol")),
        "现手": number(raw.get("cur_vol")),
        "成交额": number(raw.get("amount")),
        "主动买量": number(raw.get("b_vol")),
        "主动卖量": number(raw.get("s_vol")),
        "买盘五档": buy_levels,
        "卖盘五档": sell_levels,
        "五档买量合计": round(buy_total, 4),
        "五档卖量合计": round(sell_total, 4),
        "五档买卖量差": round(buy_total - sell_total, 4),
        "通达信服务器时间": raw.get("servertime"),
        "竞价解释": "tdxrs 无独立集合竞价接口；本记录为实时行情五档快照，可用于竞价强弱和撤单变化对比。",
    }


def transaction_to_chinese(row: dict[str, Any]) -> dict[str, Any]:
    side_map = {0: "中性/未知", 1: "卖出", 2: "买入"}
    side = row.get("buyorsell")
    return {
        "时间": row.get("time"),
        "价格": number(row.get("price")),
        "成交量": number(row.get("vol")),
        "笔数": row.get("num"),
        "方向": side_map.get(side, side),
    }


def minute_to_chinese(row: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "序号": index + 1,
        "价格": number(row.get("price")),
        "成交量": number(row.get("vol")),
    }


def fetch_snapshot(stocks: list[dict[str, Any]], include_detail: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    TdxHqClient, _, _, _ = load_tdxrs()
    client = TdxHqClient()
    errors: list[dict[str, Any]] = []
    try:
        client.connect_to_any()
    except Exception as exc:
        raise SystemExit(f"tdxrs 连接失败：{exc}") from exc

    by_code = {item["证券代码"]: item for item in stocks}
    pairs = [(infer_market(item["证券代码"]), item["证券代码"]) for item in stocks]
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []

    for start in range(0, len(pairs), 60):
        batch = pairs[start : start + 60]
        try:
            quotes = client.get_security_quotes(batch)
        except Exception as exc:
            errors.append({"批次": start // 60 + 1, "错误": str(exc)})
            continue
        for quote in quotes:
            code = str(quote.get("code", ""))
            meta = by_code.get(code, {"证券代码": code, "证券名称": "", "来源": []})
            row = quote_to_chinese(quote, meta)
            rows.append(row)

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    for row in rows:
        row["本轮行情耗时毫秒"] = elapsed_ms

    if include_detail:
        for row in rows:
            code = row["证券代码"]
            market = infer_market(code)
            try:
                transactions = client.get_transaction_data(market, code, 0, 20)
                row["逐笔成交样本"] = [transaction_to_chinese(item) for item in transactions[:20]]
            except Exception as exc:
                row["逐笔成交样本"] = []
                errors.append({"证券代码": code, "环节": "逐笔成交", "错误": str(exc)})
            try:
                minute_rows = client.get_minute_time_data(market, code)
                row["分时样本"] = [minute_to_chinese(item, i) for i, item in enumerate(minute_rows[:10])]
            except Exception as exc:
                row["分时样本"] = []
                errors.append({"证券代码": code, "环节": "分时", "错误": str(exc)})

    return rows, errors


def write_outputs(date: str, label: str, stocks: list[dict[str, Any]], rows: list[dict[str, Any]], errors: list[dict[str, Any]], out_root: Path) -> None:
    out_dir = out_root / date
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "数据日期": date,
        "快照标签": label,
        "采集时间": now,
        "数据源": "tdxrs",
        "接口边界": "无独立集合竞价接口；采集实时行情五档、逐笔成交、分时样本。",
        "股票数量": len(stocks),
        "成功数量": len(rows),
        "失败数量": len(errors),
        "股票来源": stocks,
        "快照": rows,
        "错误": errors,
    }
    json_path = out_dir / f"tdxrs-竞价快照-{label}.json"
    md_path = out_dir / f"tdxrs-竞价快照-{label}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_md(payload), encoding="utf-8")

    summary_path = out_dir / "tdxrs-竞价快照汇总.json"
    summary: list[dict[str, Any]] = []
    if summary_path.exists():
        try:
            old = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(old, list):
                summary = old
        except Exception:
            summary = []
    summary = [item for item in summary if item.get("快照标签") != label]
    summary.append(payload)
    summary.sort(key=lambda item: str(item.get("快照标签", "")))
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "tdxrs-竞价快照汇总.md").write_text(render_summary_md(summary), encoding="utf-8")
    append_log(out_dir, payload)


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['数据日期']} tdxrs 竞价快照 {payload['快照标签']}",
        "",
        f"- 采集时间：{payload['采集时间']}",
        f"- 数据源：{payload['数据源']}",
        f"- 接口边界：{payload['接口边界']}",
        f"- 成功/总数：{payload['成功数量']}/{payload['股票数量']}",
        f"- 失败数量：{payload['失败数量']}",
        "",
        "## 快照表",
        "",
        "| 股票 | 最新价 | 涨跌幅 | 成交额 | 五档买量 | 五档卖量 | 买卖量差 | 现手 | 来源 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload["快照"]:
        name = row.get("证券名称") or ""
        stock = f"{row.get('证券代码','')} {name}".strip()
        sources = "；".join(row.get("来源", [])[:2])
        lines.append(
            "| {stock} | {price} | {pct} | {amount} | {buy} | {sell} | {diff} | {cur} | {sources} |".format(
                stock=stock,
                price=row.get("最新价", ""),
                pct="" if row.get("涨跌幅") is None else f"{row.get('涨跌幅')}%",
                amount=row.get("成交额", ""),
                buy=row.get("五档买量合计", ""),
                sell=row.get("五档卖量合计", ""),
                diff=row.get("五档买卖量差", ""),
                cur=row.get("现手", ""),
                sources=sources,
            )
        )
    if payload["错误"]:
        lines += ["", "## 错误", ""]
        for item in payload["错误"]:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    lines += [
        "",
        "## 使用说明",
        "",
        "这不是独立集合竞价明细。用于比较 09:15、09:20、09:24:50、09:25:05、09:30 之间的价格、成交额、五档买卖量和逐笔成交变化。",
    ]
    return "\n".join(lines) + "\n"


def render_summary_md(summary: list[dict[str, Any]]) -> str:
    date = summary[-1]["数据日期"] if summary else today_str()
    lines = [
        f"# {date} tdxrs 竞价快照汇总",
        "",
        "| 标签 | 采集时间 | 成功/总数 | 失败 | 文件用途 |",
        "|---|---|---:|---:|---|",
    ]
    for item in summary:
        lines.append(
            f"| {item.get('快照标签')} | {item.get('采集时间')} | {item.get('成功数量')}/{item.get('股票数量')} | {item.get('失败数量')} | 竞价多时点对比 |"
        )
    lines += [
        "",
        "## 判断边界",
        "",
        "- 09:15 和 09:20 重点看价格、五档挂单和撤单变化。",
        "- 09:24:50 到 09:25:05 重点看最终撮合前后是否大幅变脸。",
        "- 09:30 后才适合结合分时和逐笔成交判断开盘承接。",
    ]
    return "\n".join(lines) + "\n"


def append_log(out_dir: Path, payload: dict[str, Any]) -> None:
    path = out_dir / "tdxrs-竞价运行日志.md"
    line = (
        f"- {payload['采集时间']} 标签={payload['快照标签']} "
        f"成功={payload['成功数量']}/{payload['股票数量']} 失败={payload['失败数量']}\n"
    )
    if not path.exists():
        path.write_text("# tdxrs 竞价运行日志\n\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def seconds_until_today_time(label: str) -> float:
    now = datetime.now()
    parts = [int(x) for x in label.split(":")]
    if len(parts) == 2:
        hour, minute = parts
        second = 0
    else:
        hour, minute, second = parts
    target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    return (target - now).total_seconds()


def run_once(args: argparse.Namespace, label: str) -> None:
    date = args.date
    codes = args.codes or []
    stocks = collect_watchlist(date, codes, args.limit)
    if not stocks:
        raise SystemExit("没有找到可采集股票。请传 --codes 600519,000858 或先生成竞价监控清单/热榜数据。")
    rows, errors = fetch_snapshot(stocks, args.include_detail)
    write_outputs(date, label, stocks, rows, errors, Path(args.output_root))
    print(f"写入完成：{DEFAULT_OUTPUT_ROOT / date} 标签={label} 成功={len(rows)}/{len(stocks)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="tdxrs 竞价/盘口快照采集")
    parser.add_argument("--date", default=today_str(), help="数据日期，默认今天")
    parser.add_argument("--label", default=None, help="快照标签，例如 09:15、09:20、盘中测试")
    parser.add_argument("--codes", default="", help="逗号分隔股票代码；为空则自动从竞价清单/热榜/涨停全景抽取")
    parser.add_argument("--limit", type=int, default=80, help="最多采集股票数")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="输出根目录")
    parser.add_argument("--include-detail", action="store_true", help="同时采集逐笔成交和分时样本")
    parser.add_argument("--session", action="store_true", help="按 09:15/09:20/09:24:50/09:25:05/09:30 多时点运行")
    parser.add_argument("--labels", default=",".join(DEFAULT_SESSION_LABELS), help="session 模式采集时点")
    args = parser.parse_args()
    args.codes = [x.strip() for x in args.codes.split(",") if x.strip()]

    if not args.session:
        label = args.label or datetime.now().strftime("%H%M%S")
        run_once(args, label)
        return

    for label in [x.strip() for x in args.labels.split(",") if x.strip()]:
        wait = seconds_until_today_time(label)
        if wait > 0:
            time.sleep(wait)
        run_once(args, label)


if __name__ == "__main__":
    main()
