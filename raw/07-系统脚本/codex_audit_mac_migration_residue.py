#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计 Mac 迁移后的 Windows/服务器残留和 Wiki 噪音源。"""

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
REPORT_DIR = ROOT / "wiki" / "09-统计与进化"
SYSTEM_DIR = ROOT / ".system"

TEXT_SUFFIXES = {
    ".md",
    ".json",
    ".jsonl",
    ".py",
    ".js",
    ".mjs",
    ".sh",
    ".plist",
    ".ps1",
    ".cmd",
    ".bat",
    ".txt",
    ".csv",
}

SKIP_PARTS = {
    ".git",
    ".venv-ocr",
    "node_modules",
    "__pycache__",
    "venv-tdxrs",
    ".stversions",
    ".stfolder",
}

SKIP_REL_PREFIXES = (
    ".conflicts/",
    ".73wiki/backups/",
    ".llm-wiki/",
    "data/",
    "raw/01-交割单/",
    "raw/02-每日复盘/",
    "raw/04-市场数据/",
    "raw/05-研报新闻/",
    "raw/08-截图/",
    "raw/09-短线知识/",
    "raw/10-飞书交易沟通/",
    "raw/11-Codex分析产物/",
    ".system/codex-raw-watch-queue",
    ".system/md-reorg-manifest-",
    ".system/tail-clean-manifest-",
    ".system/wiki-prune-manifest-",
)

MAX_SCAN_BYTES = 2_000_000

NOISE_ROOTS = [
    ".conflicts",
    ".73wiki/backups",
    ".system/.system",
    ".llm-wiki/.llm-wiki",
    "data/data",
]

WINDOWS_PATH_RE = r"[CDE]:[\\/](?:Users|ADMINI|wiki|73神话|raw|Desktop|AppData|workspace|Program|Windows|\.system)"
WINDOWS_RE = re.compile(
    rf"{WINDOWS_PATH_RE}|PowerShell|\.ps1\b|\.cmd\b|\.bat\b|04-行情市场数据|旧服务器|云服务器|服务器WeRSS",
    re.IGNORECASE,
)


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def should_skip(path: Path) -> bool:
    if set(path.parts) & SKIP_PARTS:
        return True
    r = rel(path)
    return any(r == prefix.rstrip("/") or r.startswith(prefix) for prefix in SKIP_REL_PREFIXES)


def iter_text_files() -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        base = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not should_skip(base / d)]
        for name in filenames:
            path = base / name
            if path.suffix.lower() in TEXT_SUFFIXES:
                try:
                    if path.stat().st_size > MAX_SCAN_BYTES:
                        continue
                except OSError:
                    continue
                files.append(path)
    return sorted(files)


def classify(path: Path) -> str:
    r = rel(path)
    if path.name in {
        "codex_audit_mac_migration_residue.py",
        "codex_mac_migration_doctor.py",
        "codex_normalize_mac_paths.py",
    }:
        return "迁移工具"
    if r.startswith(".conflicts/") or r.startswith(".73wiki/backups/"):
        return "隔离备份"
    if r.startswith(".system/.system/") or r.startswith(".llm-wiki/.llm-wiki/") or r.startswith("data/data/"):
        return "嵌套旧副本"
    if r.startswith("raw/07-系统脚本/legacy-tools/"):
        return "旧工具"
    if r.endswith(".ps1") or r.endswith(".cmd") or r.endswith(".bat"):
        return "Windows侧工具"
    if r.startswith("raw/07-系统脚本/templates/"):
        return "Windows协作模板"
    if path.suffix.lower() in {".md", ".txt"} and (
        r.startswith("raw/07-系统脚本/") or r.startswith("wiki/10-系统配置/")
    ):
        return "说明文档"
    if r == ".system/data-interface-registry.json":
        return "当前配置"
    if r.startswith("wiki/10-系统配置/") or r.startswith(".system/scripts/") or r.startswith("raw/07-系统脚本/"):
        return "需关注配置"
    return "历史内容"


def scan_windows_hits(files: list[Path]) -> tuple[list[dict[str, Any]], Counter[str]]:
    hits: list[dict[str, Any]] = []
    counter: Counter[str] = Counter()
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        matches = WINDOWS_RE.findall(text)
        if not matches:
            continue
        item = {
            "文件": rel(path),
            "分类": classify(path),
            "命中数": len(matches),
            "示例": sorted(set(matches))[:6],
        }
        hits.append(item)
        counter[item["分类"]] += 1
    return hits, counter


