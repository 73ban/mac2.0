#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mac 端收盘基础数据采集。

用途：
- L1 四大指数收盘：tdxrs 指数日 K。
- L5 成交额 Top100：用股票池 + tdxrs 批量报价按成交额排序。

边界：
- 纯数据采集，不调用 LLM，不写交易结论。
- 成交额 Top100 优先使用缓存股票池；股票池可来自东方财富全市场快照或 tdxrs 周末刷新。
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw" / "04-市场数据"
UNIVERSE_CACHE = ROOT / ".system" / "tdxrs-stock-universe.json"
CODE_RE = re.compile(
    r"^(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|43\d{4}|83\d{4}|87\d{4}|92\d{4})$"
)

INDEXES = [
    {"证券代码": "000001", "证券名称": "上证指数", "市场": "沪市"},
    {"证券代码": "399001", "证券名称": "深证成指", "市场": "深市"},
    {"证券代码": "399006", "证券名称": "创业板指", "市场": "深市"},
    {"证券代码": "000688", "证券名称": "科创50", "市场": "沪市"},
]


def load_tdxrs():
    try:
        from tdxrs import TdxHqClient  # type: ignore
        from tdxrs.constants import KLINE_DAILY, MARKET_BJ, MARKET_SH, MARKET_SZ  # type: ignore
    except Exception as exc:
        raise SystemExit("未安装 tdxrs，请先安装到 .system/venv-tdxrs。") from exc
    return TdxHqClient, KLINE_DAILY, MARKET_SH, MARKET_SZ, MARKET_BJ


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def number(value: Any) -> float | None:
    try:
        return round(float(value), 4)
    except Exception:
        return None


def pct(value: Any, base: Any) -> float | None:
    try:
        value_f = float(value)
        base_f = float(base)
        if base_f == 0:
            return None
        return round((value_f / base_f - 1) * 100, 2)
    except Exception:
        return None


def infer_market_name(code: str) -> str:
    if code.startswith(("60", "68")):
        return "沪市"
    if code.startswith(("43", "83", "87", "92")):
        return "北交所"
    return "深市"


def infer_market_code(code: str) -> int:
    _, _, market_sh, market_sz, market_bj = load_tdxrs()
    if code.startswith(("60", "68")):
        return market_sh
    if code.startswith(("43", "83", "87", "92")):
        return market_bj
    return market_sz


def market_from_name(name: str) -> int:
    _, _, market_sh, market_sz, market_bj = load_tdxrs()
    if name == "沪市":
        return market_sh
    if name == "北交所":
        return market_bj
    return market_sz


def latest_eastmoney_snapshot() -> Path | None:
    files = sorted((RAW / "东方财富").glob("*/market-snapshot.json"))
    return files[-1] if files else None


def universe_from_eastmoney() -> list[dict[str, Any]]:
    path = latest_eastmoney_snapshot()
    if not path:
        return []
    payload = read_json(path, {})
    rows = (((payload.get("stocks") or {}).get("data") or {}).get("diff") or [])
    out = []
    for row in rows:
        code = str(row.get("f12") or "").strip()
        if not CODE_RE.match(code):
            continue
        out.append(
            {
                "股票代码": code,
                "股票名称": str(row.get("f14") or "").strip(),
                "市场": infer_market_name(code),
                "股票池来源": str(path.relative_to(ROOT)),
            }
        )
    return out


def build_tdxrs_universe(client: Any, max_pages_per_market: int) -> list[dict[str, Any]]:
    _, _, market_sh, market_sz, market_bj = load_tdxrs()
    markets = [(market_sh, "沪市"), (market_sz, "深市"), (market_bj, "北交所")]
    out: dict[str, dict[str, Any]] = {}
    for market, market_name in markets:
        for page in range(max_pages_per_market):
            start = page * 1000
            try:
                rows = client.get_security_list(market, start)
            except Exception:
                break
            if not rows:
                break
            for row in rows:
                code = str(row.get("code") or "").strip()
                if not CODE_RE.match(code):
                    continue
                out[code] = {
                    "股票代码": code,
                    "股票名称": str(row.get("name") or "").strip(),
                    "市场": market_name,
                    "股票池来源": "tdxrs证券列表",
                }
            if len(rows) < 1000:
                break
    result = sorted(out.values(), key=lambda item: item["股票代码"])
    write_json(
        UNIVERSE_CACHE,
        {
            "生成时间": now_text(),
            "来源": "tdxrs证券列表",
            "股票数量": len(result),
            "数据": result,
        },
    )
    return result


