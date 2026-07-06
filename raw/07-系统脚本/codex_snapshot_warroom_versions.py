#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Snapshot daily war-room files into session versions."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
WIKI_ROOM = ROOT / "wiki/07-作战室"
RAW_PLAN = ROOT / "raw/03-每日计划"
OUT_ROOT = WIKI_ROOM / "版本"
FACTS = ROOT / "data/facts/warroom_version_manifest.jsonl"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def candidate_files(date: str) -> list[Path]:
    paths = [
        WIKI_ROOM / f"{date}-作战室候选票评分表.md",
        WIKI_ROOM / f"{date}-作战总控.md",
        WIKI_ROOM / f"{date}-AI上下文包.md",
        WIKI_ROOM / f"{date}-作战室输入候选.md",
        WIKI_ROOM / "当前作战室工作页.md",
        RAW_PLAN / f"{date}-竞价监控清单.md",
    ]
    return [path for path in paths if path.exists() and path.is_file()]


def snapshot(date: str, session: str, force: bool = False) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    out_dir = OUT_ROOT / date / session
    out_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for src in candidate_files(date):
        dst = out_dir / src.name
        if dst.exists() and not force:
            dst = out_dir / f"{src.stem}-{stamp}{src.suffix}"
        shutil.copy2(src, dst)
        copied.append({"source": rel(src), "snapshot": rel(dst), "sha256": sha256_file(src)})
    payload = {
        "schema": "73wiki-warroom-version-snapshot-v1",
        "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": date,
        "session": session,
        "snapshotDir": rel(out_dir),
        "files": copied,
    }
    manifest = out_dir / "manifest.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    append_jsonl(FACTS, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="作战室候选票版本快照")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--session", choices=["preopen", "auction", "postclose", "next_validation"], required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(json.dumps(snapshot(args.date, args.session, args.force), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
