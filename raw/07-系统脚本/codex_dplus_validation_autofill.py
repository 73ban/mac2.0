#!/usr/bin/env python3
"""Autofill D+ validation results with post-market Tencent K-line facts.

The script is intentionally conservative:
- it only finalizes due items at or after 15:05 local time, unless --allow-intraday is used;
- it only writes a result when the exact due-date daily bar and previous bar are available;
- missing data remains pending so it can be reviewed manually.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DUE_JSON = ROOT / "data/facts/dplus_due_tasks.json"
RESULTS_JSONL = ROOT / "data/facts/dplus_validation_results.jsonl"
OUT_DIR = ROOT / ".llm-wiki/dplus-validation-autofill"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
OVERVIEW_SCRIPT = ROOT / "raw/07-系统脚本/codex_generate_dplus_tasks.py"


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_code(value: Any) -> str:
    text = re.sub(r"\D", "", str(value or ""))
    return text[-6:].zfill(6) if text else ""


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


def result_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("date", "")),
        normalize_code(item.get("code")),
        str(item.get("node", "")),
    )


def load_existing_results() -> dict[tuple[str, str, str], dict[str, Any]]:
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    if not RESULTS_JSONL.exists():
        return out
    for line in RESULTS_JSONL.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = result_key(item)
        if all(key):
            out[key] = item
    return out


def due_items(today: str, existing: dict[tuple[str, str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    data = read_json(DUE_JSON, {"dates": {}})
    dates = data.get("dates", {}) if isinstance(data, dict) else {}
    out: list[dict[str, Any]] = []
    for due_date, tasks in sorted(dates.items()):
        if due_date > today or not isinstance(tasks, list):
            continue
        for raw in tasks:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            item["date"] = str(item.get("date") or due_date)
            item["code"] = normalize_code(item.get("code"))
            item["node"] = str(item.get("node") or "/".join(item.get("nodes") or []))
            if not item["code"] or not item["node"]:
                continue
            if result_key(item) in existing or item.get("status") == "resolved":
                continue
            out.append(item)
    return out


def existing_due_results(today: str, existing: dict[tuple[str, str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    data = read_json(DUE_JSON, {"dates": {}})
    dates = data.get("dates", {}) if isinstance(data, dict) else {}
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for due_date, tasks in sorted(dates.items()):
        if due_date > today or not isinstance(tasks, list):
            continue
        for raw in tasks:
            if not isinstance(raw, dict):
                continue
            key = (
                str(raw.get("date") or due_date),
                normalize_code(raw.get("code")),
                str(raw.get("node") or "/".join(raw.get("nodes") or [])),
            )
            if key in seen:
                continue
            result = existing.get(key)
            if result:
                out.append(result)
                seen.add(key)
    return out


def fetch_kline(code: str, days: int = 12) -> list[dict[str, Any]]:
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


def bar_pair_for_date(bars: list[dict[str, Any]], due_date: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    for idx, bar in enumerate(bars):
        if bar.get("date") == due_date:
            prev = bars[idx - 1] if idx > 0 else None
            return prev, bar
    return None, None


def classify(code: str, pct: float, close: float, prev_close: float, high: float, low: float) -> dict[str, str]:
    threshold = limit_threshold(code)
    intraday_range = ((high - low) / prev_close * 100) if prev_close else 0.0
    close_position = ((close - low) / (high - low)) if high > low else 1.0

    if pct >= threshold:
        return {
            "priceAction": "强于预期",
            "themeAction": "主线强化",
            "relativeStrength": "涨停/强趋势反馈",
            "volumeAction": "强势封板或接近涨停",
            "decision": "升级",
            "ruleUpdate": "D+验证出现涨停级反馈，相关题材、候选来源和模式条件保留加权。",
        }
    if pct >= 5:
        return {
            "priceAction": "符合预期",
            "themeAction": "主线延续",
            "relativeStrength": "有弹性正反馈",
            "volumeAction": "放量承接" if intraday_range >= 8 else "缩量强势",
            "decision": "保留观察",
            "ruleUpdate": "D+验证有正反馈但未到涨停，继续观察延续性，不直接升权。",
        }
    if pct >= 0:
        return {
            "priceAction": "弱于预期",
            "themeAction": "分歧修复" if close_position >= 0.55 else "轮动",
            "relativeStrength": "弱正反馈",
            "volumeAction": "放量滞涨" if intraday_range >= 8 else "缩量弱修复",
            "decision": "降级观察",
            "ruleUpdate": "D+验证仅小幅正反馈，高分候选不得提高追涨权限。",
        }
    if pct > -5:
        return {
            "priceAction": "弱于预期",
            "themeAction": "分歧",
            "relativeStrength": "弱于核心预期",
            "volumeAction": "缩量走弱" if intraday_range < 8 else "放量分歧",
            "decision": "降级",
            "ruleUpdate": "D+验证负反馈，相关候选来源和追高权限需要降权。",
        }
    return {
        "priceAction": "证伪",
        "themeAction": "退潮",
        "relativeStrength": "明显弱于预期",
        "volumeAction": "放量下跌/强分歧" if intraday_range >= 8 else "缩量走弱",
        "decision": "归档",
        "ruleUpdate": "D+验证大幅负反馈，必须降低自动核心池权重，并纳入失败样本复盘。",
    }


def build_result(item: dict[str, Any], prev_bar: dict[str, Any], bar: dict[str, Any], generated_at: str) -> dict[str, Any]:
    prev_close = float(prev_bar["close"])
    close = float(bar["close"])
    pct = ((close - prev_close) / prev_close * 100) if prev_close else 0.0
    verdict = classify(
        item["code"],
        pct,
        close,
        prev_close,
        float(bar["high"]),
        float(bar["low"]),
    )
    return {
        "schema": "73wiki-dplus-validation-v1",
        "resultId": f"dplus:{item['date']}:{item['code']}:{item['node']}",
        "generatedAt": generated_at,
        "date": item["date"],
        "code": item["code"],
        "name": item.get("name", ""),
        "node": item["node"],
        "evidenceDate": item.get("evidenceDate", ""),
        "role": item.get("role", ""),
        "changePercent": round(pct, 2),
        "close": round(close, 2),
        "prevClose": round(prev_close, 2),
        "high": round(float(bar["high"]), 2),
        "low": round(float(bar["low"]), 2),
        **verdict,
        "evidence": [
            f"腾讯复权日K {item['date']} close={close:.2f} prev_close={prev_close:.2f} pct={pct:.2f}%",
            f"source=symbol:{symbol_for(item['code'])}",
        ],
        "dataSources": ["tencent_qfqday_kline"],
        "status": "resolved",
    }


def append_results(rows: list[dict[str, Any]]) -> int:
    existing = load_existing_results()
    added = 0
    RESULTS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_JSONL.open("a", encoding="utf-8") as fh:
        for row in rows:
            key = result_key(row)
            if key in existing:
                continue
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            existing[key] = row
            added += 1
    return added


def update_due_status(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    data = read_json(DUE_JSON, {"version": 1, "dates": {}})
    dates = data.get("dates", {}) if isinstance(data, dict) else {}
    result_map = {result_key(row): row for row in rows}
    for due_date, tasks in dates.items():
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            key = (str(task.get("date") or due_date), normalize_code(task.get("code")), str(task.get("node") or ""))
            row = result_map.get(key)
            if not row:
                continue
            task["status"] = "resolved"
            task["result"] = row.get("priceAction")
            task["decision"] = row.get("decision")
            task["changePercent"] = row.get("changePercent")
    write_json(DUE_JSON, data)


def render_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| - | - | - | - | - | - | - |"
    lines = []
    for row in sorted(rows, key=lambda x: (x.get("date", ""), x.get("code", ""))):
        lines.append(
            f"| {row.get('date','')} | {row.get('code','')} | {row.get('name','')} | {row.get('node','')} | {row.get('changePercent','')} | {row.get('priceAction','')} | {row.get('decision','')} |"
        )
    return "\n".join(lines)


def render_report(
    today: str,
    rows: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
) -> str:
    display_rows = rows if rows else existing_rows
    missing_rows = "\n".join(
        f"| {item.get('date','')} | {item.get('code','')} | {item.get('name','')} | {item.get('node','')} | {item.get('reason','缺行情')} |"
        for item in missing
    ) or "| - | - | - | - | - |"
    return f"""# {today} D+验证自动回填

