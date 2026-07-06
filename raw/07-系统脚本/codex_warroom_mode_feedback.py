#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PRED = ROOT / "data/facts/warroom_candidate_predictions.jsonl"
MODE_DPLUS = ROOT / "data/facts/trade_mode_dplus_results.jsonl"
OUT = ROOT / "raw/11-Codex分析产物/作战室模式胜率反馈"
WIKI = ROOT / "wiki/09-统计与进化/作战室Top5-模式胜率反馈.md"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            v = json.loads(line)
        except Exception:
            continue
        if isinstance(v, dict):
            rows.append(v)
    return rows


def ret(row: dict[str, Any], node: str = "D+1") -> float | None:
    try:
        return float(((row.get("nodes") or {}).get(node) or {}).get("close_return_pct"))
    except Exception:
        return None


def mode_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by = defaultdict(list)
    for row in rows:
        by[str(row.get("primary_mode") or "待人工归因")].append(row)
    out = {}
    for mode, items in by.items():
        returns = [ret(x) for x in items]
        returns = [x for x in returns if x is not None]
        out[mode] = {
            "samples": len(items),
            "available": len(returns),
            "hit_rate": round(sum(1 for x in returns if x >= 0) / len(returns) * 100, 2) if returns else None,
            "fail_rate": round(sum(1 for x in returns if x <= -5) / len(returns) * 100, 2) if returns else None,
            "avg_d1": round(sum(returns) / len(returns), 2) if returns else None,
        }
    return out


def pick_mode(row: dict[str, Any]) -> str:
    for key in ("primaryMode", "primary_mode", "mode", "主模式"):
        if row.get(key):
            return str(row[key])
    text = json.dumps(row, ensure_ascii=False)
    for mode in ("趋势主升", "分歧转一致", "前排确认打板", "一字定方向扩散", "主线核心低吸", "断板反包", "龙头战法"):
        if mode in text:
            return mode
    return "待人工归因"


def conclusion(stat: dict[str, Any]) -> str:
    if not stat or stat.get("available", 0) < 3:
        return "样本不足，只作为提示"
    avg = stat.get("avg_d1")
    hit = stat.get("hit_rate")
    fail = stat.get("fail_rate")
    if avg is not None and avg >= 3 and hit is not None and hit >= 55:
        return "历史正反馈，允许升权但仍看盘口确认"
    if avg is not None and avg <= -3 or (fail is not None and fail >= 35):
        return "历史负反馈，必须降低无确认买点权限"
    return "历史中性，重点看当日强度"


def main() -> int:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stats = mode_stats(read_jsonl(MODE_DPLUS))
    preds = read_jsonl(PRED)[-80:]
    rows = []
    for row in reversed(preds[-30:]):
        mode = pick_mode(row)
        stat = stats.get(mode, {})
        rows.append({
            "date": row.get("date") or row.get("predictionDate") or "",
            "code": row.get("code") or row.get("股票代码") or "",
            "name": row.get("name") or row.get("股票名称") or "",
            "mode": mode,
            "score": row.get("score") or row.get("dynamicScore") or row.get("分数") or "",
            "stat": stat,
            "conclusion": conclusion(stat),
        })
    today = datetime.now().strftime("%Y-%m-%d")
    payload = {"schema": "73wiki-warroom-mode-feedback-v1", "generatedAt": generated_at, "rows": rows, "modeStats": stats}
    OUT.joinpath(today).mkdir(parents=True, exist_ok=True)
    (OUT / today / "warroom-mode-feedback.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 作战室Top5-模式胜率反馈",
        "",
        f"- 生成时间：{generated_at}",
        "- 用途：给作战室候选票附加历史同类模式D+反馈，防止只按热度排序。",
        "",
        "## 最近作战室候选",
        "",
        "| 日期 | 股票 | 模式 | 分数 | 历史样本 | D+1命中 | D+1失败 | D+1均值 | 结论 |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        st = row["stat"] or {}
        lines.append(
            f"| {row['date']} | {row['name']} {row['code']} | {row['mode']} | {row['score']} | "
            f"{st.get('available', 0)} | {st.get('hit_rate', '待数据')} | {st.get('fail_rate', '待数据')} | {st.get('avg_d1', '待数据')} | {row['conclusion']} |"
        )
    lines += ["", "## 模式胜率底表", "", "| 模式 | 样本 | 可算 | D+1命中 | D+1失败 | D+1均值 |", "|---|---:|---:|---:|---:|---:|"]
    for mode, st in sorted(stats.items(), key=lambda kv: kv[1].get("available", 0), reverse=True):
        lines.append(f"| {mode} | {st['samples']} | {st['available']} | {st['hit_rate']} | {st['fail_rate']} | {st['avg_d1']} |")
    md = "\n".join(lines) + "\n"
    (OUT / today / "warroom-mode-feedback.md").write_text(md, encoding="utf-8")
    WIKI.write_text(md, encoding="utf-8")
    print(json.dumps({"ok": True, "rows": len(rows), "output": str(WIKI.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
