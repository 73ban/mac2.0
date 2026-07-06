#!/usr/bin/env python3
"""Backfill OCR sections for historical Youzi公众号 RAW markdown files."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SYSTEM_DIR = ROOT / ".system"
QUALITY_AUDIT = SYSTEM_DIR / "youzi-quality-audit.json"
REPORT_JSON = SYSTEM_DIR / "youzi-ocr-repair-report.json"
REPORT_MD = SYSTEM_DIR / "youzi-ocr-repair-report.md"
INGEST_SCRIPT = ROOT / "raw/07-系统脚本/codex_ingest_werss_api.py"


IMAGE_LINK_RE = re.compile(r"!\[[^\]]*?\]\(([^)]+)\)")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_ingest_module():
    spec = importlib.util.spec_from_file_location("codex_ingest_werss_api", INGEST_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {INGEST_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_frontmatter(text: str) -> tuple[dict[str, str], str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, "", text
    raw = match.group(1)
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, raw, text[match.end() :]


def render_frontmatter(raw: str, updates: dict[str, str]) -> str:
    lines = raw.splitlines()
    seen = set()
    out: list[str] = []
    for line in lines:
        if ":" not in line:
            out.append(line)
            continue
        key = line.split(":", 1)[0].strip()
        if key in updates:
            out.append(f"{key}: {updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}: {value}")
    return "---\n" + "\n".join(out) + "\n---\n"


def unique_image_links(body: str) -> list[str]:
    links: list[str] = []
    seen = set()
    for match in IMAGE_LINK_RE.finditer(body):
        link = match.group(1).strip()
        if link.startswith(("http://", "https://")):
            continue
        if link in seen:
            continue
        seen.add(link)
        links.append(link)
    return links


def resolve_image_path(md_path: Path, link: str) -> Path | None:
    raw = link.split("#", 1)[0].split("?", 1)[0]
    candidate = (md_path.parent / raw).resolve()
    if candidate.exists() and candidate.suffix.lower() in IMAGE_EXTS:
        return candidate
    parent = candidate.parent
    stem = candidate.stem
    if parent.exists():
        matches = [p for p in parent.glob(stem + ".*") if p.suffix.lower() in IMAGE_EXTS]
        if matches:
            return sorted(matches)[0]
    asset_dir = md_path.parent / f"{md_path.stem}_assets"
    if asset_dir.exists():
        matches = [p for p in asset_dir.glob(stem + ".*") if p.suffix.lower() in IMAGE_EXTS]
        if matches:
            return sorted(matches)[0]
    return None


def strip_existing_ocr(body: str) -> str:
    marker = "\n## 图片文字识别\n"
    idx = body.find(marker)
    if idx < 0:
        if body.startswith("## 图片文字识别\n"):
            return ""
        return body.rstrip() + "\n"
    return body[:idx].rstrip() + "\n"


def build_ocr_section(rows: list[dict]) -> str:
    blocks: list[str] = []
    for row in rows:
        text = (row.get("ocr_text") or "").strip()
        if not text:
            continue
        blocks.extend(
            [
                f"### 图片 {row['index']}",
                "",
                f"- 本地图片：{row['markdown_path']}",
                "",
                "OCR文本：",
                "",
                text,
                "",
            ]
        )
    if not blocks:
        return ""
    return "\n## 图片文字识别\n\n" + "\n".join(blocks).rstrip() + "\n"


def repair_file(md_path: Path, ocr_image_file, *, dry_run: bool = False) -> dict:
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    meta, raw_fm, body = parse_frontmatter(text)
    links = unique_image_links(body)
    rows = []
    missing = []
    for index, link in enumerate(links, start=1):
        img_path = resolve_image_path(md_path, link)
        if img_path is None:
            missing.append(link)
            continue
        ocr_text = ocr_image_file(img_path)
        rows.append(
            {
                "index": index,
                "markdown_path": img_path.relative_to(md_path.parent).as_posix(),
                "image_path": img_path.relative_to(ROOT).as_posix(),
                "ocr_text": ocr_text,
                "ocr_chars": len(ocr_text),
            }
        )
    ocr_count = sum(1 for row in rows if row["ocr_text"].strip())
    image_count = len(links)
    changed = False
    if image_count and ocr_count:
        updates = {
            "images_localized": "true",
            "image_count": str(image_count),
            "ocr_image_count": str(ocr_count),
            "ocr_engine": '"rapidocr_onnxruntime"',
            "image_heavy": "true" if image_count > 0 else "false",
            "content_form": '"image_heavy"' if ocr_count else meta.get("content_form", '"image_only"'),
            "updated": now_text().split(" ")[0],
        }
        new_body = strip_existing_ocr(body) + build_ocr_section(rows)
        new_text = render_frontmatter(raw_fm, updates) + "\n" + new_body.lstrip("\n")
        changed = new_text != text
        if changed and not dry_run:
            md_path.write_text(new_text, encoding="utf-8")
    return {
        "raw_rel": md_path.relative_to(ROOT).as_posix(),
        "image_count": image_count,
        "resolved_images": len(rows),
        "missing_images": missing,
        "ocr_image_count": ocr_count,
        "ocr_chars": sum(row["ocr_chars"] for row in rows),
        "changed": changed and not dry_run,
        "would_change": changed,
    }


def candidate_paths(limit: int | None) -> list[Path]:
    audit = load_json(QUALITY_AUDIT, {})
    paths: list[Path] = []
    seen = set()
    for item in audit.get("image_repair_queue", []):
        rel = item.get("raw_rel")
        if not rel or "sync-conflict" in rel:
            continue
        path = ROOT / rel
        if not path.exists() or path.suffix.lower() != ".md":
            continue
        key = path.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
        if limit is not None and len(paths) >= limit:
            break
    return paths


def write_report(result: dict) -> None:
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# 游资图片 OCR 修复报告",
        "",
        f"- 生成时间：{result['generated_at']}",
        f"- dry_run：{result['dry_run']}",
        f"- 候选文件：{result['summary']['candidates']}",
        f"- 写入文件：{result['summary']['changed']}",
        f"- OCR 图片：{result['summary']['ocr_images']}",
        f"- OCR 字符：{result['summary']['ocr_chars']}",
        "",
        "| RAW | 图片 | OCR | 字符 | 状态 |",
        "|---|---:|---:|---:|---|",
    ]
    for row in result["files"][:200]:
        status = "changed" if row["changed"] else ("would_change" if row["would_change"] else "unchanged")
        lines.append(
            f"| {row['raw_rel']} | {row['image_count']} | {row['ocr_image_count']} | {row['ocr_chars']} | {status} |"
        )
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ingest = load_ingest_module()
    paths = candidate_paths(args.limit)
    rows = [repair_file(path, ingest.ocr_image_file, dry_run=args.dry_run) for path in paths]
    result = {
        "generated_at": now_text(),
        "dry_run": args.dry_run,
        "summary": {
            "candidates": len(paths),
            "changed": sum(1 for row in rows if row["changed"]),
            "would_change": sum(1 for row in rows if row["would_change"]),
            "ocr_images": sum(row["ocr_image_count"] for row in rows),
            "ocr_chars": sum(row["ocr_chars"] for row in rows),
            "missing_images": sum(len(row["missing_images"]) for row in rows),
        },
        "files": rows,
    }
    if not args.dry_run:
        write_report(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
