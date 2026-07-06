#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Summarize dynamic warroom learning signals for continuous evolution."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_OUT = ROOT / "raw/11-Codex分析产物/动态作战室"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
SYSTEM = ROOT / ".system"
PREDICTIONS = ROOT / "data/facts/warroom_candidate_predictions.jsonl"
D0_RESULTS = ROOT / "data/facts/warroom_candidate_validation_results.jsonl"
DPLUS_RESULTS = ROOT / "data/facts/warroom_candidate_dplus_validation_results.jsonl"
CALIBRATION = ROOT / "data/facts/feishu_calibration_events.jsonl"
VERSIONS = ROOT / "data/facts/warroom_dynamic_versions.jsonl"
CHANGES = ROOT / "data/facts/warroom_dynamic_change_events.jsonl"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def clean(value: Any, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().replace("|", "/")[:limit]


def factor_tags(row: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            row.get("entryReason") or "",
            row.get("role") or "",
            row.get("permission") or "",
            row.get("condition") or "",
            " ".join(row.get("verifyBasis") or []),
        ]
    )
    tags = []
    for key in ("持仓", "三榜", "热榜", "竞价", "板块扩散", "涨停", "风险复核", "消息", "实盘赛", "机器人", "半导体", "算力", "存储"):
        if key in text:
            tags.append(key)
    return tags or ["未分类"]