def load_universe(client: Any, refresh: bool, max_pages_per_market: int) -> tuple[list[dict[str, Any]], str]:
    if refresh:
        universe = build_tdxrs_universe(client, max_pages_per_market)
        if universe:
            return universe, "tdxrs证券列表刷新"
    cached = read_json(UNIVERSE_CACHE, {})
    cached_rows = cached.get("数据") if isinstance(cached, dict) else None
    if isinstance(cached_rows, list) and cached_rows:
        return cached_rows, "tdxrs股票池缓存"
    em_rows = universe_from_eastmoney()
    if em_rows:
        write_json(
            UNIVERSE_CACHE,
            {
                "生成时间": now_text(),
                "来源": "东方财富全市场快照缓存",
                "股票数量": len(em_rows),
                "数据": em_rows,
            },
        )
        return em_rows, "东方财富全市场快照缓存"
    return [], "无股票池"


def normalize_index_bar(meta: dict[str, Any], row: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "证券代码": meta["证券代码"],
        "证券名称": meta["证券名称"],
        "市场": meta["市场"],
        "交易日期": row.get("datetime"),
        "开盘价": number(row.get("open")),
        "收盘价": number(row.get("close")),
        "最高价": number(row.get("high")),
        "最低价": number(row.get("low")),
        "涨跌幅": pct(row.get("close"), prev.get("close") if prev else None),
        "成交量": number(row.get("vol")),
        "成交额": number(row.get("amount")),
        "上涨家数": row.get("up_count"),
        "下跌家数": row.get("down_count"),
    }


def fetch_indices(client: Any, requested_date: str, count: int) -> tuple[list[dict[str, Any]], str | None]:
    _, kline_daily, _, _, _ = load_tdxrs()
    out = []
    evidence_dates = []
    for meta in INDEXES:
        try:
            rows = client.get_index_bars(kline_daily, market_from_name(meta["市场"]), meta["证券代码"], 0, count)
        except Exception as exc:
            out.append({**meta, "错误": str(exc)})
            continue
        if not rows:
            out.append({**meta, "错误": "无K线"})
            continue
        candidates = [row for row in rows if str(row.get("datetime") or "") <= requested_date]
        target = candidates[-1] if candidates else rows[-1]
        idx = rows.index(target)
        prev = rows[idx - 1] if idx > 0 else None
        evidence_dates.append(str(target.get("datetime")))
        out.append(normalize_index_bar(meta, target, prev))
    evidence_date = max(evidence_dates) if evidence_dates else None
    return out, evidence_date


def quote_to_row(rank: int, quote: dict[str, Any], meta: dict[str, Any], trade_date: str, pulled_at: str) -> dict[str, Any]:
    amount = number(quote.get("amount")) or 0
    volume = number(quote.get("vol"))
    latest = number(quote.get("price"))
    prev = number(quote.get("last_close"))
    return {
        "交易日期": trade_date,
        "数据时间": pulled_at,
        "排名": rank,
        "股票代码": meta["股票代码"],
        "股票名称": meta.get("股票名称", ""),
        "市场类型": meta.get("市场", infer_market_name(meta["股票代码"])),
        "现价": latest,
        "涨跌幅": pct(latest, prev),
        "成交额亿": round(amount / 100000000, 4),
        "成交额": amount,
        "成交量手": volume,
        "主动买量": number(quote.get("b_vol")),
        "主动卖量": number(quote.get("s_vol")),
        "开盘价": number(quote.get("open")),
        "最高价": number(quote.get("high")),
        "最低价": number(quote.get("low")),
        "昨收价": prev,
        "数据源": "Mac tdxrs批量报价",
        "拉取人": "Codex/Mac自动事实层",
        "数据缺口": ["概念标签待板块成分股映射补", "主力净额待zjlx资金流向补"],
    }


