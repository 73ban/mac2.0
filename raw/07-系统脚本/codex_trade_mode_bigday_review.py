#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DPLUS = ROOT / "data/facts/trade_mode_dplus_results.jsonl"
OUT_DIR = ROOT / f"raw/11-Codex分析产物/交易模式大赚大亏日归因/{date.today().isoformat()}"
WIKI_OUT = ROOT / f"wiki/09-统计与进化/{date.today().isoformat()}-大赚大亏日模式归因.md"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def node_return(row: dict[str, Any], node: str = "D+1") -> float | None:
    value = (((row.get("nodes") or {}).get(node) or {}).get("close_return_pct"))
    return value if isinstance(value, (int, float)) else None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[str(row.get("date") or "")].append(row)
    days = []
    for d, items in sorted(by_date.items()):
        d1 = [node_return(row, "D+1") for row in items]
        d1 = [x for x in d1 if x is not None]
        d3 = [node_return(row, "D+3") for row in items]
        d3 = [x for x in d3 if x is not None]
        modes = Counter(row.get("primary_mode") or "待归因" for row in items)
        win_modes = Counter(row.get("primary_mode") or "待归因" for row in items if (node_return(row, "D+1") or -999) >= 5)
        lose_modes = Counter(row.get("primary_mode") or "待归因" for row in items if (node_return(row, "D+1") or 999) <= -5)
        days.append(
            {
                "date": d,
                "samples": len(items),
                "d1_available": len(d1),
                "d1_avg": round(sum(d1) / len(d1), 2) if d1 else None,
                "d3_avg": round(sum(d3) / len(d3), 2) if d3 else None,
                "modes": dict(modes),
                "win_modes": dict(win_modes),
                "lose_modes": dict(lose_modes),
                "items": items,
            }
        )
    big_win = [x for x in days if x["d1_avg"] is not None and x["d1_avg"] >= 5]
    big_loss = [x for x in days if x["d1_avg"] is not None and x["d1_avg"] <= -5]
    return {"days": days, "big_win": big_win, "big_loss": big_loss}


def render_md(summary: dict[str, Any]) -> str:
    lines = [
        f"# {date.today().isoformat()} 大赚大亏日模式归因",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "- 口径：按逐笔买入后的 D+1 收盘收益聚合到交易日，解释当天赚钱/亏钱主要来自什么模式。",
        "",
        "## 交易日总览",
        "",
        "| 日期 | 买入笔数 | D+1可算 | D+1均值 | D+3均值 | 主模式分布 | 强反馈模式 | 负反馈模式 |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ]
    for day in sorted(summary["days"], key=lambda x: (x["d1_avg"] is None, -(x["d1_avg"] or -999))):
        fmt = lambda d: "、".join(f"{k}:{v}" for k, v in d.items()) or "-"
        lines.append(
            f"| {day['date']} | {day['samples']} | {day['d1_available']} | {day['d1_avg'] if day['d1_avg'] is not None else '待数据'} | "
            f"{day['d3_avg'] if day['d3_avg'] is not None else '待数据'} | {fmt(day['modes'])} | {fmt(day['win_modes'])} | {fmt(day['lose_modes'])} |"
        )
    lines += ["", "## 大赚日", ""]
    if not summary["big_win"]:
        lines.append("- 暂无按D+1均值定义的大赚日。")
    for day in summary["big_win"]:
        lines.append(f"- {day['date']}：D+1均值 {day['d1_avg']}%，主要正反馈模式：{day['win_modes'] or day['modes']}。")
    lines += ["", "## 大亏日", ""]
    if not summary["big_loss"]:
        lines.append("- 暂无按D+1均值定义的大亏日。")
    for day in summary["big_loss"]:
        lines.append(f"- {day['date']}：D+1均值 {day['d1_avg']}%，主要负反馈模式：{day['lose_modes'] or day['modes']}。")
    lines += [
        "",
        "## 后续修正",
        "",
        "- 大亏日优先回看：是否后排、是否退潮、是否买点后置、是否把题材热度误判为前排确认。",
        "- 大赚日优先沉淀：当时市场状态、题材阶段、股票角色、买点类型是否可复用。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    rows = read_jsonl(DPLUS)
    summary = summarize(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "73wiki-trade-mode-bigday-review-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
    }
    md = render_md(summary)
    (OUT_DIR / "trade-mode-bigday-review.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "trade-mode-bigday-review.md").write_text(md, encoding="utf-8")
    WIKI_OUT.write_text(md, encoding="utf-8")
    print(json.dumps({"ok": True, "days": len(summary["days"]), "big_win": len(summary["big_win"]), "big_loss": len(summary["big_loss"]), "output": str(WIKI_OUT.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
