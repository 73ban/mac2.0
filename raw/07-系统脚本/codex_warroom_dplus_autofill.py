#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Autofill D+1/D+3/D+5 results for war-room candidates."""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FACTS = ROOT / "data/facts"
PREDICTIONS = FACTS / "warroom_candidate_predictions.jsonl"
RESULTS = FACTS / "warroom_candidate_dplus_validation_results.jsonl"
OUT_DIR = ROOT / ".llm-wiki/warroom-dplus-autofill"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
BOARD_DIR = ROOT / "raw/04-市场数据/板块强度"
STOCK_BOARD_DIR = ROOT / "raw/04-市场数据/板块成分股"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def append_jsonl_unique(path: Path, rows: list[dict[str, Any]], key: str) -> int:
    existing = {str(item.get(key) or "") for item in read_jsonl(path)}
    path.parent.mkdir(parents=True, exist_ok=True)
    added = 0
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            row_key = str(row.get(key) or "")
            if not row_key or row_key in existing:
                continue
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            existing.add(row_key)
            added += 1
    return added


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def normalize_code(value: Any) -> str:
    text = re.sub(r"\D", "", str(value or ""))
    return text[-6:].zfill(6) if text else ""


def symbol_for(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    if code.startswith("8"):
        return f"bj{code}"
    return f"sz{code}"


def fetch_kline(symbol: str, days: int = 80) -> list[dict[str, Any]]:
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,{days},qfq"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    rows = payload.get("data", {}).get(symbol, {}).get("qfqday") or payload.get("data", {}).get(symbol, {}).get("day") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            out.append({"date": str(row[0]), "close": float(row[2]), "high": float(row[3]), "low": float(row[4])})
        except Exception:
            continue
    return out


def pct_for_date(bars: list[dict[str, Any]], day: str) -> tuple[float | None, dict[str, Any] | None]:
    for idx, bar in enumerate(bars):
        if bar.get("date") != day or idx == 0:
            continue
        prev_close = float(bars[idx - 1]["close"])
        close = float(bar["close"])
        return (round((close - prev_close) / prev_close * 100, 2), bar) if prev_close else (None, bar)
    return None, None


def number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace("%", "").replace("+", "").strip())
    except Exception:
        return None


def latest_daily_file(base: Path, day: str, names: list[str]) -> Path | None:
    if not base.exists():
        return None
    candidates = []
    for date_dir in sorted(base.iterdir()):
        if not date_dir.is_dir() or date_dir.name > day:
            continue
        for name in names:
            path = date_dir / name
            if path.exists():
                candidates.append(path)
    return candidates[-1] if candidates else None


def board_rows_for(day: str) -> dict[str, dict[str, Any]]:
    path = latest_daily_file(BOARD_DIR, day, ["tdx-board-strength.json", "通达信板块强度.json"])
    payload = read_json(path, {}) if path else {}
    rows = []
    if isinstance(payload, dict):
        rows.extend(payload.get("涨幅Top10") or payload.get("涨幅前十") or [])
        rows.extend(payload.get("跌幅Top10") or payload.get("跌幅前十") or [])
        rows.extend(payload.get("涨幅Top100全量") if isinstance(payload.get("涨幅Top100全量"), list) else [])
        rows.extend(payload.get("跌幅Top30全量") if isinstance(payload.get("跌幅Top30全量"), list) else [])
        rows.extend(payload.get("板块列表") or payload.get("主线板块") or [])
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("名称") or row.get("板块名称") or row.get("name") or "").strip()
        if not name:
            continue
        out[name] = {
            "name": name,
            "code": str(row.get("代码") or row.get("板块代码") or row.get("code") or ""),
            "rank": row.get("排名") or row.get("板块排名") or "",
            "changePercent": number(row.get("涨跌幅")),
            "source": str(path.relative_to(ROOT)) if path else "",
        }
    return out