def build(date: str) -> dict[str, Any]:
    current = read_json(RAW_OUT / date / "dynamic-warroom-top5.json", {})
    current_change = current.get("change") or {}
    if not any(current_change.get(key) for key in ("addedDetail", "removedDetail", "rankChanges")):
        signature = current.get("signature")
        for row in reversed(iter_jsonl(CHANGES)):
            if row.get("date") == date and row.get("signature") == signature:
                current_change = row.get("change") or {}
                break
    predictions = [row for row in iter_jsonl(PREDICTIONS) if str(row.get("predictionId", "")).startswith("dynamic-warroom:")]
    today_predictions = [row for row in predictions if row.get("date") == date]
    results = [*iter_jsonl(D0_RESULTS), *iter_jsonl(DPLUS_RESULTS)]
    calibrations = iter_jsonl(CALIBRATION)
    today_calibrations = [row for row in calibrations if (row.get("trade_date") or row.get("date") or str(row.get("created_at", ""))[:10]) == date]

    by_prediction = {(row.get("date"), row.get("code")): row for row in predictions}
    matched_results = []
    for result in results:
        key = (result.get("sourceDate") or result.get("date"), result.get("code"))
        if key in by_prediction:
            matched_results.append({**result, "prediction": by_prediction[key]})

    factor_score: dict[str, int] = defaultdict(int)
    factor_detail: dict[str, list[str]] = defaultdict(list)
    for result in matched_results[-200:]:
        prediction = result.get("prediction") or {}
        decision = result.get("decision") or ""
        delta = 2 if decision == "加分" else 1 if decision == "保留观察" else -1 if decision == "降权观察" else -2 if decision == "扣分" else 0
        for tag in factor_tags(prediction):
            factor_score[tag] += delta
            if len(factor_detail[tag]) < 5:
                factor_detail[tag].append(f"{prediction.get('name') or prediction.get('code')} {decision}")

    calibration_summary = Counter()
    for row in today_calibrations:
        judgement = row.get("user_judgement") or row.get("action") or ""
        calibration_summary[judgement] += 1

    suggestions = []
    for tag, score in sorted(factor_score.items(), key=lambda item: item[1]):
        if score <= -3:
            suggestions.append({"factor": tag, "action": "降权", "reason": "近期动态作战室D+反馈偏弱", "examples": factor_detail[tag]})
    for tag, score in sorted(factor_score.items(), key=lambda item: item[1], reverse=True):
        if score >= 3:
            suggestions.append({"factor": tag, "action": "保留/升权", "reason": "近期动态作战室D+反馈较好", "examples": factor_detail[tag]})

    return {
        "schema": "73wiki-dynamic-warroom-evolution-v1",
        "date": date,
        "generatedAt": now_text(),
        "currentTop5": current.get("top5") or [],
        "currentChange": current_change,
        "todayPredictionCount": len(today_predictions),
        "matchedValidationCount": len(matched_results),
        "todayCalibrationSummary": dict(calibration_summary),
        "factorScores": dict(sorted(factor_score.items(), key=lambda item: item[0])),
        "factorSuggestions": suggestions[:12],
        "pendingValidation": [
            {
                "code": row.get("code"),
                "name": row.get("name"),
                "rank": row.get("rank"),
                "entryReason": row.get("entryReason"),
                "validationDates": row.get("validationDates"),
            }
            for row in today_predictions[-10:]
        ],
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 动态作战室进化日报",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 今日动态预测入账：{payload['todayPredictionCount']}",
        f"- 已匹配历史验证：{payload['matchedValidationCount']}",
        f"- 今日飞书校准：{payload['todayCalibrationSummary'] or {}}",
        "",
        "## 当前Top5",
        "",
        "| 排名 | 股票 | 分数 | 入选原因 | 验证依据 |",
        "|---:|---|---:|---|---|",
    ]
    for row in payload["currentTop5"]:
        lines.append(f"| {row.get('rank')} | {row.get('name') or row.get('code')} {row.get('code')} | {row.get('score')} | {clean(row.get('entryReason'), 120)} | {clean('；'.join(row.get('verifyBasis') or []), 120)} |")
    if not payload["currentTop5"]:
        lines.append("| - | 无 | - | - | - |")

    lines.extend(["", "## 本次变化", ""])
    change = payload.get("currentChange") or {}
    if not any(change.get(key) for key in ("addedDetail", "removedDetail", "rankChanges")):
        lines.append("- 暂无变化。")
    for item in change.get("addedDetail") or []:
        lines.append(f"- 调入：{item.get('name') or item.get('code')} {item.get('code')}，{item.get('reason')}")
    for item in change.get("removedDetail") or []:
        lines.append(f"- 调出：{item.get('name') or item.get('code')} {item.get('code')}，{item.get('reason')}")
    for item in change.get("rankChanges") or []:
        lines.append(f"- 排名变化：{item.get('code')}，{item.get('reason')}")

    lines.extend(["", "## 权重建议", "", "| 因子 | 动作 | 原因 | 样本 |", "|---|---|---|---|"])
    for item in payload["factorSuggestions"]:
        lines.append(f"| {item['factor']} | {item['action']} | {item['reason']} | {'；'.join(item.get('examples') or [])} |")
    if not payload["factorSuggestions"]:
        lines.append("| - | 暂无 | 等更多D+验证 | - |")

    lines.extend(["", "## 待验证", "", "| 股票 | 排名 | 入选原因 | D+节点 |", "|---|---:|---|---|"])
    for row in payload["pendingValidation"]:
        lines.append(f"| {row.get('name') or row.get('code')} {row.get('code')} | {row.get('rank')} | {clean(row.get('entryReason'), 120)} | {row.get('validationDates')} |")
    if not payload["pendingValidation"]:
        lines.append("| - | - | 无 | - |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="动态作战室进化日报")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    if args.write:
        out = RAW_OUT / args.date
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / "dynamic-warroom-evolution.json", payload)
        (out / "dynamic-warroom-evolution.md").write_text(render(payload), encoding="utf-8")
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / f"{args.date}-动态作战室进化日报.md").write_text(render(payload), encoding="utf-8")
        write_json(SYSTEM / "dynamic-warroom-evolution.json", payload)
    print(json.dumps({"ok": True, "date": args.date, "todayPredictionCount": payload["todayPredictionCount"], "suggestions": len(payload["factorSuggestions"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
