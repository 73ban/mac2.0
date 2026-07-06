#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit stock-to-board mapping coverage for candidates and hot stocks."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WIKI_STATS = ROOT / "wiki/09-统计与进化"
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|8\d{5})(?!\d)")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def latest_stock_boards() -> tuple[str, dict[str, Any], Path | None]:
    root = ROOT / "raw/04-市场数据/板块成分股"
    candidates = sorted(root.glob("*/tdx-stock-boards.json"), reverse=True)
    for path in candidates:
        data = read_json(path)
        if isinstance(data, dict):
            if isinstance(data.get("股票板块"), dict):
                return path.parent.name, data["股票板块"], path
            return path.parent.name, data, path
        if isinstance(data, list):
            mapping = {}
            for item in data:
                if isinstance(item, dict):
                    code = str(item.get("code") or item.get("stockCode") or "")
                    if code:
                        mapping[code] = item
            return path.parent.name, mapping, path
    return "", {}, None


def codes_from_json(path: Path) -> set[str]:
    data = read_json(path)
    text = json.dumps(data, ensure_ascii=False) if data is not None else read_text(path)
    return set(CODE_RE.findall(text))


def collect_codes(date: str) -> dict[str, set[str]]:
    sources: dict[str, set[str]] = {}
    source_paths = [
        ("作战室候选", ROOT / f"wiki/07-作战室/{date}-作战室候选票评分表.md"),
        ("作战室输入", ROOT / f"wiki/07-作战室/{date}-作战室输入候选.md"),
        ("消息催化评分", ROOT / f"raw/11-Codex分析产物/消息催化评分/{date}/message-catalyst-score.json"),
        ("同花顺热榜", ROOT / f"raw/04-市场数据/同花顺热榜/{date}/ths-hot-top100.json"),
        ("通达信热榜", ROOT / f"raw/04-市场数据/通达信热榜/{date}/tdx-hot-top100.json"),
    ]
    for label, path in source_paths:
        if path.exists():
            sources[label] = codes_from_json(path)
    return sources


def build(date: str) -> dict[str, Any]:
    board_date, mapping, mapping_path = latest_stock_boards()
    sources = collect_codes(date)
    all_codes = sorted(set().union(*sources.values())) if sources else []
    mapped = []
    missing = []
    for code in all_codes:
        entry = mapping.get(code) or mapping.get(code[-6:])
        if entry:
            mapped.append({"code": code, "board": entry})
        else:
            missing.append(code)
    total = len(all_codes)
    return {
        "schema": "73wiki-board-mapping-coverage-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": date,
        "mappingDate": board_date,
        "mappingPath": str(mapping_path.relative_to(ROOT)) if mapping_path else "",
        "summary": {
            "codes": total,
            "mapped": len(mapped),
            "missing": len(missing),
            "coverage": round(len(mapped) / total, 4) if total else 0,
        },
        "sources": {label: sorted(codes) for label, codes in sources.items()},
        "missing": missing,
        "mappedSample": mapped[:30],
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 板块成分股映射覆盖率",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 映射日期：{payload['mappingDate'] or '-'}",
        f"- 映射文件：`{payload['mappingPath'] or '-'}`",
        f"- 覆盖率：{payload['summary']['mapped']}/{payload['summary']['codes']} = {payload['summary']['coverage']:.2%}",
        "",
        "## 来源覆盖",
        "",
        "| 来源 | 代码数 |",
        "|---|---:|",
    ]
    for label, codes in payload["sources"].items():
        lines.append(f"| {label} | {len(codes)} |")
    lines.extend(["", "## 缺映射代码", ""])
    if payload["missing"]:
        for code in payload["missing"][:120]:
            lines.append(f"- `{code}`")
    else:
        lines.append("- 无。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="板块成分股映射覆盖率")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    if args.write:
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / f"{args.date}-板块成分股映射覆盖率.md").write_text(render(payload), encoding="utf-8")
        (WIKI_STATS / f"{args.date}-板块成分股映射覆盖率.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