def stock_boards_for(code: str, day: str) -> dict[str, Any]:
    path = latest_daily_file(STOCK_BOARD_DIR, day, ["tdx-stock-boards.json"])
    payload = read_json(path, {}) if path else {}
    mapping = payload.get("股票板块", {}) if isinstance(payload, dict) else {}
    item = mapping.get(code, {}) if isinstance(mapping, dict) else {}
    boards = item.get("板块", []) if isinstance(item, dict) else []
    return {"boards": boards if isinstance(boards, list) else [], "source": str(path.relative_to(ROOT)) if path else ""}


def board_strength_for(code: str, day: str, change: float | None) -> dict[str, Any]:
    stock_board = stock_boards_for(code, day)
    strength = board_rows_for(day)
    matched = []
    for name in stock_board["boards"]:
        row = strength.get(str(name))
        if row:
            matched.append(row)
    matched.sort(key=lambda row: (row.get("changePercent") is None, -(row.get("changePercent") or -9999)))
    best = matched[0] if matched else {}
    board_change = best.get("changePercent")
    relative = round(change - board_change, 2) if change is not None and board_change is not None else None
    if not stock_board["boards"]:
        label = "缺板块成分股映射"
    elif not matched:
        label = "所属板块未进入当日强弱榜"
    else:
        label = f"{best.get('name')} {board_change}%"
    return {
        "boardStrength": label,
        "boardName": best.get("name", ""),
        "boardCode": best.get("code", ""),
        "boardRank": best.get("rank", ""),
        "boardChangePercent": board_change,
        "relativeToBoard": relative,
        "beatBoard": bool(relative is not None and relative > 0),
        "boardSources": [x for x in [stock_board.get("source"), best.get("source")] if x],
    }


def market_closed(now: datetime) -> bool:
    return now.hour > 15 or (now.hour == 15 and now.minute >= 5)


def classify(change: float | None, relative_sh: float | None) -> tuple[str, str, str]:
    if change is None:
        return "待补数据", "待补行情", "行情缺失，保留待回填，不做权重变化。"
    if change >= 9.5:
        return "强于预判", "加分", "D+命中涨停级反馈，候选来源和题材逻辑保留加权。"
    if relative_sh is not None and relative_sh >= 3 and change >= 3:
        return "跑赢大盘", "保留观察", "D+明显跑赢大盘但未涨停，继续看延续性。"
    if change >= 0:
        return "弱兑现", "降权观察", "D+正反馈偏弱，高分候选不得提高追涨权限。"
    if relative_sh is not None and relative_sh < 0:
        return "未跑赢大盘", "扣分", "D+弱于大盘，相关模式和消息来源降权。"
    return "负反馈", "扣分", "D+下跌，进入失败样本复盘。"


def due_predictions(today: str, existing_ids: set[str]) -> list[tuple[dict[str, Any], str, str]]:
    due: list[tuple[dict[str, Any], str, str]] = []
    for item in read_jsonl(PREDICTIONS):
        dates = item.get("validationDates", {})
        if not isinstance(dates, dict):
            continue
        code = normalize_code(item.get("code"))
        if not code:
            continue
        for node in ("D+1", "D+3", "D+5"):
            due_date = str(dates.get(node) or "")
            if not due_date or due_date > today:
                continue
            result_id = f"warroom-dplus:{item.get('date')}:{code}:{node}:{due_date}"
            if result_id in existing_ids:
                continue
            due.append((item, node, due_date))
    return due