def fetch_turnover_top100(client: Any, universe: list[dict[str, Any]], limit: int, batch_size: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_code = {item["股票代码"]: item for item in universe if CODE_RE.match(str(item.get("股票代码") or ""))}
    pairs = [(infer_market_code(code), code) for code in by_code]
    rows = []
    errors = []
    for start in range(0, len(pairs), batch_size):
        batch = pairs[start : start + batch_size]
        try:
            quotes = client.get_security_quotes(batch)
        except Exception as exc:
            errors.append({"批次": start // batch_size + 1, "起始": start, "错误": str(exc)})
            continue
        for quote in quotes:
            code = str(quote.get("code") or "")
            amount = number(quote.get("amount")) or 0
            if amount <= 0:
                continue
            rows.append((amount, quote, by_code.get(code, {"股票代码": code, "股票名称": "", "市场": infer_market_name(code)})))
    rows.sort(key=lambda item: item[0], reverse=True)
    pulled_at = now_text()
    return [quote_to_row(i + 1, quote, meta, "", pulled_at) for i, (_, quote, meta) in enumerate(rows[:limit])], errors


def render_turnover_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['元数据']['交易日期']} 成交额Top100",
        "",
        f"- 拉取时间：{payload['拉取时间']}",
        f"- 数据源：{payload['元数据']['数据源']}",
        f"- 股票池：{payload['元数据']['股票池来源']}，数量 {payload['元数据']['股票池数量']}",
        f"- 实际获取：{payload['元数据']['实际获取']}",
        "",
        "| 排名 | 代码 | 名称 | 涨跌幅% | 成交额亿 | 现价 | 市场 |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for row in payload["数据"]:
        lines.append(
            f"| {row['排名']} | {row['股票代码']} | {row['股票名称']} | {row.get('涨跌幅','')} | {row.get('成交额亿','')} | {row.get('现价','')} | {row.get('市场类型','')} |"
        )
    if payload.get("错误"):
        lines += ["", "## 错误", ""]
        for item in payload["错误"]:
            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def render_basics_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['检查日期']} 收盘基础数据",
        "",
        f"- 拉取时间：{payload['生成时间']}",
        f"- 证据交易日：{payload.get('证据交易日')}",
        f"- 数据源：{payload['数据源']}",
        "",
        "## 四大指数",
        "",
        "| 指数 | 交易日 | 收盘 | 涨跌幅% | 成交额 | 上涨家数 | 下跌家数 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload["四大指数"]:
        lines.append(
            f"| {row.get('证券名称')} | {row.get('交易日期')} | {row.get('收盘价','')} | {row.get('涨跌幅','')} | {row.get('成交额','')} | {row.get('上涨家数','')} | {row.get('下跌家数','')} |"
        )
    lines += [
        "",
        "## 成交额Top20",
        "",
        "| 排名 | 代码 | 名称 | 涨跌幅% | 成交额亿 |",
        "|---:|---|---|---:|---:|",
    ]
    for row in payload["成交额Top100"][:20]:
        lines.append(f"| {row['排名']} | {row['股票代码']} | {row['股票名称']} | {row.get('涨跌幅','')} | {row.get('成交额亿','')} |")
    return "\n".join(lines) + "\n"


def write_outputs(date: str, indices: list[dict[str, Any]], evidence_date: str | None, turnover: list[dict[str, Any]], errors: list[dict[str, Any]], source: str, universe_count: int) -> None:
    for row in turnover:
        row["交易日期"] = evidence_date or date
    generated_at = now_text()
    basics = {
        "模式版本": "73wiki-mac-tdxrs-close-basics-v1",
        "检查日期": date,
        "证据交易日": evidence_date,
        "生成时间": generated_at,
        "拉取人": "Codex/Mac自动事实层",
        "数据源": "tdxrs指数K线 + tdxrs批量报价",
        "四大指数": indices,
        "成交额Top100": turnover,
        "错误": errors,
        "说明": "纯数据采集，不调用LLM；L1指数和L5成交额Top100由Mac本机承担。",
    }
    basics_dir = RAW / "收盘基础数据" / date
    write_json(basics_dir / "tdx-close-basics.json", basics)
    (basics_dir / "tdx-close-basics.md").write_text(render_basics_md(basics), encoding="utf-8")

    turnover_payload = {
        "模式版本": "73wiki-成交额排名-v2-mac-tdxrs",
        "拉取时间": generated_at,
        "拉取人": "Codex/Mac自动事实层",
        "目的": "Mac端自动拉取全市场成交额Top100，减少外部模型和图片token消耗",
        "元数据": {
            "交易日期": evidence_date or date,
            "请求日期": date,
            "数据源": "tdxrs批量实时行情",
            "股票池来源": source,
            "股票池数量": universe_count,
            "排名依据": "今日成交额从大到小",
            "目标数量": 100,
            "实际获取": len(turnover),
            "是否完整Top100": len(turnover) == 100,
            "费用": "0 LLM token；本机行情接口",
            "数据缺口": ["概念标签、主力净额需后续板块/资金流向补齐"],
        },
        "数据": turnover,
        "错误": errors,
    }
    turnover_dir = RAW / "通达信成交额排名" / date
    write_json(turnover_dir / "tdx-成交额Top100.json", turnover_payload)
    (turnover_dir / "tdx-成交额Top100.md").write_text(render_turnover_md(turnover_payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mac tdxrs 收盘基础数据：四大指数 + 成交额Top100")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--refresh-universe", action="store_true", help="用tdxrs刷新股票池，较慢，建议周末跑")
    parser.add_argument("--max-pages-per-market", type=int, default=8, help="刷新tdxrs股票池时每市场最多页数")
    parser.add_argument("--batch-size", type=int, default=60)
    parser.add_argument("--top", type=int, default=100)
    args = parser.parse_args()

    TdxHqClient, _, _, _, _ = load_tdxrs()
    client = TdxHqClient()
    client.connect_to_any()
    universe, source = load_universe(client, args.refresh_universe, args.max_pages_per_market)
    if not universe:
        raise SystemExit("没有可用股票池，无法生成成交额Top100。")
    indices, evidence_date = fetch_indices(client, args.date, 180)
    turnover, errors = fetch_turnover_top100(client, universe, args.top, args.batch_size)
    write_outputs(args.date, indices, evidence_date, turnover, errors, source, len(universe))
    print(f"written date={args.date} evidence={evidence_date} universe={len(universe)} turnover={len(turnover)} errors={len(errors)} source={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
