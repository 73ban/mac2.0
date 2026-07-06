#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write Jiuyangongshe warroom-focus evidence into L3 stock cards."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
WIKI_STOCK = ROOT / "wiki" / "03-L3个股档案"
FOCUS_DIR = RAW / "05-研报新闻" / "韭研公社网页"


def rel(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except Exception:
        return str(path)


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def clean(value: Any, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().replace("|", "/")
    return text[:limit]


def title_from_md(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return path.parent.name
    for line in text.splitlines()[:80]:
        line = line.strip()
        if line.startswith("# "):
            return clean(line[2:], 120)
    return path.parent.name


def brief_from_md(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    parts = []
    for line in text.splitlines()[1:120]:
        line = clean(line, 120)
        if not line or line.startswith("!") or line.startswith("[") or line.startswith("*"):
            continue
        parts.append(line)
        if len(" ".join(parts)) > 120:
            break
    return clean(" ".join(parts), 180)


def stock_card_path(code: str, name: str) -> Path:
    WIKI_STOCK.mkdir(parents=True, exist_ok=True)
    return WIKI_STOCK / f"{name}-{code}.md"


def render_block(date: str, row: dict[str, Any]) -> str:
    code = str(row.get("code") or "")
    name = str(row.get("name") or code)
    article_outputs = [Path(p) for p in row.get("articleOutputs") or []]
    lines = [
        "",
        f"<!-- jiuyangongshe-focus:{date}:{code} -->",
        f"## {date} 韭研公社专项逻辑",
        "",
        f"- 更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 触发原因：{'持仓票专项' if row.get('isHolding') else '动态作战室Top5专项'}",
        f"- 作战室排名：{row.get('rank') or '-'}",
        f"- 搜索命中：{row.get('articleLinkCount') or 0} 条，已深挖 {len(article_outputs)} 篇。",
        f"- 搜索页：`{rel(row.get('searchOutput') or '')}`",
        "- 使用边界：韭研负责补题材和产业链逻辑，不直接给买入权限；必须用竞价、热榜、涨停、互动易/公告和 D+验证确认。",
        "",
        "| 文章 | 初步摘要 | RAW |",
        "|---|---|---|",
    ]
    for output in article_outputs:
        md = output / "原文.md"
        title = title_from_md(md)
        brief = brief_from_md(md)
        lines.append(f"| {title} | {brief or '-'} | `{rel(md)}` |")
    if not article_outputs:
        lines.append("| - | 未深挖详情 | - |")
    lines.append("")
    return "\n".join(lines)


def update_card(date: str, row: dict[str, Any]) -> Path:
    code = str(row.get("code") or "")
    name = str(row.get("name") or code)
    path = stock_card_path(code, name)
    marker = f"<!-- jiuyangongshe-focus:{date}:{code} -->"
    block = render_block(date, row)
    if not path.exists():
        path.write_text(f"# {name} {code}\n\n> 自动创建：韭研公社专项抓取首次覆盖该股。\n{block}", encoding="utf-8")
        return path
    text = path.read_text(encoding="utf-8", errors="ignore")
    if marker in text:
        text = re.sub(rf"\n?{re.escape(marker)}\n## {re.escape(date)} 韭研公社专项逻辑\n.*?(?=\n<!-- jiuyangongshe-focus:|\n<!-- dynamic-warroom:|\n## |\Z)", block.strip() + "\n", text, flags=re.S)
    else:
        text = text.rstrip() + "\n" + block
    path.write_text(text, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="韭研公社作战室专项结果写入个股卡")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    payload = read_json(FOCUS_DIR / args.date / "_focus-warroom" / "focus-warroom.json", {})
    rows = payload.get("rows") or []
    outputs = []
    if args.write:
        for row in rows:
            if row.get("code") and row.get("name"):
                outputs.append(rel(update_card(args.date, row)))
    print(json.dumps({"ok": True, "date": args.date, "rows": len(rows), "updatedCards": outputs}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
