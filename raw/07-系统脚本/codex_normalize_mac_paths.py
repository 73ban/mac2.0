#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAC_ROOT = PROJECT_ROOT.as_posix()

REPLACEMENTS = {
    "C:\\wiki\\73神话": MAC_ROOT,
    "C:\\\\wiki\\\\73神话": MAC_ROOT,
    "C:/wiki/73神话": MAC_ROOT,
    "C:\\wiki\\73绁炶瘽": MAC_ROOT,
    "C:\\\\wiki\\\\73绁炶瘽": MAC_ROOT,
    "C:/wiki/73绁炶瘽": MAC_ROOT,
    "C:\\Users\\Administrator\\Desktop\\73WIKI-1.0-source": "/Users/qixinchaye/Workspace/73WIKI-1.0-source",
    "C:\\\\Users\\\\Administrator\\\\Desktop\\\\73WIKI-1.0-source": "/Users/qixinchaye/Workspace/73WIKI-1.0-source",
    "C:/Users/Administrator/Desktop/73WIKI-1.0-source": "/Users/qixinchaye/Workspace/73WIKI-1.0-source",
    "C:\\Users\\Administrator\\Desktop\\workspace\\feishu-73-manager": "/Users/qixinchaye/Workspace/feishu-73-manager",
    "C:\\\\Users\\\\Administrator\\\\Desktop\\\\workspace\\\\feishu-73-manager": "/Users/qixinchaye/Workspace/feishu-73-manager",
    "C:/Users/Administrator/Desktop/workspace/feishu-73-manager": "/Users/qixinchaye/Workspace/feishu-73-manager",
    "C:\\Program Files\\nodejs\\node.exe": "/Users/qixinchaye/.nvm/versions/node/v24.18.0/bin/node",
    "C:\\\\Program Files\\\\nodejs\\\\node.exe": "/Users/qixinchaye/.nvm/versions/node/v24.18.0/bin/node",
    "C:\\Windows\\system32\\cmd.exe": "/bin/zsh",
    "C:\\\\Windows\\\\system32\\\\cmd.exe": "/bin/zsh",
    "npm.cmd": "npm",
}

DEFAULT_TARGETS = [
    ".system/cs-cailian-seen.json",
    ".system/raw-queue-consumer-state.json",
    ".system/raw-queue-hot-files.json",
    ".system/codex-raw-watch-queue.indexed-2026-06-13-121243.jsonl",
    ".system/ingest-registry.jsonl",
    ".system/werss-api-registry.jsonl",
    ".system/werss-api-state.json",
    ".system/werss-api-repair-audit.json",
    ".system/werss-api-repair-audit.md",
    ".system/werss-api-repair-audit-damangshe.json",
    ".system/werss-private-link-import.audit.json",
    ".system/youzi-author-refresh-audit.json",
    ".system/youzi-author-refresh-private-verify.json",
    ".system/werss-private-mp-seeds.audit.json",
    ".system/werss-api-repair-audit-damangshe.md",
    ".system/werss-repair-summary-2026-06-21.md",
    ".system/交接单-2026-06-20-WeRSS接管与公众号重抓.md",
    ".system/交接单-2026-06-21-私域游资号直抓与学习闭环.md",
    "data/facts/stock_reason_cards.jsonl",
    "data/facts/catalyst_events.jsonl",
    "data/training/raw_learning_errors.jsonl",
    "data/training/raw_learning_samples.jsonl",
]

TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt"}

PATH_PREFIXES = (
    MAC_ROOT,
    "/Users/qixinchaye/Workspace/73WIKI-1.0-source",
    "/Users/qixinchaye/Workspace/feishu-73-manager",
)


def iter_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if not target.exists():
        return []
    return [
        path
        for path in target.rglob("*")
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES
    ]


def normalize_string(value: str) -> str:
    updated = value
    for old, new in REPLACEMENTS.items():
        updated = updated.replace(old, new)

    if any(prefix in updated for prefix in PATH_PREFIXES):
        updated = updated.replace("\\\\", "/").replace("\\", "/")
        updated = re.sub(r"/+", "/", updated)
        updated = updated.replace("http:/", "http://").replace("https:/", "https://")
    return updated


def normalize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_string(value)
    if isinstance(value, list):
        return [normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_json_value(item) for key, item in value.items()}
    return value


def dumps_json(value: Any, *, pretty: bool = False, ascii_safe: bool = False) -> str:
    kwargs = {
        "ensure_ascii": ascii_safe,
    }
    if pretty:
        kwargs["indent"] = 2
    else:
        kwargs["separators"] = (",", ":")
    text = json.dumps(value, **kwargs)
    if not ascii_safe:
        try:
            text.encode("utf-8")
        except UnicodeEncodeError:
            return dumps_json(value, pretty=pretty, ascii_safe=True)
    return text


def normalize_text(text: str) -> str:
    updated = normalize_string(text)
    project_prefix = re.escape(MAC_ROOT)
    workspace_prefix = re.escape("/Users/qixinchaye/Workspace/73WIKI-1.0-source")
    updated = re.sub(rf"({project_prefix}|{workspace_prefix})(?:\\\\|\\)+", r"\1/", updated)
    return updated


def normalize_file(path: Path, dry_run: bool) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False

    updated = text
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            updated = normalize_text(text)
        else:
            normalized = normalize_json_value(payload)
            updated = f"{dumps_json(normalized, pretty=True)}\n"
    elif path.suffix.lower() == ".jsonl":
        lines = text.splitlines()
        normalized_lines: list[str] = []
        parse_all = True
        for line in lines:
            if not line.strip():
                normalized_lines.append(line)
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                parse_all = False
                break
            normalized_lines.append(dumps_json(normalize_json_value(payload), ascii_safe=True))
        updated = "\n".join(normalized_lines) + ("\n" if text.endswith("\n") else "") if parse_all else normalize_text(text)
    else:
        updated = normalize_text(text)

    if updated == text:
        return False
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="把当前缓存/状态里的 Windows 项目根路径统一成 Mac 项目根路径。")
    parser.add_argument("targets", nargs="*", help="要处理的文件或目录；默认处理当前系统缓存和状态文件")
    parser.add_argument("--dry-run", action="store_true", help="只打印会修改的文件，不写入")
    args = parser.parse_args()

    targets = args.targets or DEFAULT_TARGETS
    changed: list[Path] = []
    checked = 0
    for target_arg in targets:
        target = (PROJECT_ROOT / target_arg).resolve() if not Path(target_arg).is_absolute() else Path(target_arg)
        for path in iter_files(target):
            checked += 1
            if normalize_file(path, args.dry_run):
                changed.append(path)

    for path in changed:
        print(path.relative_to(PROJECT_ROOT))
    print(f"checked={checked} changed={len(changed)} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
