#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DPLUS = ROOT / "data/facts/trade_mode_dplus_results.jsonl"
MODE_DIR = ROOT / "wiki/04-L4交易模式与执行/游资交易模式卡片库"
OUT = ROOT / "raw/11-Codex分析产物/交易模式案例回填"
START = "<!-- codex-mode-cases:start -->"
END = "<!-- codex-mode-cases:end -->"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if path.exists() else []:
        if not line.strip():
            continue
        try:
            v = json.loads(line)
        except Exception:
            continue
        if isinstance(v, dict):
            rows.append(v)
    return rows


def val(row: dict[str, Any], node: str = "D+1") -> float | None:
    try:
        return float(((row.get("nodes") or {}).get(node) or {}).get("close_return_pct"))
    except Exception:
        return None


def replace_block(text: str, block: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if pattern.search(text):
        return pattern.sub(block, text)
    return text.rstrip() + "\n\n" + block + "\n"


def mode_path(mode: str) -> Path:
    return MODE_DIR / f"{mode.replace('/', '-')}.md"


def render(mode: str, rows: list[dict[str, Any]]) -> str:
    wins = sorted([x for x in rows if val(x) is not None and val(x) >= 5], key=lambda x: val(x) or 0, reverse=True)[:8]
    losses = sorted([x for x in rows if val(x) is not None and val(x) <= -5], key=lambda x: val(x) or 0)[:8]
    lines = [
        START,
        "## Codex真实案例库",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "- 口径：来自真实成交后的D+验证，用于补充模式页，不删除原有定义。",
        "",
        "### 成功样本",
        "",
        "| 日期 | 股票 | 操作 | 入场价 | D+1 | D+3 | D+5 | 复盘要点 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in wins:
        lines.append(f"| {row.get('date')} | {row.get('name')} {row.get('code')} | {row.get('action')} | {row.get('entry_price')} | {val(row,'D+1')} | {val(row,'D+3')} | {val(row,'D+5')} | 成功后检查是否主线/前排/盘口确认共振 |")
    if not wins:
        lines.append("| - | - | - | - | - | - | - | 暂无D+1强反馈样本 |")
    lines += ["", "### 失败样本", "", "| 日期 | 股票 | 操作 | 入场价 | D+1 | D+3 | D+5 | 复盘要点 |", "|---|---|---|---:|---:|---:|---:|---|"]
    for row in losses:
        lines.append(f"| {row.get('date')} | {row.get('name')} {row.get('code')} | {row.get('action')} | {row.get('entry_price')} | {val(row,'D+1')} | {val(row,'D+3')} | {val(row,'D+5')} | 失败后检查是否后排/退潮/高潮末端/无确认 |")
    if not losses:
        lines.append("| - | - | - | - | - | - | - | 暂无D+1大负反馈样本 |")
    lines.append(END)
    return "\n".join(lines)


def main() -> int:
    rows = read_jsonl(DPLUS)
    by = defaultdict(list)
    for row in rows:
        by[str(row.get("primary_mode") or "待人工归因")].append(row)
    updated = []
    for mode, items in by.items():
        path = mode_path(mode)
        text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else f"# {mode}\n\n## 模式定义\n\n待补充。\n"
        new = replace_block(text, render(mode, items))
        if new != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new, encoding="utf-8")
            updated.append(str(path.relative_to(ROOT)))
    today = datetime.now().strftime("%Y-%m-%d")
    OUT.joinpath(today).mkdir(parents=True, exist_ok=True)
    (OUT / today / "mode-casebook-update.json").write_text(json.dumps({"updated": updated}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "updated": len(updated)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
