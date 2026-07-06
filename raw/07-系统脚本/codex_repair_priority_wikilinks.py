#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repair broken wikilinks in priority directories when target is unambiguous."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "wiki"
REPORT_DIR = WIKI / "09-统计与进化"
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(#[^\]|]+)?(\|[^\]]+)?\]\]")
GENERATED_REPORT_MARKERS = (
    "Wiki链接修复报告",
    "Wiki链接二次处理",
    "Wiki链接修复剩余工作单",
    "安全WikiLint报告",
)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def iter_md(base: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"99-待删除审核", "迁移归档", "配置归档"}]
        for name in filenames:
            if name.endswith(".md") and not name.startswith("."):
                if any(marker in name for marker in GENERATED_REPORT_MARKERS):
                    continue
                out.append(Path(dirpath) / name)
    return sorted(out)


def build_index() -> tuple[set[str], dict[str, list[str]]]:
    existing: set[str] = set()
    by_norm: dict[str, list[str]] = {}
    for path in iter_md(WIKI):
        slug = str(path.relative_to(WIKI).with_suffix(""))
        existing.add(slug)
        existing.add(path.stem)
        keys = {
            normalize(path.stem),
            normalize(slug),
            normalize(path.stem.replace("-", "")),
        }
        for key in keys:
            if key:
                by_norm.setdefault(key, []).append(slug)
    return existing, by_norm


def normalize(value: str) -> str:
    return re.sub(r"[\s`《》“”\"'（）()【】\[\]\-_/]+", "", value).lower()


def choose_target(link: str, existing: set[str], by_norm: dict[str, list[str]]) -> tuple[str, str]:
    if link in existing or Path(link).name in existing:
        return link, "already_ok"
    key = normalize(link)
    candidates = sorted(set(by_norm.get(key, [])))
    if len(candidates) == 1:
        return candidates[0], "fixed_unique"
    return "", "ambiguous" if candidates else "missing"


def repair_file(path: Path, existing: set[str], by_norm: dict[str, list[str]], write: bool) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    changes: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []

    def repl(match: re.Match[str]) -> str:
        link, anchor, alias = match.group(1).strip(), match.group(2) or "", match.group(3) or ""
        target, status = choose_target(link, existing, by_norm)
        if status == "fixed_unique" and target != link:
            changes.append({"from": link, "to": target})
            return f"[[{target}{anchor}{alias}]]"
        if status in {"missing", "ambiguous"}:
            unresolved.append({"link": link, "status": status})
        return match.group(0)

    new_text = WIKILINK_RE.sub(repl, text)
    if write and new_text != text:
        path.write_text(new_text, encoding="utf-8")
    return {"path": rel(path), "changed": len(changes), "unresolved": unresolved[:50], "changes": changes[:50]}


def run(dirs: list[str], write: bool) -> dict[str, Any]:
    existing, by_norm = build_index()
    files: list[Path] = []
    for item in dirs:
        base = WIKI / item
        if base.exists():
            files.extend(iter_md(base))
    reports = [repair_file(path, existing, by_norm, write) for path in sorted(set(files))]
    changed = sum(item["changed"] for item in reports)
    unresolved_count = sum(len(item["unresolved"]) for item in reports)
    return {
        "schema": "73wiki-priority-wikilink-repair-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "write": write,
        "dirs": dirs,
        "files": len(reports),
        "changedLinks": changed,
        "unresolvedLinksInReport": unresolved_count,
        "reports": [item for item in reports if item["changed"] or item["unresolved"]][:200],
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        "# 优先目录 Wiki 链接修复报告",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 写入模式：{payload['write']}",
        f"- 扫描文件：{payload['files']}",
        f"- 已修链接：{payload['changedLinks']}",
        f"- 报告内未解链接：{payload['unresolvedLinksInReport']}",
        f"- 目录：{', '.join(payload['dirs'])}",
        "",
        "## 文件明细",
        "",
    ]
    for item in payload["reports"]:
        lines.append(f"### `{item['path']}`")
        for change in item.get("changes", []):
            lines.append(f"- 修复：`[[{change['from']}]]` -> `[[{change['to']}]]`")
        for unresolved in item.get("unresolved", [])[:20]:
            lines.append(f"- 未解：`[[{unresolved['link']}]]` ({unresolved['status']})")
        lines.append("")
    if not payload["reports"]:
        lines.append("- 无需处理。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="优先目录 Wiki 链接修复")
    parser.add_argument("--dirs", nargs="+", default=["00-总纲", "07-作战室", "09-统计与进化"])
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    payload = run(args.dirs, args.write)
    slug = "-".join(re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", item).strip("-") for item in args.dirs)[:80] or "all"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / f"{args.date}-{slug}-Wiki链接修复报告.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPORT_DIR / f"{args.date}-{slug}-Wiki链接修复报告.md").write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
