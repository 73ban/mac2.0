#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingest screenshots into raw/08 and create OCR sidecar placeholders."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_SCREEN = ROOT / "raw/08-截图"
FACTS = ROOT / "data/facts/screenshot_ocr_index.jsonl"
PADDLE_SCRIPT = ROOT / "raw/07-系统脚本/codex_paddleocr_raw08.py"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def run_ocr(image: Path, out_txt: Path) -> str:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        if PADDLE_SCRIPT.exists():
            out_json = out_txt.with_suffix(out_txt.suffix + ".json")
            result = subprocess.run([
                "python3",
                str(PADDLE_SCRIPT),
                "--image",
                str(image),
                "--out-md",
                str(out_txt),
                "--out-json",
                str(out_json),
                "--force",
            ], cwd=str(ROOT), text=True, capture_output=True)
            if result.returncode == 0:
                return "ok_paddleocr"
            out_txt.write_text(f"OCR状态：PaddleOCR失败\n\n{result.stderr or result.stdout}\n", encoding="utf-8")
            return "failed_paddleocr"
        out_txt.write_text("OCR状态：待OCR。本机未检测到 tesseract 或 PaddleOCR。\n", encoding="utf-8")
        return "pending_no_ocr_engine"
    base = out_txt.with_suffix("")
    result = subprocess.run([tesseract, str(image), str(base), "-l", "chi_sim+eng"], text=True, capture_output=True)
    if result.returncode != 0:
        out_txt.write_text(f"OCR状态：失败\n\n{result.stderr}\n", encoding="utf-8")
        return "failed"
    return "ok" if out_txt.exists() else "failed"


def ingest(src: Path, date: str, category: str, note: str, ocr: bool) -> dict[str, Any]:
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(src)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    out_dir = RAW_SCREEN / date / category
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{stamp}-{src.name}"
    shutil.copy2(src, dst)
    ocr_txt = dst.with_suffix(dst.suffix + ".ocr.txt")
    ocr_status = run_ocr(dst, ocr_txt) if ocr else "skipped"
    md = dst.with_suffix(dst.suffix + ".md")
    md.write_text(
        "\n".join(
            [
                f"# 截图资料 {stamp}",
                "",
                "```yaml",
                f"date: {date}",
                f"category: {category}",
                f"source_path: {src}",
                f"image_path: {rel(dst)}",
                f"ocr_path: {rel(ocr_txt)}",
                f"ocr_status: {ocr_status}",
                "status: RAW截图资料，重要内容需再进入作战室或个股档案",
                "```",
                "",
                "## 备注",
                "",
                note or "- 待补",
                "",
            ]
        ),
        encoding="utf-8",
    )
    item = {
        "schema": "73wiki-screenshot-ocr-index-v1",
        "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "date": date,
        "category": category,
        "image": rel(dst),
        "ocr": rel(ocr_txt),
        "sidecar": rel(md),
        "ocrStatus": ocr_status,
        "note": note,
    }
    append_jsonl(FACTS, item)
    return item


def main() -> int:
    parser = argparse.ArgumentParser(description="截图/OCR RAW资料池入库")
    parser.add_argument("image")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--category", default="待分类")
    parser.add_argument("--note", default="")
    parser.add_argument("--no-ocr", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ingest(Path(args.image).expanduser(), args.date, args.category, args.note, not args.no_ocr), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
