#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rotate 73神话 runtime logs for long-running Mac usage."""

from __future__ import annotations

import argparse
import gzip
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / ".system/logs"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def rotate_one(path: Path, max_bytes: int, keep: int) -> dict[str, object] | None:
    if not path.is_file() or path.suffix == ".gz":
        return None
    size = path.stat().st_size
    if size <= max_bytes:
        return None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = path.with_name(f"{path.name}.{stamp}.gz")
    with path.open("rb") as src, gzip.open(archive, "wb") as dst:
        shutil.copyfileobj(src, dst)

    # Keep launchd file handles valid by truncating in place instead of renaming.
    path.write_text("", encoding="utf-8")

    archives = sorted(path.parent.glob(f"{path.name}.*.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed: list[str] = []
    for old in archives[keep:]:
        removed.append(rel(old))
        old.unlink(missing_ok=True)

    return {
        "日志": rel(path),
        "原大小": size,
        "归档": rel(archive),
        "删除旧归档": removed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate 73神话 .system/logs files.")
    parser.add_argument("--max-mb", type=int, default=5)
    parser.add_argument("--keep", type=int, default=7)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    max_bytes = args.max_mb * 1024 * 1024
    rotated: list[dict[str, object]] = []
    if LOG_DIR.exists():
        for path in sorted(LOG_DIR.glob("*.log")) + sorted(LOG_DIR.glob("*.out")) + sorted(LOG_DIR.glob("*.err")):
            item = rotate_one(path, max_bytes=max_bytes, keep=args.keep)
            if item:
                rotated.append(item)

    if not args.quiet:
        if rotated:
            for item in rotated:
                print(f"rotated {item['日志']} -> {item['归档']}")
        else:
            print("no logs rotated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
