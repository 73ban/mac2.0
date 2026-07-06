#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""73神话安全 Wiki lint。

只检查活动 wiki 目录，不扫 raw，不扫旧嵌套副本，不调用模型。
用于替代应用内全量 lint 卡死场景。
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WIKI_ROOT = ROOT / "wiki"
REPORT_DIR = ROOT / "wiki" / "09-统计与进化"
SYSTEM_DIR = ROOT / ".system"

SKIP_DIRS = {
    ".stfolder",
    ".stversions",
    "wiki",
    "99-待删除审核",
    "99-迁移",
    "迁移归档",
    "配置归档",
    "logs",
    "__pycache__",
    "node_modules",
    "target",
    "dist",
    "build",
}

SKIP_PATH_PARTS = {
    "RAW独立知识卡",
    "公众号-资料卡",
    "知识星球-每日上扬研报-资料卡",
}

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MAX_FILE_BYTES = 1_000_000


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def should_skip_dir(path: Path) -> bool:
    name = path.name
    if name.startswith("."):
        return True
    if name in SKIP_DIRS:
        return True
    parts = set(path.parts)
    return bool(parts & SKIP_PATH_PARTS)


def iter_md_files() -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(WIKI_ROOT):
        dir_path = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not should_skip_dir(dir_path / d)]
        for filename in filenames:
            if filename.startswith(".") or not filename.endswith(".md"):
                continue
            if filename.endswith("-安全WikiLint报告.md"):
                continue
            files.append(dir_path / filename)
    return sorted(files)


def slug_variants(path: Path) -> set[str]:
    relative = path.relative_to(WIKI_ROOT).with_suffix("")
    value = str(relative)
    return {value, path.stem}


def read_text_limited(path: Path) -> tuple[str, bool]:
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        return "", True
    return path.read_text(encoding="utf-8", errors="ignore"), False


def run_lint() -> dict[str, Any]:
    files = iter_md_files()
    slug_map: dict[str, str] = {}
    for path in files:
        for slug in slug_variants(path):
            slug_map.setdefault(slug, rel(path))

    inbound: dict[str, int] = {}
    pages: list[dict[str, Any]] = []
    broken: list[dict[str, str]] = []
    skipped_large: list[str] = []
    no_outlinks: list[str] = []

    for path in files:
        if path.name in {"index.md", "log.md"}:
            continue
        text, too_large = read_text_limited(path)
        if too_large:
            skipped_large.append(rel(path))
            continue
        links = [x.strip() for x in WIKILINK_RE.findall(text)]
        page_rel = rel(path)
        page_slug = str(path.relative_to(WIKI_ROOT).with_suffix(""))
        pages.append({"path": page_rel, "slug": page_slug, "outlinks": links})
        if not links:
            no_outlinks.append(page_rel)
        for link in links:
            target = slug_map.get(link) or slug_map.get(Path(link).name)
            if target:
                target_slug = str((ROOT / target).relative_to(WIKI_ROOT).with_suffix("")) if target.startswith("wiki/") else link
                inbound[target_slug] = inbound.get(target_slug, 0) + 1
            else:
                broken.append({"page": page_rel, "link": link})

    orphan = [
        page["path"]
        for page in pages
        if inbound.get(page["slug"], 0) == 0 and not page["path"].endswith("/index.md")
    ]
    broken_by_dir = Counter()
    broken_by_link = Counter()
    for item in broken:
        broken_by_dir["/".join(Path(item["page"]).parts[:3])] += 1
        broken_by_link[item["link"]] += 1

    return {
        "生成时间": now_text(),
        "wiki根目录": rel(WIKI_ROOT),
        "扫描文件数": len(files),
        "参与链接检查文件数": len(pages),
        "跳过超大文件数": len(skipped_large),
        "失效链接数": len(broken),
        "孤立页面数": len(orphan),
        "无出链页面数": len(no_outlinks),
        "失效链接高发目录": [
            {"目录": key, "数量": count}
            for key, count in broken_by_dir.most_common(50)
        ],
        "高频失效目标": [
            {"目标": key, "数量": count}
            for key, count in broken_by_link.most_common(80)
        ],
        "跳过超大文件": skipped_large[:80],
        "失效链接": broken[:300],
        "孤立页面": orphan[:300],
        "无出链页面": no_outlinks[:300],
        "忽略目录": sorted(SKIP_DIRS | SKIP_PATH_PARTS),
    }


def render_md(data: dict[str, Any]) -> str:
    lines = [
        "# 安全 Wiki Lint 报告",
        "",
        f"- 生成时间：{data['生成时间']}",
        f"- wiki根目录：`{data['wiki根目录']}`",
        f"- 扫描文件数：{data['扫描文件数']}",
        f"- 参与链接检查文件数：{data['参与链接检查文件数']}",
        f"- 跳过超大文件数：{data['跳过超大文件数']}",
        f"- 失效链接数：{data['失效链接数']}",
        f"- 孤立页面数：{data['孤立页面数']}",
        f"- 无出链页面数：{data['无出链页面数']}",
        "",
        "## 结论",
        "",
        "本脚本只扫活动 wiki，不扫 raw、不扫 `wiki/wiki` 旧嵌套副本、不扫待删除审核目录，也不调用模型。",
        "适合日常快速体检；深度语义检查应按日期或专题分批执行。",
        "",
    ]

    def section(title: str, rows: list[Any], formatter) -> None:
        lines.extend([f"## {title}", ""])
        if not rows:
            lines.append("- 无")
        else:
            for item in rows[:80]:
                lines.append(formatter(item))
        lines.append("")

    section("失效链接样例", data["失效链接"], lambda x: f"- `{x['page']}` -> `[[{x['link']}]]`")
    section("失效链接高发目录", data["失效链接高发目录"], lambda x: f"- `{x['目录']}`：{x['数量']} 个")
    section("高频失效目标", data["高频失效目标"], lambda x: f"- `[[{x['目标']}]]`：{x['数量']} 次")
    section("孤立页面样例", data["孤立页面"], lambda x: f"- `{x}`")
    section("无出链页面样例", data["无出链页面"], lambda x: f"- `{x}`")
    section("跳过超大文件", data["跳过超大文件"], lambda x: f"- `{x}`")

    lines.extend(
        [
            "## 后续处理规则",
            "",
            "- 先修失效链接，再处理孤立页面。",
            "- 孤立页面不等于一定要删，可能是新规则、新复盘或入口未链接。",
            "- 不要对全库一次跑 LLM 语义 lint；需要按月、按目录、按主题分批。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="安全 Wiki lint")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    data = run_lint()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if args.write:
        SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        json_path = SYSTEM_DIR / "safe-wiki-lint.json"
        md_path = REPORT_DIR / f"{args.date}-安全WikiLint报告.md"
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(render_md(data), encoding="utf-8")
        print(f"written {rel(json_path)}")
        print(f"written {rel(md_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
