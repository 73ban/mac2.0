#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check local OCR capability for screenshot ingestion."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "wiki/10-系统配置/OCR截图识别能力体检.md"
STATUS = ROOT / ".system/ocr-health.json"
VENV_PY = ROOT / ".venv-ocr/bin/python"
PADDLE_MODELS = [
    Path.home() / ".paddlex/official_models/PP-OCRv6_small_det",
    Path.home() / ".paddlex/official_models/PP-OCRv6_small_rec",
]
RAW_SCREEN = ROOT / "raw/08-截图"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def check_paddleocr() -> dict:
    if not VENV_PY.exists():
        return {"ok": False, "python": "", "version": "", "modelsReady": False, "status": "未安装 .venv-ocr"}
    code = "import paddle, paddleocr; print(paddle.__version__); print(getattr(paddleocr, '__version__', 'unknown'))"
    result = subprocess.run([str(VENV_PY), "-c", code], text=True, capture_output=True, timeout=60)
    lines = (result.stdout or "").splitlines()
    models_ready = all((path / "inference.pdiparams").exists() for path in PADDLE_MODELS)
    ok = result.returncode == 0 and models_ready
    return {
        "ok": ok,
        "python": str(VENV_PY.relative_to(ROOT)),
        "paddleVersion": lines[0] if lines else "",
        "paddleocrVersion": lines[1] if len(lines) > 1 else "",
        "modelsReady": models_ready,
        "models": [str(path) for path in PADDLE_MODELS],
        "status": "可用：PaddleOCR PP-OCRv6 small" if ok else "PaddleOCR安装或模型权重不完整",
    }


def screenshot_sidecar_status() -> dict:
    images = []
    for path in RAW_SCREEN.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
            continue
        if ".stversions" in path.parts or ".conflicts" in path.parts:
            continue
        images.append(path)
    missing = []
    for image in sorted(images):
        md_path = image.with_suffix(image.suffix + ".ocr.md")
        json_path = image.with_suffix(image.suffix + ".ocr.json")
        if not (md_path.exists() and json_path.exists()):
            missing.append(str(image.relative_to(ROOT)))
    ocr_md = sorted(RAW_SCREEN.rglob("*.ocr.md"))
    ocr_json = sorted(RAW_SCREEN.rglob("*.ocr.json"))
    return {
        "imageCount": len(images),
        "ocrMdCount": len(ocr_md),
        "ocrJsonCount": len(ocr_json),
        "missingSidecarCount": len(missing),
        "missingSidecars": missing[:20],
    }


def build() -> dict:
    binary = shutil.which("tesseract")
    version = ""
    ok = False
    if binary:
        result = subprocess.run([binary, "--version"], text=True, capture_output=True)
        ok = result.returncode == 0
        version = (result.stdout or result.stderr).splitlines()[0] if (result.stdout or result.stderr) else ""
    paddle = check_paddleocr()
    sidecars = screenshot_sidecar_status()
    any_ok = ok or paddle["ok"]
    return {
        "schema": "73wiki-ocr-health-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ok": any_ok,
        "tesseract": binary or "",
        "version": version,
        "paddleocr": paddle,
        "raw08Sidecars": sidecars,
        "status": "可直接OCR" if any_ok else "待安装OCR引擎；截图仍可入 raw/08，OCR文本标记为待补。",
    }


def render(payload: dict) -> str:
    return "\n".join(
        [
            "# OCR截图识别能力体检",
            "",
            f"- 生成时间：{payload['generatedAt']}",
            f"- 状态：{payload['status']}",
            f"- tesseract：`{payload['tesseract'] or 'not found'}`",
            f"- version：{payload['version'] or '-'}",
            f"- PaddleOCR：{payload['paddleocr']['status']}",
            f"- PaddleOCR Python：`{payload['paddleocr']['python'] or '-'}`",
            f"- PaddlePaddle：`{payload['paddleocr'].get('paddleVersion') or '-'}`",
            f"- PaddleOCR版本：`{payload['paddleocr'].get('paddleocrVersion') or '-'}`",
            f"- PP-OCRv6 small模型：{'已就绪' if payload['paddleocr'].get('modelsReady') else '未就绪'}",
            f"- raw/08 原图数：{payload['raw08Sidecars'].get('imageCount')}",
            f"- raw/08 `.ocr.md`：{payload['raw08Sidecars'].get('ocrMdCount')}",
            f"- raw/08 `.ocr.json`：{payload['raw08Sidecars'].get('ocrJsonCount')}",
            f"- 缺侧车原图数：{payload['raw08Sidecars'].get('missingSidecarCount')}",
            "",
            "## 使用规则",
            "",
            "- 截图原图仍统一进入 `raw/08-截图`。",
            "- 默认优先使用 PaddleOCR PP-OCRv6 small；少数低置信度、版面复杂图再交给视觉模型复核。",
            "- 自动化规则见 [[截图OCR自动化规则]]。",
            "- OCR 不可用时，不阻塞入库；重要截图后续人工或外部OCR补文本。",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR能力体检")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build()
    if args.write:
        STATUS.parent.mkdir(parents=True, exist_ok=True)
        STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
