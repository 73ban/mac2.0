#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公告事件 D+ 自动回填。"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
WIKI = ROOT / "wiki"
QUEUE = WIKI / "09-统计与进化" / "公告事件D+验证队列.md"
RESULTS = ROOT / "data" / "facts" / "announcement_event_validation_results.jsonl"
OUT_DIR = ROOT / ".llm-wiki" / "announcement-dplus-autofill"
EVENT_DIR = WIKI / "03-L3个股档案" / "公告事件档案"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_cell(value: str) -> str:
    return value.strip().strip("`")


def symbol_for(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    if code.startswith("8"):
        return f"bj{code}"
    return f"sz{code}"


def limit_threshold(code: str) -> float:
    if code.startswith(("300", "301", "688")):
        return 19.5
    if code.startswith(("8", "9")):
        return 29.0
    return 9.5


def market_closed(now: datetime) -> bool:
    return now.hour > 15 or (now.hour == 15 and now.minute >= 5)


def parse_queue() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in read_text(QUEUE).splitlines():
        if not line.startswith("| 20"):
            continue
        cells = [normalize_cell(c) for c in line.strip().strip("|").split("|")]
        if len(cells) < 12:
            continue
        rows.append(
            {
                "入队日": cells[0],
                "事件ID": cells[1],
                "股票代码": cells[2],
                "公司名称": cells[3],
                "公告类型": cells[4],
                "首个验证日": cells[5],
                "D+1": cells[6],
                "D+3": cells[7],
                "D+5": cells[8],
                "D+10": cells[9],
                "初始假设": cells[10],
                "状态": cells[11],
            }
        )
    return rows


def result_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("事件ID", "")), str(row.get("验证节点", "")))


def load_existing_results() -> dict[tuple[str, str], dict[str, Any]]:
    existing: dict[tuple[str, str], dict[str, Any]] = {}
    if not RESULTS.exists():
        return existing
    for line in RESULTS.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        key = result_key(row)
        if all(key):
            existing[key] = row
    return existing


