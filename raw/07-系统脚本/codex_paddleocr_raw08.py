#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run local PaddleOCR PP-OCRv6 small on raw/08 screenshots."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
VENV_PY = ROOT / ".venv-ocr/bin/python"
RAW_SCREEN = ROOT / "raw/08-截图"
FACTS = ROOT / "data/facts/screenshot_ocr_index.jsonl"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


def maybe_reexec() -> None:
    if os.environ.get("PADDLEOCR_RAW08_NO_REEXEC") == "1":
        return
    if "paddleocr" in sys.modules:
        return
    if sys.executable != str(VENV_PY) and VENV_PY.exists():
        env = os.environ.copy()
        env["PADDLEOCR_RAW08_NO_REEXEC"] = "1"
        os.execve(str(VENV_PY), [str(VENV_PY), *sys.argv], env)


maybe_reexec()

from paddleocr import PaddleOCR  # noqa: E402


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def iter_images(date: str | None = None) -> list[Path]:
    images = []
    date_tokens = []
    if date:
        date_tokens = [date, date.replace("-", "/")]
    for path in RAW_SCREEN.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
            continue
        if ".stversions" in path.parts or ".conflicts" in path.parts:
            continue
        if date_tokens and not any(token in str(path) for token in date_tokens):
            continue
        images.append(path)
    return sorted(images)


def sidecar_paths(image: Path) -> tuple[Path, Path]:
    return image.with_suffix(image.suffix + ".ocr.md"), image.with_suffix(image.suffix + ".ocr.json")


def get_ocr() -> PaddleOCR:
    return PaddleOCR(
        text_detection_model_name="PP-OCRv6_small_det",
        text_recognition_model_name="PP-OCRv6_small_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def result_payload(image: Path, result: Any, elapsed: float) -> dict[str, Any]:
    rows = []
    for page in result if isinstance(result, list) else [result]:
        getter = page.get if hasattr(page, "get") else lambda key, default=None: getattr(page, key, default)
        texts = getter("rec_texts", [])
        scores = getter("rec_scores", [])
        boxes = getter("rec_boxes", [])
        texts = [] if texts is None else texts
        scores = [] if scores is None else scores
        boxes = [] if boxes is None else boxes
        for idx, text in enumerate(texts):
            score = float(scores[idx]) if idx < len(scores) else None
            box = boxes[idx].tolist() if hasattr(boxes, "tolist") else None
            if hasattr(boxes, "__len__") and idx < len(boxes) and hasattr(boxes[idx], "tolist"):
                box = boxes[idx].tolist()
            rows.append({"index": idx + 1, "text": str(text), "score": score, "box": box})
    useful = [row for row in rows if row["text"].strip()]
    avg_score = round(sum(row["score"] or 0 for row in useful) / len(useful), 4) if useful else 0
    return {
        "schema": "73wiki-paddleocr-raw08-v1",
        "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "engine": "PaddleOCR",
        "ocrVersion": "PP-OCRv6",
        "detModel": "PP-OCRv6_small_det",
        "recModel": "PP-OCRv6_small_rec",
        "image": rel(image),
        "elapsedSeconds": round(elapsed, 3),
        "lineCount": len(useful),
        "avgScore": avg_score,
        "rows": useful,
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# PaddleOCR识别结果：{Path(payload['image']).name}",
        "",
        "```yaml",
        f"createdAt: {payload['createdAt']}",
        f"engine: {payload['engine']}",
        f"ocrVersion: {payload['ocrVersion']}",
        f"detModel: {payload['detModel']}",
        f"recModel: {payload['recModel']}",
        f"image: {payload['image']}",
        f"elapsedSeconds: {payload['elapsedSeconds']}",
        f"lineCount: {payload['lineCount']}",
        f"avgScore: {payload['avgScore']}",
        "status: 本机PaddleOCR自动识别，低分行需人工复核",
        "```",
        "",
        "## 纯文本",
        "",
    ]
    for row in payload["rows"]:
        if row["score"] is not None and row["score"] < 0.6:
            lines.append(f"{row['text']}  # low_score={row['score']:.3f}")
        else:
            lines.append(row["text"])
    lines.extend(["", "## 行明细", "", "| 序号 | 置信度 | 文本 |", "|---:|---:|---|"])
    for row in payload["rows"]:
        score = f"{row['score']:.4f}" if row["score"] is not None else "-"
        lines.append(f"| {row['index']} | {score} | {row['text'].replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def run_one(ocr: PaddleOCR, image: Path, *, force: bool, out_md: Path | None = None, out_json: Path | None = None) -> dict[str, Any]:
    md_path, json_path = sidecar_paths(image)
    if out_md:
        md_path = out_md
    if out_json:
        json_path = out_json
    if md_path.exists() and json_path.exists() and not force:
        return {"image": rel(image), "status": "skipped_exists", "ocr": rel(md_path), "json": rel(json_path)}
    start = time.monotonic()
    result = ocr.predict(str(image))
    payload = result_payload(image, result, time.monotonic() - start)
    md_path.write_text(render_md(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    append_jsonl(FACTS, {
        "schema": "73wiki-screenshot-ocr-index-v1",
        "createdAt": payload["createdAt"],
        "image": payload["image"],
        "ocr": rel(md_path),
        "json": rel(json_path),
        "ocrStatus": "ok_paddleocr",
        "engine": payload["engine"],
        "lineCount": payload["lineCount"],
        "avgScore": payload["avgScore"],
    })
    return {"image": rel(image), "status": "ok", "ocr": rel(md_path), "json": rel(json_path), "lineCount": payload["lineCount"], "avgScore": payload["avgScore"], "elapsedSeconds": payload["elapsedSeconds"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="raw/08 截图 PaddleOCR 本机识别")
    parser.add_argument("--image", action="append", default=[], help="单张或多张图片路径")
    parser.add_argument("--date", help="只处理路径中包含该日期的 raw/08 图片")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out-md")
    parser.add_argument("--out-json")
    args = parser.parse_args()

    explicit_images = bool(args.image)
    images = [Path(item).expanduser() for item in args.image]
    if not images:
        images = iter_images(args.date)
    images = [path if path.is_absolute() else ROOT / path for path in images]
    images = [path for path in images if path.exists() and path.suffix.lower() in IMAGE_EXTS]
    if not explicit_images and not args.force:
        images = [path for path in images if not all(sidecar.exists() for sidecar in sidecar_paths(path))]
    if args.limit > 0:
        images = images[: args.limit]
    if not images:
        print(json.dumps({"ok": True, "reason": "no_new_images", "count": 0}, ensure_ascii=False, indent=2))
        return 0

    ocr = get_ocr()
    rows = []
    for index, image in enumerate(images):
        out_md = Path(args.out_md).expanduser() if args.out_md and len(images) == 1 else None
        out_json = Path(args.out_json).expanduser() if args.out_json and len(images) == 1 else None
        if out_md and not out_md.is_absolute():
            out_md = ROOT / out_md
        if out_json and not out_json.is_absolute():
            out_json = ROOT / out_json
        rows.append(run_one(ocr, image, force=args.force, out_md=out_md, out_json=out_json))
    print(json.dumps({"ok": True, "count": len(rows), "rows": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
