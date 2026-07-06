#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit active 73wiki workflow files for Windows/external fact-layer residue."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = ROOT / ".system/mac-only-workflow-audit.json"
OUT_MD_DIR = ROOT / "wiki/09-统计与进化"

PATTERN = re.compile(
    r"Windows 本地|Windows本地|Windows电脑|云服务器|旧服务器|外部事实层|回传外部事实层|"
    r"PowerShell|\.ps1\b|\.cmd\b|\.bat\b|C:\\|C:/|D:\\|D:/",
    re.I,
)

ACTIVE_FILES = [
    ROOT / "AGENTS.md",
    ROOT / "MEMORY.md",
    ROOT / "73wiki.config.json",
    ROOT / "73wiki.system.json",
    ROOT / ".system/data-interface-registry.json",
]

ACTIVE_DIRS = [
    ROOT / "raw/07-系统脚本",
    ROOT / "wiki/10-系统配置",
]

SKIP_PARTS = {
    ".git",
    ".venv-ocr",
    ".system/venv-tdxrs",
    ".conflicts",
    ".llm-wiki",
    "node_modules",
    "__pycache__",
    "raw/09-短线知识/淘股吧实盘赛",
}

HISTORICAL_NAME_MARKERS = [
    "迁移",
    "历史",
    "清理候选",
    "SOUL",
    "TDX_CLAW_CONTEXT",
]

ACTIVE_DOC_NAMES = {
    "AGENTS.md",
    "MEMORY.md",
    "Codex每日启动检查清单.md",
    "数据接口统一总控.md",
    "截图OCR自动化规则.md",
    "淘股吧实盘赛样本学习规则.md",
    "Codex每日工作必需数据与缺口清单.md",
    "2026-07-05-Codex新窗口交接单.md",
    "2026-07-05-Mac长期常驻运行维护规则.md",
    "热榜数据统一落点规则.md",
    "互动问答与22点30个股线索雷达规则.md",
}

SKIP_FILE_NAMES = {
    "codex_audit_mac_only_workflow.py",
    "codex_audit_mac_migration_residue.py",
    "codex_mac_migration_doctor.py",
    "codex_normalize_mac_paths.py",
}

NEGATION_MARKERS = [
    "不再",
    "已停用",
    "历史",
    "不能把",
    "不能作为",
    "不绑定",
    "不等于",
    "不作为当前",
    "不要",
    "无 Windows",
    "无 `.ps1",
    "Mac-only",
]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def skipped(path: Path) -> bool:
    r = rel(path)
    return any(part in r for part in SKIP_PARTS)


def iter_files() -> list[Path]:
    files = [path for path in ACTIVE_FILES if path.exists()]
    for directory in ACTIVE_DIRS:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or skipped(path):
                continue
            if path.name in SKIP_FILE_NAMES:
                continue
            if path.suffix.lower() not in {".md", ".py", ".sh", ".json", ".txt", ".plist"}:
                continue
            files.append(path)
    launch_agents = Path.home() / "Library/LaunchAgents"
    if launch_agents.exists():
        files.extend(sorted(launch_agents.glob("com.73wiki*.plist")))
    return sorted(set(files), key=lambda p: rel(p))


def classify(path: Path, line: str) -> str:
    name = path.name
    r = rel(path)
    if any(marker in line for marker in NEGATION_MARKERS):
        return "historical_or_template"
    if re.match(r"20\d{2}-\d{2}-\d{2}-", name) and name not in ACTIVE_DOC_NAMES:
        return "historical_or_template"
    if r.startswith("raw/07-系统脚本/templates/"):
        return "historical_or_template"
    if path in ACTIVE_FILES or name in ACTIVE_DOC_NAMES:
        return "active_blocker"
    if path.suffix in {".py", ".sh"} and "raw/07-系统脚本/templates" not in r:
        return "active_blocker"
    if r.startswith("raw/07-系统脚本/scripts/") or any(marker in name for marker in HISTORICAL_NAME_MARKERS) or "评估" in name:
        return "historical_or_template"
    if "历史" in line or "旧口径" in line or "不作为当前" in line:
        return "historical_or_template"
    return "review"


def scan() -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    scanned = 0
    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        scanned += 1
        for lineno, line in enumerate(text.splitlines(), start=1):
            if PATTERN.search(line):
                hits.append(
                    {
                        "file": rel(path),
                        "line": lineno,
                        "class": classify(path, line),
                        "text": line.strip()[:240],
                    }
                )
    blockers = [item for item in hits if item["class"] == "active_blocker"]
    review = [item for item in hits if item["class"] == "review"]
    historical = [item for item in hits if item["class"] == "historical_or_template"]
    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scope": "active Mac-only workflow files",
        "scannedFiles": scanned,
        "hits": len(hits),
        "activeBlockers": blockers,
        "reviewItems": review,
        "historicalOrTemplates": historical,
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {datetime.now().strftime('%Y-%m-%d')} Mac-only工作流审计报告",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 扫描范围：{payload['scope']}",
        f"- 扫描文件数：{payload['scannedFiles']}",
        f"- 命中总数：{payload['hits']}",
        f"- 活跃阻断项：{len(payload['activeBlockers'])}",
        f"- 待复核项：{len(payload['reviewItems'])}",
        f"- 历史/模板项：{len(payload['historicalOrTemplates'])}",
        "",
        "## 结论",
        "",
    ]
    if payload["activeBlockers"]:
        lines.append("- 仍有活跃入口残留 Windows、外部事实层或龙虾/老虎当前依赖口径，需要继续修。")
    else:
        lines.append("- 活跃入口未发现必须阻断的 Windows/外部事实层依赖；剩余命中主要是历史记录、旧模板或需人工复核的说明。")
    lines += ["", "## 活跃阻断项", ""]
    if payload["activeBlockers"]:
        for item in payload["activeBlockers"][:120]:
            lines.append(f"- `{item['file']}:{item['line']}`：{item['text']}")
    else:
        lines.append("- 无。")
    lines += ["", "## 待复核项", ""]
    if payload["reviewItems"]:
        for item in payload["reviewItems"][:120]:
            lines.append(f"- `{item['file']}:{item['line']}`：{item['text']}")
    else:
        lines.append("- 无。")
    lines += [
        "",
        "## 历史/模板命中",
        "",
        "- 这类文件不作为当前 Mac-only 运行入口；如后续要清理，应单独按历史模板归档处理。",
    ]
    for item in payload["historicalOrTemplates"][:80]:
        lines.append(f"- `{item['file']}:{item['line']}`：{item['text']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit active Mac-only workflow files.")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = scan()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUT_MD_DIR.mkdir(parents=True, exist_ok=True)
        report = OUT_MD_DIR / f"{datetime.now().strftime('%Y-%m-%d')}-Mac-only工作流审计报告.md"
        report.write_text(render_md(payload), encoding="utf-8")
        print(f"written {rel(OUT_JSON)}")
        print(f"written {rel(report)}")
    return 1 if payload["activeBlockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