更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 摘要

```yaml
resolved_added: {len(rows)}
resolved_existing_due: {len(existing_rows)}
missing_data: {len(missing)}
```

## 已回填

| 到期日 | 代码 | 名称 | 节点 | 涨跌幅% | 结论 | 处理 |
|---|---|---|---|---:|---|---|
{render_rows(display_rows)}

## 缺行情

| 到期日 | 代码 | 名称 | 节点 | 原因 |
|---|---|---|---|---|
{missing_rows}

## 原则

- 只使用到期日的日 K 事实，不用错日期替代。
- 拿不到精确日 K 的任务继续保留待回填。
- 回填结果服务于模式权重修正，不作为新的买入建议。
"""


def upsert_task_page_section(date: str, rows: list[dict[str, Any]]) -> None:
    path = WIKI_STATS / f"{date}-D+验证任务.md"
    if not path.exists():
        return
    page_rows = [row for row in rows if row.get("date") == date]
    if not page_rows:
        return
    text = path.read_text(encoding="utf-8", errors="ignore")
    section = "\n## 自动回填结果\n\n| 代码 | 名称 | 节点 | 涨跌幅% | 结论 | 处理 | 证据 |\n|---|---|---|---:|---|---|---|\n"
    section += "\n".join(
        f"| {row.get('code','')} | {row.get('name','')} | {row.get('node','')} | {row.get('changePercent','')} | {row.get('priceAction','')} | {row.get('decision','')} | {row.get('evidence', [''])[0]} |"
        for row in sorted(page_rows, key=lambda x: x.get("code", ""))
    )
    section += "\n"
    if "\n## 自动回填结果\n" in text:
        text = re.sub(r"\n## 自动回填结果\n.*?(?=\n## 回写要求\n|\Z)", section + "\n", text, flags=re.S)
    elif "\n## 回写要求\n" in text:
        text = text.replace("\n## 回写要求\n", section + "\n## 回写要求\n")
    else:
        text = text.rstrip() + "\n" + section
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--allow-intraday", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now = datetime.now()
    if not args.allow_intraday and not market_closed(now):
        payload = {
            "schema": "73wiki-dplus-validation-autofill-run-v1",
            "ok": True,
            "skipped": True,
            "skipReason": "before_post_market_window",
            "today": args.today,
            "now": now.strftime("%Y-%m-%d %H:%M:%S"),
            "message": "15:05 前不自动写 D+验证结论。",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    existing = load_existing_results()
    pending = due_items(args.today, existing)
    existing_rows = existing_due_results(args.today, existing)
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    by_code: dict[str, list[dict[str, Any]]] = {}
    for item in pending:
        by_code.setdefault(item["code"], []).append(item)

    kline_cache: dict[str, list[dict[str, Any]]] = {}
    fetch_errors: dict[str, str] = {}
    for code in sorted(by_code):
        try:
            kline_cache[code] = fetch_kline(code)
        except Exception as error:
            fetch_errors[code] = str(error)

    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for item in pending:
        bars = kline_cache.get(item["code"], [])
        prev_bar, bar = bar_pair_for_date(bars, item["date"])
        if not prev_bar or not bar:
            missing.append({**item, "reason": fetch_errors.get(item["code"]) or "缺少到期日或前一交易日日K"})
            continue
        rows.append(build_result(item, prev_bar, bar, generated_at))

    added = 0 if args.dry_run else append_results(rows)
    if not args.dry_run:
        update_due_status(rows)
        for due_date in sorted({row["date"] for row in rows}):
            upsert_task_page_section(due_date, rows)
        report = render_report(args.today, rows, missing, existing_rows)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        write_json(OUT_DIR / "latest-dplus-validation-autofill.json", {
            "schema": "73wiki-dplus-validation-autofill-run-v1",
            "ok": True,
            "skipped": False,
            "today": args.today,
            "generatedAt": generated_at,
            "pendingChecked": len(pending),
            "resolved": len(rows),
            "added": added,
            "existingResolvedDue": len(existing_rows),
            "missing": len(missing),
            "missingItems": missing,
            "results": rows,
            "existingResults": existing_rows,
        })
        (OUT_DIR / "latest-dplus-validation-autofill.md").write_text(report, encoding="utf-8")
        (OUT_DIR / f"{args.today}-dplus-validation-autofill.md").write_text(report, encoding="utf-8")
        (WIKI_STATS / f"{args.today}-D+验证自动回填.md").write_text(report, encoding="utf-8")

    payload = {
        "schema": "73wiki-dplus-validation-autofill-run-v1",
        "ok": True,
        "skipped": False,
        "dryRun": args.dry_run,
        "today": args.today,
        "generatedAt": generated_at,
        "pendingChecked": len(pending),
        "resolved": len(rows),
        "added": added,
        "existingResolvedDue": len(existing_rows),
        "missing": len(missing),
        "fetchErrors": fetch_errors,
        "outputs": {
            "json": ".llm-wiki/dplus-validation-autofill/latest-dplus-validation-autofill.json",
            "md": ".llm-wiki/dplus-validation-autofill/latest-dplus-validation-autofill.md",
            "wiki": f"wiki/09-统计与进化/{args.today}-D+验证自动回填.md",
            "results": "data/facts/dplus_validation_results.jsonl",
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
