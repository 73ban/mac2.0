#!/usr/bin/env python3
"""Register and validate war-room candidates for D+ learning."""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from codex_trading_calendar import add_trade_days


ROOT = Path(__file__).resolve().parents[2]
WIKI_ROOM = ROOT / "wiki" / "07-作战室"
WIKI_STATS = ROOT / "wiki" / "09-统计与进化"
FACTS = ROOT / "data" / "facts"
OUT_DIR = ROOT / ".llm-wiki" / "warroom-validation"
PREDICTIONS = FACTS / "warroom_candidate_predictions.jsonl"
RESULTS = FACTS / "warroom_candidate_validation_results.jsonl"
QUEUE = WIKI_STATS / "作战室候选票D+验证队列.md"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl_unique(path: Path, rows: list[dict[str, Any]], key: str) -> int:
    existing: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            if item.get(key):
                existing.add(str(item[key]))
    added = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            row_key = str(row.get(key) or "")
            if not row_key or row_key in existing:
                continue
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            existing.add(row_key)
            added += 1
    return added


def next_trading_days(date: str, count: int = 6) -> list[str]:
    return [add_trade_days(date, i).isoformat() for i in range(1, count + 1)]


def infer_session(now: datetime | None = None) -> str:
    current = now or datetime.now()
    hhmm = current.hour * 100 + current.minute
    if hhmm < 930:
        return "preopen"
    if hhmm < 1500:
        return "intraday"
    return "postclose"


def normalize_cell(value: str) -> str:
    return value.strip().strip("`").strip()


