#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FACTS = ROOT / "data/facts"
ALIAS_PATH = ROOT / "data/facts/trade_mode_alias_map.json"
OUT_DIR = ROOT / "raw/11-Codex分析产物/交易模式归一化"
WIKI = ROOT / "wiki/04-L4交易模式与执行/模式别名归一化表.md"

DEFAULT_ALIAS = {
    "神龙战法": "分歧转一致",
    "弱转强": "分歧转一致",
    "低开转强": "分歧转一致",
    "升龙战法": "趋势主升",
    "趋势加速": "趋势主升",
    "主升浪": "趋势主升",
    "回龙战法": "一进二回封",
    "一进二": "一进二回封",
    "换手回封": "一进二回封",
    "容量中军锚定": "容量票强弱锚",
    "容量中军": "容量票强弱锚",
    "中军锚定": "容量票强弱锚",
    "龙头战法": "龙头战法",
    "市场龙头": "龙头战法",
    "空间龙": "龙头战法",
    "核心龙头": "龙头战法",
    "短板反包": "断板反包",
    "断板修复": "断板反包",
    "首阴反包": "断板反包",
}


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + ("\n" if rows else ""), encoding="utf-8")


def normalize(mode: str, alias: dict[str, str]) -> str:
    return alias.get(str(mode or "").strip(), str(mode or "").strip() or "待人工归因")


def normalize_rows(rows: list[dict[str, Any]], alias: dict[str, str]) -> tuple[list[dict[str, Any]], Counter[str]]:
    changed: Counter[str] = Counter()
    out = []
    for row in rows:
        item = dict(row)
        old = str(item.get("primary_mode") or "待人工归因")
        new = normalize(old, alias)
        if old != new:
            changed[f"{old}->{new}"] += 1
        item["primary_mode_raw"] = old
        item["primary_mode"] = new
        secondary = []
        for mode in item.get("secondary_modes") or []:
            nm = normalize(str(mode), alias)
            if nm and nm != new and nm not in secondary:
                secondary.append(nm)
        item["secondary_modes"] = secondary
        out.append(item)
    return out, changed


def render_md(alias: dict[str, str], changed: Counter[str], unknown: Counter[str], generated_at: str) -> str:
    lines = [
        "# 模式别名归一化表",
        "",
        f"- 生成时间：{generated_at}",
        "- 目的：把淘股吧俗称、你的口述名、Codex旧口径统一到标准模式，便于统计胜率和复盘。",
        "- 规则：不删除历史口径；事实层保留 `primary_mode_raw`，统计使用 `primary_mode`。",
        "",
        "## 已配置别名",
        "",
        "| 别名/旧口径 | 标准模式 |",
        "|---|---|",
    ]
    for key, value in sorted(alias.items()):
        lines.append(f"| {key} | {value} |")
    lines += ["", "## 本次归一化命中", "", "| 变更 | 笔数 |", "|---|---:|"]
    for key, count in changed.most_common():
        lines.append(f"| {key} | {count} |")
    if not changed:
        lines.append("| 无 | 0 |")
    lines += ["", "## 仍需人工确认的模式名", "", "| 模式 | 笔数 |", "|---|---:|"]
    for key, count in unknown.most_common(50):
        lines.append(f"| {key} | {count} |")
    if not unknown:
        lines.append("| 无 | 0 |")
    return "\n".join(lines) + "\n"


def main() -> int:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alias = dict(DEFAULT_ALIAS)
    existing = read_json(ALIAS_PATH, {})
    if isinstance(existing, dict):
        alias.update({str(k): str(v) for k, v in existing.items()})
    write_json(ALIAS_PATH, alias)

    files = [
        FACTS / "trade_mode_attributions.jsonl",
        FACTS / "trade_mode_dplus_results.jsonl",
    ]
    total_changed: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    for path in files:
        rows = read_jsonl(path)
        normalized, changed = normalize_rows(rows, alias)
        total_changed.update(changed)
        for row in normalized:
            mode = str(row.get("primary_mode") or "")
            if mode == "待人工归因":
                unknown[mode] += 1
        if rows:
            write_jsonl(path, normalized)

    today = datetime.now().strftime("%Y-%m-%d")
    OUT_DIR.joinpath(today).mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "73wiki-mode-alias-normalizer-v1",
        "generatedAt": generated_at,
        "alias_count": len(alias),
        "changed": dict(total_changed),
        "unknown": dict(unknown),
    }
    write_json(OUT_DIR / today / "mode-alias-normalizer.json", report)
    md = render_md(alias, total_changed, unknown, generated_at)
    OUT_DIR.joinpath(today, "mode-alias-normalizer.md").write_text(md, encoding="utf-8")
    WIKI.write_text(md, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
