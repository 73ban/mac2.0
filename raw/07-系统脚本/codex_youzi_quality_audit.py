import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SYSTEM_DIR = ROOT / ".system"
DEFAULT_STATE = SYSTEM_DIR / "youzi-learning-state.json"
DEFAULT_AUDIT_JSON = SYSTEM_DIR / "youzi-quality-audit.json"
DEFAULT_AUDIT_MD = SYSTEM_DIR / "youzi-quality-audit.md"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def rel_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def score_priority(item: dict) -> int:
    validation = item.get("validation", {})
    body_length = int(validation.get("body_length", 0) or 0)
    image_count = int(validation.get("image_count", 0) or 0)
    ocr_count = int(validation.get("ocr_image_count", 0) or 0)
    score = 0
    score += 3 if validation.get("level") == "low" else 1
    score += 3 if image_count > 0 and ocr_count < image_count else 0
    score += 2 if item.get("content_form") in {"image_heavy", "image_only"} else 0
    score += 1 if body_length < 600 else 0
    return score


def build_audit(items: list[dict]) -> dict:
    low_quality = []
    image_repair = []
    source_counter = Counter()
    source_low_counter = Counter()

    for item in items:
        validation = item.get("validation", {})
        level = validation.get("level", "")
        image_count = int(validation.get("image_count", 0) or 0)
        ocr_count = int(validation.get("ocr_image_count", 0) or 0)
        source = item.get("source", "")
        source_counter[source] += 1
        needs_repair = image_count > 0 and ocr_count < image_count
        if level == "low":
            source_low_counter[source] += 1
        if level == "low" or item.get("content_form") in {"image_heavy", "image_only"} or needs_repair:
            row = {
                "source": source,
                "date": item.get("date", ""),
                "title": item.get("title", ""),
                "raw_rel": item.get("raw_rel", ""),
                "card_rel": item.get("card_rel", ""),
                "content_form": item.get("content_form", ""),
                "validation": validation,
                "priority": score_priority(item),
            }
            low_quality.append(row)
        if needs_repair:
            image_repair.append(
                {
                    "source": source,
                    "date": item.get("date", ""),
                    "title": item.get("title", ""),
                    "raw_rel": item.get("raw_rel", ""),
                    "card_rel": item.get("card_rel", ""),
                    "image_count": image_count,
                    "ocr_image_count": ocr_count,
                    "ocr_gap": image_count - ocr_count,
                    "priority": score_priority(item),
                }
            )

    low_quality.sort(key=lambda item: (item["priority"], item["date"], item["title"]), reverse=True)
    image_repair.sort(key=lambda item: (item["priority"], item["ocr_gap"], item["date"]), reverse=True)

    return {
        "generated_at": now_text(),
        "summary": {
            "cards": len(items),
            "low_quality": len(low_quality),
            "image_repair_queue": len(image_repair),
            "sources_with_low_quality": len(source_low_counter),
        },
        "top_sources": source_counter.most_common(20),
        "top_low_quality_sources": source_low_counter.most_common(20),
        "low_quality": low_quality[:400],
        "image_repair_queue": image_repair[:400],
    }


def write_markdown(path: Path, audit: dict) -> None:
    lines = [
        "# 游资质量审计",
        "",
        f"- 生成时间：{audit['generated_at']}",
        f"- 学习卡总数：{audit['summary']['cards']}",
        f"- 低质量候选：{audit['summary']['low_quality']}",
        f"- 图片/OCR补强队列：{audit['summary']['image_repair_queue']}",
        f"- 低质量来源数：{audit['summary']['sources_with_low_quality']}",
        "",
        "## 低质量来源",
        "",
        "| 来源 | 低质量数 |",
        "|---|---:|",
    ]
    for source, count in audit["top_low_quality_sources"]:
        lines.append(f"| {source} | {count} |")
    if len(lines) == 10:
        lines.append("| 无 | 0 |")

    lines += [
        "",
        "## 优先补强队列",
        "",
        "| 来源 | 日期 | 标题 | 形态 | OCR | 等级 | RAW | 学习卡 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in audit["low_quality"][:200]:
        validation = item["validation"]
        lines.append(
            f"| {item['source']} | {item['date']} | {item['title'][:80]} | {item['content_form']} | "
            f"{validation.get('ocr_image_count', 0)}/{validation.get('image_count', 0)} | {validation.get('level', '')} | "
            f"{item['raw_rel']} | {item['card_rel']} |"
        )
    if len(lines) == 16:
        lines.append("| 无 | - | - | - | - | - | - | - |")

    lines += [
        "",
        "## 图片补强队列",
        "",
        "| 来源 | 日期 | 标题 | 图片数 | OCR数 | 缺口 | RAW |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for item in audit["image_repair_queue"][:200]:
        lines.append(
            f"| {item['source']} | {item['date']} | {item['title'][:80]} | {item['image_count']} | "
            f"{item['ocr_image_count']} | {item['ocr_gap']} | {item['raw_rel']} |"
        )
    if len(lines) == 22:
        lines.append("| 无 | - | - | 0 | 0 | 0 | - |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    global ROOT, SYSTEM_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--audit-json", default=str(DEFAULT_AUDIT_JSON))
    parser.add_argument("--audit-md", default=str(DEFAULT_AUDIT_MD))
    args = parser.parse_args()

    ROOT = Path(args.root)
    SYSTEM_DIR = ROOT / ".system"
    state = load_json(Path(args.state), {"items": []})
    audit = build_audit(list(state.get("items", [])))
    save_json(Path(args.audit_json), audit)
    write_markdown(Path(args.audit_md), audit)
    payload = json.dumps(audit, ensure_ascii=False, indent=2)
    try:
        print(payload)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe = payload.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