def parse_score_table(date: str) -> list[dict[str, Any]]:
    path = WIKI_ROOM / f"{date}-作战室候选票评分表.md"
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in read_text(path).splitlines():
        if not line.startswith("|"):
            continue
        cells = [normalize_cell(c) for c in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        if cells[0] in {"排名", "---:---"}:
            continue
        rank, code, name, role, score, permission, condition = cells[:7]
        if not re.fullmatch(r"\d+", rank or "") or not re.fullmatch(r"\d{6}", code or ""):
            continue
        try:
            score_value = float(score)
        except Exception:
            score_value = None
        rows.append(
            {
                "rank": int(rank),
                "code": code,
                "name": name,
                "role": role,
                "score": score_value,
                "permission": permission,
                "condition": condition,
                "sourcePath": str(path.relative_to(ROOT)),
            }
        )
    return rows


def hotlist_map() -> dict[str, dict[str, Any]]:
    payload = read_json(ROOT / ".llm-wiki" / "ths-hotlist" / "latest-ths-hotlist.json", {})
    rows = payload.get("rows") if isinstance(payload, dict) else []
    out: dict[str, dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            code = str(row.get("code") or "").strip()
            if code:
                out[code] = row
    return out


def tencent_quote_map() -> dict[str, dict[str, Any]]:
    payload = read_json(ROOT / ".llm-wiki" / "tencent-market" / "latest-tencent-market.json", {})
    rows = payload.get("stockQuotes") if isinstance(payload, dict) else []
    out: dict[str, dict[str, Any]] = {}
    if isinstance(rows, list):
        for row in rows:
            code = str(row.get("code") or "").strip()
            if code:
                out[code] = row
    return out


def symbol_for(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return f"sh{code}"
    if code.startswith("8"):
        return f"bj{code}"
    return f"sz{code}"


def fetch_tencent_quotes(codes: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for code in codes:
        symbol = symbol_for(code)
        try:
            req = urllib.request.Request(
                f"https://qt.gtimg.cn/q={symbol}",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                raw = response.read().decode("gb18030", errors="ignore")
        except Exception:
            continue
        match = re.search(r'="([^"]*)"', raw)
        if not match:
            continue
        fields = match.group(1).split("~")
        if len(fields) < 35:
            continue
        try:
            price = float(fields[3])
            prev_close = float(fields[4])
            open_price = float(fields[5])
            high = float(fields[33])
            low = float(fields[34])
        except Exception:
            continue
        change = ((price - prev_close) / prev_close * 100) if prev_close else None
        out[code] = {
            "symbol": symbol,
            "code": code,
            "name": fields[1] or "",
            "latestPrice": round(price, 2),
            "prevClose": round(prev_close, 2),
            "openPrice": round(open_price, 2),
            "highPrice": round(high, 2),
            "lowPrice": round(low, 2),
            "changePercent": round(change, 2) if change is not None else None,
            "time": fields[30] if len(fields) > 30 else "",
        }
    return out


def limit_threshold(code: str) -> float:
    if code.startswith(("300", "301", "688")):
        return 19.5
    if code.startswith(("8", "9")):
        return 29.0
    return 9.5


def classify_candidate(candidate: dict[str, Any], hot: dict[str, Any] | None, quote: dict[str, Any] | None) -> dict[str, Any]:
    code = candidate["code"]
    change = None
    rank = None
    amount = ""
    source = []
    if hot:
        rank = hot.get("rank")
        change = hot.get("changePercent")
        amount = str(hot.get("amountText") or "")
        source.append("ths_hotlist")
    if change is None and quote:
        change = quote.get("changePercent")
        source.append("tencent_quote")
    try:
        change_value = float(change)
    except Exception:
        change_value = None
    if change_value is None:
        decision = "待补数据"
        price_action = "无数据"
        relative = "待补行情"
        rule_update = "缺行情时不允许判定作战室选票有效。"
    elif change_value >= limit_threshold(code):
        decision = "加分"
        price_action = "强于预期"
        relative = "热榜/涨停强反馈"
        rule_update = "命中涨停或20cm强反馈，相关题材和候选来源保留加权。"
    elif change_value >= 5:
        decision = "保留观察"
        price_action = "符合预期"
        relative = "有正反馈"
        rule_update = "有弹性但未到涨停，继续看 D+1/D+3 延续。"
    elif change_value >= 0:
        decision = "降权观察"
        price_action = "弱于预期"
        relative = "弱正反馈"
        rule_update = "高分候选只小涨，后续需要降低追高权限。"
    else:
        decision = "扣分"
        price_action = "证伪"
        relative = "负反馈"
        rule_update = "作战室候选 D+0 负反馈，相关来源和模式必须降权。"
    if rank is not None:
        try:
            rank_int = int(rank)
            if rank_int <= 30 and decision in {"加分", "保留观察"}:
                relative = f"热榜Top{rank_int}强反馈"
        except Exception:
            pass
    return {
        "code": code,
        "name": candidate["name"],
        "rank": candidate["rank"],
        "role": candidate["role"],
        "score": candidate.get("score"),
        "permission": candidate.get("permission"),
        "priceAction": price_action,
        "changePercent": change_value,
        "hotRank": rank,
        "amountText": amount,
        "relativeStrength": relative,
        "decision": decision,
        "ruleUpdate": rule_update,
        "dataSources": source,
    }


def build_predictions(date: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    days = next_trading_days(date, 6)
    out: list[dict[str, Any]] = []
    for item in candidates:
        prediction_id = f"warroom:{date}:{item['code']}"
        out.append(
            {
                "schema": "73wiki-warroom-candidate-prediction-v1",
                "predictionId": prediction_id,
                "date": date,
                "code": item["code"],
                "name": item["name"],
                "rank": item["rank"],
                "role": item["role"],
                "score": item.get("score"),
                "permission": item.get("permission"),
                "condition": item.get("condition"),
                "sourcePath": item.get("sourcePath"),
                "validationDates": {
                    "D+1": days[0],
                    "D+3": days[2],
                    "D+5": days[4],
                },
                "status": "active",
            }
        )
    return out


def render_queue(date: str, predictions: list[dict[str, Any]]) -> str:
    existing = ""
    if QUEUE.exists():
        existing = read_text(QUEUE)
    header = "\n".join(
        [
            "# 作战室候选票 D+验证队列",
            "",
            "用途：所有进入作战室评分表的票，必须进入 D+0/D+1/D+3/D+5 验证；不允许只做推荐、不做回看。",
            "",
            "| 入队日 | 代码 | 名称 | 排名 | 角色 | 分数 | 权限 | D+1 | D+3 | D+5 | 状态 |",
            "|---|---|---|---:|---|---:|---|---|---|---|---|",
        ]
    )
    old_rows = []
    if existing:
        old_rows = [line for line in existing.splitlines() if line.startswith("| 20")]
    new_rows = []
    old_keys = set()
    for line in old_rows:
        cells = [normalize_cell(c) for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3:
            old_keys.add(f"{cells[0]}:{cells[1]}")
    for item in predictions:
        key = f"{date}:{item['code']}"
        if key in old_keys:
            continue
        vd = item["validationDates"]
        new_rows.append(
            f"| {date} | {item['code']} | {item['name']} | {item['rank']} | {item['role']} | {item.get('score') if item.get('score') is not None else ''} | {item.get('permission','')} | {vd['D+1']} | {vd['D+3']} | {vd['D+5']} | active |"
        )
    rows = old_rows + new_rows
    return header + "\n" + ("\n".join(rows) if rows else "| - | - | - | - | - | - | - | - | - | - | - |") + "\n"


def render_report(date: str, session: str, validations: list[dict[str, Any]]) -> str:
    lines = [
        f"# {date} 作战室候选验证回看",
        "",
        f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"运行阶段：{session}",
        "",
        "说明：preopen/intraday 是盘中快照，只用于临时调权；postclose 才是正式 D+0 复盘结果。",
        "",
        "## 结论表",
        "",
        "| 排名 | 代码 | 名称 | 分数 | 角色 | 涨跌幅 | 热榜排名 | D+0判断 | 权重处理 |",
        "|---:|---|---|---:|---|---:|---:|---|---|",
    ]
    for item in validations:
        change = "" if item["changePercent"] is None else f"{item['changePercent']:.2f}"
        hot_rank = item["hotRank"] if item["hotRank"] is not None else ""
        score = item["score"] if item["score"] is not None else ""
        lines.append(
            f"| {item['rank']} | {item['code']} | {item['name']} | {score} | {item['role']} | {change} | {hot_rank} | {item['priceAction']} | {item['decision']} |"
        )
    if not validations:
        lines.append("| - | - | - | - | - | - | - | 无候选 | - |")
    lines.extend(
        [
            "",
            "## 规则回写",
            "",
        ]
    )
    for item in validations:
        lines.append(f"- {item['code']} {item['name']}：{item['ruleUpdate']}")
    lines.extend(
        [
            "",
            "## 后续",
            "",
            "- D+1/D+3/D+5 必须继续回看。",
            "- 高分但 D+0/D+1 连续弱反馈的候选来源必须降权。",
            "- 命中涨停/Top30 且 D+1 延续的候选来源才允许升权。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Register and validate war-room candidates.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--session", choices=["preopen", "intraday", "postclose"], default="", help="Validation session. Empty means infer from local time.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    session = args.session or infer_session()
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    candidates = parse_score_table(args.date)
    predictions = build_predictions(args.date, candidates)
    hot = hotlist_map()
    quotes = tencent_quote_map()
    fetched_quotes = fetch_tencent_quotes([item["code"] for item in candidates if item["code"] not in quotes])
    quotes.update(fetched_quotes)
    validations = [
        classify_candidate(item, hot.get(item["code"]), quotes.get(item["code"]))
        for item in candidates
    ]
    result_rows = []
    for item in validations:
        result_rows.append(
            {
                "schema": "73wiki-warroom-candidate-validation-v1",
                "resultId": f"warroom-d0:{args.date}:{session}:{item['code']}",
                "date": args.date,
                "node": f"D+0/{session}",
                "session": session,
                **item,
            }
        )
    payload = {
        "schema": "73wiki-warroom-validation-run-v1",
        "generatedAt": generated_at,
        "date": args.date,
        "session": session,
        "candidateCount": len(candidates),
        "quoteCount": len(quotes),
        "fetchedQuoteCount": len(fetched_quotes),
        "registeredPredictions": len(predictions),
        "validationCount": len(validations),
        "summary": {
            "add": sum(1 for x in validations if x["decision"] == "加分"),
            "keep": sum(1 for x in validations if x["decision"] == "保留观察"),
            "downgradeWatch": sum(1 for x in validations if x["decision"] == "降权观察"),
            "penalty": sum(1 for x in validations if x["decision"] == "扣分"),
            "missingData": sum(1 for x in validations if x["decision"] == "待补数据"),
        },
        "validations": validations,
        "outputs": {
            "json": ".llm-wiki/warroom-validation/latest-warroom-validation.json",
            "md": ".llm-wiki/warroom-validation/latest-warroom-validation.md",
            "wiki": f"wiki/09-统计与进化/{args.date}-作战室候选验证回看.md",
            "queue": str(QUEUE.relative_to(ROOT)),
            "predictions": str(PREDICTIONS.relative_to(ROOT)),
            "results": str(RESULTS.relative_to(ROOT)),
        },
    }
    if not args.dry_run:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        write_json(OUT_DIR / "latest-warroom-validation.json", payload)
        write_json(OUT_DIR / f"{args.date}-warroom-validation.json", payload)
        report = render_report(args.date, session, validations)
        (OUT_DIR / "latest-warroom-validation.md").write_text(report, encoding="utf-8")
        (WIKI_STATS / f"{args.date}-作战室候选验证回看.md").write_text(report, encoding="utf-8")
        QUEUE.write_text(render_queue(args.date, predictions), encoding="utf-8")
        added_predictions = append_jsonl_unique(PREDICTIONS, predictions, "predictionId")
        added_results = append_jsonl_unique(RESULTS, result_rows, "resultId")
    else:
        added_predictions = 0
        added_results = 0
    payload["addedPredictions"] = added_predictions
    payload["addedResults"] = added_results
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