def count_files(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    return sum(1 for p in path.rglob("*") if p.is_file())


def size_text(path: Path) -> str:
    if not path.exists():
        return "不存在"
    total = 0
    if path.is_file():
        total = path.stat().st_size
    else:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    units = ["B", "KB", "MB", "GB"]
    value = float(total)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{total}B"


def build_report() -> dict[str, Any]:
    files = iter_text_files()
    hits, by_type = scan_windows_hits(files)
    noise = []
    for item in NOISE_ROOTS:
        path = ROOT / item
        noise.append(
            {
                "目录": item,
                "存在": path.exists(),
                "文件数": count_files(path),
                "体积": size_text(path),
                "建议": "不进索引、不进全库 lint；确认外层副本完整后再考虑删除",
            }
        )

    active_script_files = [p for p in files if rel(p).startswith("raw/07-系统脚本/")]
    windows_tools = [
        rel(p)
        for p in active_script_files
        if p.suffix.lower() in {".ps1", ".cmd", ".bat"} and "legacy-tools" not in rel(p)
    ]

    return {
        "生成时间": now_text(),
        "根目录": str(ROOT),
        "扫描文本文件数": len(files),
        "Windows或旧路径命中文件数": len(hits),
        "按分类统计": dict(by_type),
        "噪音目录": noise,
        "Windows侧工具文件": windows_tools,
        "必须修复": [
            x
            for x in hits
            if x["分类"] == "需关注配置"
        ][:80],
        "保留或隔离": [
            x
            for x in hits
            if x["分类"] in {"隔离备份", "嵌套旧副本", "旧工具", "Windows侧工具", "Windows协作模板", "说明文档", "迁移工具"}
        ][:120],
        "全部命中样例": hits[:300],
    }


def render_md(data: dict[str, Any]) -> str:
    lines = [
        "# Mac迁移残留与Wiki结构审计",
        "",
        f"生成时间：{data['生成时间']}",
        "",
        "## 总结",
        "",
        f"- 扫描文本文件：{data['扫描文本文件数']} 个。",
        f"- Windows/旧路径命中文件：{data['Windows或旧路径命中文件数']} 个。",
        "- 当前真正需要关注的是 Mac 主链路配置，不是隔离区里的旧 Windows 记录。",
        "- `.conflicts`、`.system/.system`、`.llm-wiki/.llm-wiki`、`data/data` 是全库 lint 的主要噪音源，必须排除。",
        "",
        "## 噪音目录",
        "",
        "| 目录 | 存在 | 文件数 | 体积 | 建议 |",
        "|---|---:|---:|---:|---|",
    ]
    for item in data["噪音目录"]:
        lines.append(
            f"| `{item['目录']}` | {item['存在']} | {item['文件数']} | {item['体积']} | {item['建议']} |"
        )
    lines.extend(["", "## Windows侧工具文件", ""])
    if data["Windows侧工具文件"]:
        for path in data["Windows侧工具文件"]:
            lines.append(f"- `{path}`")
    else:
        lines.append("- 无")

    lines.extend(["", "## 必须修复或复核", ""])
    if data["必须修复"]:
        lines.append("| 文件 | 命中数 | 示例 |")
        lines.append("|---|---:|---|")
        for item in data["必须修复"]:
            lines.append(f"| `{item['文件']}` | {item['命中数']} | {', '.join(item['示例'])} |")
    else:
        lines.append("- 暂无 Mac 主链路配置硬伤。")

    lines.extend(
        [
            "",
            "## 处理结论",
            "",
            "1. 根目录 Windows 一次性脚本已移入 `raw/07-系统脚本/legacy-tools/`。",
            "2. 新增 `.wikiignore`，统一排除迁移冲突、旧副本、运行缓存、RAW 和 Syncthing 历史。",
            "3. 新增 `wiki/10-系统配置/Wiki清理与Lint降噪规则.md`，应用内深度 lint 必须按这个口径执行。",
            "4. `data/data` 体积较大，先标记为旧嵌套副本，不直接删除；等确认外层 `data/` 已完整承接后再清。",
            "5. `.system/.system` 和 `.llm-wiki/.llm-wiki` 含旧 Windows 路径，不作为 Mac 当前运行入口。",
            "",
            "## 后续自动化",
            "",
            "以后每次迁移、同步、应用卡死或全库 lint 异常，先运行：",
            "",
            "```bash",
            "python3 raw/07-系统脚本/codex_audit_mac_migration_residue.py --write",
            "python3 raw/07-系统脚本/codex_safe_wiki_lint.py --write",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Mac 迁移残留审计")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    data = build_report()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if args.write:
        SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        json_path = SYSTEM_DIR / "mac-migration-residue-audit.json"
        md_path = REPORT_DIR / "2026-07-04-Mac迁移残留与Wiki结构审计.md"
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(render_md(data), encoding="utf-8")
        print(f"written {rel(json_path)}")
        print(f"written {rel(md_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
