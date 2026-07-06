from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path


IGNORE_DIR_NAMES = {".git", ".73wiki", ".llm-wiki", ".system", "__pycache__"}
IGNORE_REL_DIRS = {"07-系统脚本"}
IGNORE_SUFFIXES = {".tmp", ".crdownload", ".part", ".lock"}
WATCH_SUFFIXES = {".md", ".txt", ".csv", ".xls", ".xlsx", ".json"}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load_seen(registry: Path, queue: Path) -> set[str]:
    seen: set[str] = set()
    for file in (registry, queue):
        if not file.exists():
            continue
        with file.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                source_path = item.get("source_path")
                content_hash = item.get("content_hash")
                if source_path and content_hash:
                    seen.add(f"{source_path}|{content_hash}")
    return seen


def should_scan(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    if any(part in IGNORE_DIR_NAMES for part in rel.parts):
        return False
    if any(part.lower() in {"images", "image", "assets"} or part.lower().endswith("_assets") for part in rel.parts):
        return False
    if rel.parts and rel.parts[0] in IGNORE_REL_DIRS:
        return False
    if path.suffix.lower() in IGNORE_SUFFIXES:
        return False
    if path.suffix.lower() not in WATCH_SUFFIXES:
        return False
    return path.is_file()


def list_raw_files(raw_root: Path, min_mtime: float | None = None) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(raw_root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIR_NAMES]
        base = Path(dirpath)
        for name in filenames:
            path = base / name
            if min_mtime is not None:
                try:
                    if path.stat().st_mtime < min_mtime:
                        continue
                except Exception:
                    continue
            if should_scan(path, raw_root):
                files.append(path)
    return files


def infer_source_agent(path: Path) -> str:
    text = str(path)
    if path.suffix.lower() in {".md", ".txt"}:
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:4096]
            if "ingested_by: codex" in head or "capture_pipeline: werss_rss" in head or "capture_pipeline: werss_api" in head:
                return "codex"
        except Exception:
            pass
    if "公众号" in text or "ymj0418" in text or "小睿睿" in text or "股痴" in text or "奇衡" in text:
        return "hermes"
    if "通达信" in text or "竞价" in text or "龙虎榜" in text:
        return "tdxclaw/workbuddy"
    return "unknown"


def write_log_page(log_page: Path, discovered: list[dict], scan_seconds: int) -> None:
    log_page.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# RAW自动扫描日志-{today}",
        "",
        f"最近扫描时间：{now_text()}",
        f"扫描间隔：{scan_seconds} 秒",
        "",
        "## 说明",
        "",
        "本页由大鸟 RAW 监控器自动生成，只负责发现、排队、防重复标记。",
        "内容是否真正写入 WIKI 的 L2/L3/L4，由大鸟在摄入流程中完成。",
        "",
        "## 本轮新发现",
        "",
    ]
    if not discovered:
        lines.append("本轮无新文件。")
    else:
        lines.extend(["| 时间 | 来源智能体 | 文件 | 大小 | 状态 |", "|---|---|---|---:|---|"])
        for item in discovered:
            lines.append(
                f"| {item['first_seen_at']} | {item['source_agent']} | {item['source_path']} | {item['size']} | pending_codex_ingest |"
            )
    lines.append("")
    log_page.write_text("\n".join(lines), encoding="utf-8")


def scan_once(root: Path, scan_seconds: int, lookback_hours: int, write_wiki_log: bool = True) -> int:
    raw_root = root / "raw"
    system_dir = root / ".system"
    system_dir.mkdir(parents=True, exist_ok=True)

    registry = system_dir / "ingest-registry.jsonl"
    queue = system_dir / "codex-raw-watch-queue.jsonl"
    state = system_dir / "codex-raw-watch-state.json"
    log_page = root / "wiki" / "08-信息来源" / f"RAW自动扫描日志-{datetime.now().strftime('%Y-%m-%d')}.md"

    seen = load_seen(registry, queue)
    discovered: list[dict] = []

    min_mtime = None if lookback_hours <= 0 else time.time() - lookback_hours * 3600
    for path in list_raw_files(raw_root, min_mtime=min_mtime):
        try:
            stat = path.stat()
            if stat.st_size == 0:
                continue
            digest = sha256_file(path)
        except Exception as exc:
            discovered.append(
                {
                    "raw_id": "",
                    "source_path": str(path),
                    "source_agent": "unknown",
                    "status": "scan_error",
                    "size": 0,
                    "content_hash": "",
                    "first_seen_at": now_text(),
                    "error": str(exc),
                }
            )
            continue
        key = f"{path}|{digest}"
        if key in seen:
            continue
        item = {
            "raw_id": f"{digest}:codex-raw-watch",
            "source_path": str(path),
            "source_agent": infer_source_agent(path),
            "preferred_ingestor": "codex",
            "status": "pending_codex_ingest",
            "deepseek_action": "skip_pending_codex",
            "truth_grade": "S3",
            "fate": "pending",
            "content_hash": digest,
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "first_seen_at": now_text(),
            "notes": "RAW watcher discovered this file. Codex should ingest it before DeepSeek handles it.",
        }
        with queue.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        discovered.append(item)
        seen.add(key)

    state.write_text(
        json.dumps(
            {
                "last_scan_at": now_text(),
                "scan_seconds": scan_seconds,
                "lookback_hours": lookback_hours,
                "new_files_this_scan": len(discovered),
                "queue_path": str(queue),
                "log_page": str(log_page) if write_wiki_log else "",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if write_wiki_log:
        write_log_page(log_page, discovered, scan_seconds)
    return len(discovered)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--seconds", type=int, default=3)
    parser.add_argument("--lookback-hours", type=int, default=96)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-wiki-log", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    seconds = max(3, args.seconds)
    lookback_hours = args.lookback_hours

    if args.once:
        count = scan_once(root, seconds, lookback_hours, write_wiki_log=not args.no_wiki_log)
        print(json.dumps({"new_files": count, "root": str(root), "lookback_hours": lookback_hours}, ensure_ascii=False))
        return

    while True:
        try:
            scan_once(root, seconds, lookback_hours, write_wiki_log=not args.no_wiki_log)
        except Exception as exc:
            error_log = root / ".system" / "codex-raw-watch-error.log"
            error_log.parent.mkdir(parents=True, exist_ok=True)
            with error_log.open("a", encoding="utf-8") as f:
                f.write(f"[{now_text()}] {exc}\n")
        time.sleep(seconds)


if __name__ == "__main__":
    main()