def build_rows(today: str) -> tuple[list[dict[str, Any]], list[str]]:
    existing_ids = {str(item.get("resultId") or "") for item in read_jsonl(RESULTS)}
    due = due_predictions(today, existing_ids)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    benchmark_bars: list[dict[str, Any]] = []
    try:
        benchmark_bars = fetch_kline("sh000001")
    except Exception as error:
        errors.append(f"benchmark sh000001: {error}")

    cache: dict[str, list[dict[str, Any]]] = {}
    for prediction, node, due_date in due:
        code = normalize_code(prediction.get("code"))
        symbol = symbol_for(code)
        if symbol not in cache:
            try:
                cache[symbol] = fetch_kline(symbol)
            except Exception as error:
                errors.append(f"{code}: {error}")
                cache[symbol] = []
        change, bar = pct_for_date(cache[symbol], due_date)
        sh_change, _ = pct_for_date(benchmark_bars, due_date) if benchmark_bars else (None, None)
        relative_sh = round(change - sh_change, 2) if change is not None and sh_change is not None else None
        board = board_strength_for(code, due_date, change)
        price_action, decision, rule_update = classify(change, relative_sh)
        rows.append(
            {
                "schema": "73wiki-warroom-candidate-dplus-validation-v1",
                "resultId": f"warroom-dplus:{prediction.get('date')}:{code}:{node}:{due_date}",
                "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sourceDate": prediction.get("date"),
                "date": due_date,
                "node": node,
                "code": code,
                "name": prediction.get("name", ""),
                "rank": prediction.get("rank"),
                "role": prediction.get("role", ""),
                "score": prediction.get("score"),
                "permission": prediction.get("permission", ""),
                "condition": prediction.get("condition", ""),
                "changePercent": change,
                "benchmarkSH": sh_change,
                "relativeToSH": relative_sh,
                "beatMarket": bool(relative_sh is not None and relative_sh > 0),
                **board,
                "followedPrediction": price_action in {"强于预判", "跑赢大盘"},
                "priceAction": price_action,
                "decision": decision,
                "ruleUpdate": rule_update,
                "evidence": [
                    f"腾讯复权日K {symbol} {due_date} 涨跌幅={change}%",
                    f"上证指数 {due_date} 涨跌幅={sh_change}%",
                ],
                "dataSources": ["tencent_qfqday_kline", "sh000001_benchmark", *board.get("boardSources", [])],
                "status": "resolved" if change is not None else "pending",
            }
        )
    return rows, errors


def render_report(today: str, rows: list[dict[str, Any]], errors: list[str]) -> str:
    lines = [
        f"# {today} 作战室候选票 D+自动回填",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 回填条数：{len(rows)}",
        "",
        "| 来源日 | 节点 | 代码 | 名称 | 涨跌幅 | 上证 | 板块 | 跑赢板块 | 结论 | 权重处理 |",
        "|---|---|---|---|---:|---:|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('sourceDate')} | {row.get('node')} | {row.get('code')} | {row.get('name')} | {row.get('changePercent', '')} | {row.get('benchmarkSH', '')} | {row.get('boardStrength', '')} | {row.get('beatBoard')} | {row.get('priceAction')} | {row.get('decision')} |"
        )
    if not rows:
        lines.append("| - | - | - | - | - | - | - | 今日无到期项 | - |")
    lines.extend(["", "## 规则回写", ""])
    for row in rows:
        lines.append(f"- {row.get('code')} {row.get('name')}：{row.get('ruleUpdate')}")
    if errors:
        lines.extend(["", "## 数据缺口", ""])
        lines.extend(f"- {item}" for item in errors[:30])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="作战室候选票 D+自动回填")
    parser.add_argument("--today", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--allow-intraday", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.allow_intraday and not market_closed(datetime.now()):
        print(json.dumps({"ok": False, "reason": "未到15:05，不回填作战室D+结论", "today": args.today}, ensure_ascii=False, indent=2))
        return 0

    rows, errors = build_rows(args.today)
    added = 0
    if not args.dry_run:
        added = append_jsonl_unique(RESULTS, rows, "resultId")
        payload = {"date": args.today, "rows": rows, "errors": errors, "added": added}
        write_json(OUT_DIR / f"{args.today}-warroom-dplus-autofill.json", payload)
        write_json(OUT_DIR / "latest-warroom-dplus-autofill.json", payload)
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / f"{args.today}-作战室候选票D+自动回填.md").write_text(render_report(args.today, rows, errors), encoding="utf-8")

    with_board = sum(1 for row in rows if row.get("boardName"))
    with_board_strength = sum(1 for row in rows if row.get("boardStrength"))
    beat_board = sum(1 for row in rows if row.get("beatBoard") is True)
    print(json.dumps({
        "ok": True,
        "today": args.today,
        "due": len(rows),
        "added": added,
        "withBoard": with_board,
        "withBoardStrength": with_board_strength,
        "beatBoard": beat_board,
        "errors": errors[:10],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