def due_nodes(item: dict[str, Any], today: str, existing: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = [
        ("D+0", item.get("首个验证日")),
        ("D+1", item.get("D+1")),
        ("D+3", item.get("D+3")),
        ("D+5", item.get("D+5")),
        ("D+10", item.get("D+10")),
    ]
    out: list[dict[str, Any]] = []
    for node, due_date in nodes:
        if not due_date or due_date > today:
            continue
        row = {**item, "验证节点": node, "到期日": due_date}
        if result_key(row) in existing:
            continue
        out.append(row)
    return out


def fetch_kline(code: str, days: int = 40) -> list[dict[str, Any]]:
    symbol = symbol_for(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{days},qfq"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    rows = payload.get("data", {}).get(symbol, {}).get("qfqday")
    if not rows:
        rows = payload.get("data", {}).get(symbol, {}).get("day", [])
    bars: list[dict[str, Any]] = []
    for row in rows or []:
        try:
            trade_date, open_price, close, high, low, volume = row[:6]
            bars.append(
                {
                    "date": str(trade_date),
                    "open": float(open_price),
                    "close": float(close),
                    "high": float(high),
                    "low": float(low),
                    "volume": float(volume),
                    "raw": row,
                }
            )
        except Exception:
            continue
    return bars


def bar_pair_for_date(bars: list[dict[str, Any]], due_date: str) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    for idx, bar in enumerate(bars):
        if bar.get("date") == due_date:
            prev = bars[idx - 1] if idx > 0 else None
            return prev, bar
    return None, None


def classify_feedback(code: str, pct: float, bar: dict[str, Any], prev_bar: dict[str, Any], initial: str, node: str) -> dict[str, str]:
    prev_close = float(prev_bar["close"])
    open_pct = ((float(bar["open"]) - prev_close) / prev_close * 100) if prev_close else 0.0
    high_pct = ((float(bar["high"]) - prev_close) / prev_close * 100) if prev_close else 0.0
    threshold = limit_threshold(code)
    positive_expected = "正向" in initial
    risk_expected = "负向" in initial or "压制" in initial
    failed_intraday = high_pct >= 5 and pct < 2

    if pct >= threshold:
        feedback = "持续强反馈" if node != "D+0" else "涨停强反馈"
        decision = "公告有效，升权观察"
        pattern = "公告被市场强定价"
    elif pct >= 5:
        feedback = "正反馈"
        decision = "保留观察"
        pattern = "公告有弹性，但要继续验证持续性"
    elif failed_intraday:
        feedback = "一日游风险"
        decision = "不升权，等待后续节点"
        pattern = "冲高回落，公告可能只兑现预期"
    elif pct >= 0:
        feedback = "弱反馈"
        decision = "归档观察" if positive_expected else "风险未扩散"
        pattern = "公告有反应但强度不足"
    elif pct > -5:
        feedback = "负反馈"
        decision = "降权"
        pattern = "市场不认可公告或情绪环境压制"
    else:
        feedback = "强负反馈"
        decision = "证伪或风险强化"
        pattern = "公告后大幅走弱，进入负样本"

    if risk_expected and pct <= -5:
        pattern = "风险公告被市场确认"
    elif risk_expected and pct >= 0:
        pattern = "风险公告未被市场放大，可能被忽略或提前消化"

    return {
        "开盘反馈": f"{open_pct:.2f}%",
        "最高反馈": f"{high_pct:.2f}%",
        "收盘反馈": f"{pct:.2f}%",
        "反馈结论": feedback,
        "处理结论": decision,
        "规律标签": pattern,
    }


def build_result(item: dict[str, Any], prev_bar: dict[str, Any], bar: dict[str, Any], generated_at: str) -> dict[str, Any]:
    prev_close = float(prev_bar["close"])
    close = float(bar["close"])
    pct = ((close - prev_close) / prev_close * 100) if prev_close else 0.0
    verdict = classify_feedback(item["股票代码"], pct, bar, prev_bar, item["初始假设"], item["验证节点"])
    return {
        "schema": "73wiki-announcement-event-validation-v1",
        "生成时间": generated_at,
        "事件ID": item["事件ID"],
        "验证节点": item["验证节点"],
        "到期日": item["到期日"],
        "股票代码": item["股票代码"],
        "公司名称": item["公司名称"],
        "公告类型": item["公告类型"],
        "初始假设": item["初始假设"],
        "前收盘": round(prev_close, 2),
        "开盘": round(float(bar["open"]), 2),
        "最高": round(float(bar["high"]), 2),
        "最低": round(float(bar["low"]), 2),
        "收盘": round(close, 2),
        "涨跌幅": round(pct, 2),
        **verdict,
        "证据": f"腾讯复权日K {item['到期日']} close={close:.2f} prev_close={prev_close:.2f} pct={pct:.2f}% symbol={symbol_for(item['股票代码'])}",
        "状态": "resolved",
    }


def append_results(rows: list[dict[str, Any]]) -> int:
    existing = load_existing_results()
    added = 0
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a", encoding="utf-8") as fh:
        for row in rows:
            key = result_key(row)
            if key in existing:
                continue
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            existing[key] = row
            added += 1
    return added


def render_report(today: str, rows: list[dict[str, Any]], missing: list[dict[str, Any]], existing_count: int) -> str:
    lines = [
        f"# {today} 公告事件D+自动回填",
        "",
        f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 摘要",
        "",
        "```yaml",
        f"resolved_added: {len(rows)}",
        f"resolved_existing: {existing_count}",
        f"missing_data: {len(missing)}",
        "```",
        "",
        "## 本次回填",
        "",
        "| 到期日 | 节点 | 代码 | 名称 | 公告类型 | 涨跌幅% | 反馈结论 | 处理 | 规律标签 |",
        "|---|---|---|---|---|---:|---|---|---|",
    ]
    if rows:
        for row in sorted(rows, key=lambda x: (x["到期日"], x["股票代码"], x["验证节点"])):
            lines.append(
                f"| {row['到期日']} | {row['验证节点']} | {row['股票代码']} | {row['公司名称']} | {row['公告类型']} | {row['涨跌幅']} | {row['反馈结论']} | {row['处理结论']} | {row['规律标签']} |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - | - |")
    lines += [
        "",
        "## 缺行情",
        "",
        "| 到期日 | 节点 | 代码 | 名称 | 原因 |",
        "|---|---|---|---|---|",
    ]
    if missing:
        for item in missing:
            lines.append(f"| {item.get('到期日','')} | {item.get('验证节点','')} | {item.get('股票代码','')} | {item.get('公司名称','')} | {item.get('原因','')} |")
    else:
        lines.append("| - | - | - | - | - |")
    lines += [
        "",
        "## 使用边界",
        "",
        "- 本页只验证公告后的市场反馈，不产生新的买入建议。",
        "- D+0 强不代表能持续，必须继续看 D+1/D+3/D+5/D+10。",
        "- 一日游、冲高回落、风险公告被忽略，都要沉淀为后续公告评分规则。",
    ]
    return "\n".join(lines) + "\n"


def find_dossier(code: str, name: str) -> Optional[Path]:
    candidates = list(EVENT_DIR.glob(f"{code}-*-公告事件档案.md"))
    if candidates:
        return candidates[0]
    candidates = list(EVENT_DIR.glob(f"*-{name}-公告事件档案.md"))
    return candidates[0] if candidates else None


def append_validation_to_dossiers(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        path = find_dossier(row["股票代码"], row["公司名称"])
        if not path:
            continue
        marker = f"announcement-validation:{row['事件ID']}:{row['验证节点']}"
        text = read_text(path)
        if marker in text:
            continue
        block = (
            f"\n### {row['到期日']} {row['验证节点']}验证\n\n"
            f"<!-- {marker} -->\n\n"
            f"- 涨跌幅：{row['涨跌幅']}%\n"
            f"- 开盘/最高/收盘反馈：{row['开盘反馈']} / {row['最高反馈']} / {row['收盘反馈']}\n"
            f"- 反馈结论：{row['反馈结论']}\n"
            f"- 处理结论：{row['处理结论']}\n"
            f"- 规律标签：{row['规律标签']}\n"
            f"- 证据：{row['证据']}\n"
        )
        path.write_text(text.rstrip() + "\n" + block, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="公告事件D+自动回填")
    parser.add_argument("--today", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--allow-intraday", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now = datetime.now()
    if not args.allow_intraday and not market_closed(now):
        print(json.dumps({"ok": True, "skipped": True, "reason": "15:05前不回填公告D+结果"}, ensure_ascii=False, indent=2))
        return 0

    existing = load_existing_results()
    queue = parse_queue()
    due: list[dict[str, Any]] = []
    for item in queue:
        due.extend(due_nodes(item, args.today, existing))

    by_code: dict[str, list[dict[str, Any]]] = {}
    for item in due:
        by_code.setdefault(item["股票代码"], []).append(item)

    kline_cache: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    for code in sorted(by_code):
        try:
            kline_cache[code] = fetch_kline(code)
        except Exception as exc:
            errors[code] = str(exc)

    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    for item in due:
        bars = kline_cache.get(item["股票代码"], [])
        prev_bar, bar = bar_pair_for_date(bars, item["到期日"])
        if not prev_bar or not bar:
            missing.append({**item, "原因": errors.get(item["股票代码"]) or "缺少到期日或前一交易日日K"})
            continue
        rows.append(build_result(item, prev_bar, bar, generated_at))

    added = 0
    if not args.dry_run:
        added = append_results(rows)
        append_validation_to_dossiers(rows)
        report = render_report(args.today, rows, missing, len(existing))
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        write_json(OUT_DIR / "latest-announcement-dplus-autofill.json", {
            "ok": True,
            "today": args.today,
            "generatedAt": generated_at,
            "dueChecked": len(due),
            "resolved": len(rows),
            "added": added,
            "missing": len(missing),
            "results": rows,
            "missingItems": missing,
        })
        (OUT_DIR / "latest-announcement-dplus-autofill.md").write_text(report, encoding="utf-8")
        (WIKI / "09-统计与进化" / f"{args.today}-公告事件D+自动回填.md").write_text(report, encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "dryRun": args.dry_run,
        "today": args.today,
        "dueChecked": len(due),
        "resolved": len(rows),
        "added": added,
        "missing": len(missing),
        "fetchErrors": errors,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
