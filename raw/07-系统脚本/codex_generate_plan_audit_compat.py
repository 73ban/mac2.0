#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为旧版 73WIKI 计划审计生成复盘兼容文件。

旧版 App 只识别 `## 五、明日计划`。当前 13 段复盘可能使用
`明日操盘要点初稿`、`明日计划`、`次日计划` 等标题。本脚本不改原文，
只在 raw/02-每日复盘/计划审计兼容/ 下生成轻量兼容文件。
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REVIEW_ROOT = ROOT / "raw" / "02-每日复盘"
COMPAT_DIR = REVIEW_ROOT / "计划审计兼容"

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})-复盘\.md$")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)


def extract_next_plan(text: str) -> str:
    preferred = []
    for match in HEADING_RE.finditer(text):
        title = match.group(1)
        if "明日" in title and ("计划" in title or "操盘" in title or "要点" in title):
            preferred.append(match)
        elif "次日" in title and ("计划" in title or "操盘" in title or "要点" in title):
            preferred.append(match)

    if not preferred:
        return ""

    match = preferred[-1]
    start = match.end()
    next_match = HEADING_RE.search(text, start)
    end = next_match.start() if next_match else len(text)
    plan = text[start:end].strip()
    return plan


def main() -> int:
    COMPAT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for path in sorted(REVIEW_ROOT.rglob("*-复盘.md")):
        if COMPAT_DIR in path.parents:
            continue
        m = DATE_RE.search(path.name)
        if not m:
            continue
        date = m.group(1)
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"^##\s*五、明日计划", text, re.M):
            continue
        plan = extract_next_plan(text)
        if not plan:
            continue
        out = COMPAT_DIR / f"{date}-复盘.md"
        out.write_text(
            "\n".join(
                [
                    f"# {date} 计划审计兼容复盘",
                    "",
                    f"- 原始文件：`{path.relative_to(ROOT)}`",
                    "- 用途：供旧版 73WIKI 计划审计读取，不作为正式复盘正文。",
                    "",
                    "## 五、明日计划",
                    "",
                    plan,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        written += 1
    print(f"written={written} dir={COMPAT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
