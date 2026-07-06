#!/usr/bin/env python3
"""Extract platform Top10 hot-stock lists from WeChat MP RAW articles.

Targets lines like:
  淘股吧:1.贤丰控股2.威派格...
  同花顺:1.京东方A2.长电科技...
  东方财富:1.多氟多2.惠科股份...
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_MP = ROOT / "raw/05-研报新闻/公众号"
FACTS = ROOT / "data/facts/mp_hot_top10_snapshots.jsonl"
OUT_DIR = ROOT / ".llm-wiki/mp-hot-top10"
WIKI_OUT = ROOT / "wiki/09-统计与进化/公众号三榜Top10交叉验证.md"
PLATFORMS = ("淘股吧", "同花顺", "东方财富")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.open("a", encoding="utf-8").write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def title_from_text(text: str) -> str:
    match = re.search(r'^title:\s*"?([^"\n]+)"?\s*$', text, re.M)
    if match:
        return match.group(1).strip()
    match = re.search(r"^#\s+(.+)$", text, re.M)
    return match.group(1).strip() if match else ""


def date_from_path(path: Path) -> str:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
    return match.group(1) if match else ""


def split_ranked_names(value: str) -> list[dict[str, Any]]:
    text = re.sub(r"\s+", "", value.strip())
    text = text.replace("Ｎ", "N")
    matches = list(re.finditer(r"(\d{1,2})[.、．)]", text))
    rows: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        rank = int(match.group(1))
        if rank < 1 or rank > 10:
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        name = text[start:end].strip(" ，,;；。")
        if not name:
            continue
        rows.append({"rank": rank, "name": name})
    return rows[:10]


def extract_blocks(text: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for line in text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        for platform in PLATFORMS:
            match = re.match(rf"^{platform}\s*[:：]\s*(.+)$", clean)
            if not match:
                continue
            rows = split_ranked_names(match.group(1))
            if rows:
                out[platform] = rows
    return out


def candidate_files(days: int) -> list[Path]:
    cutoff = datetime.now() - timedelta(days=days)
    files: list[Path] = []
    for path in RAW_MP.rglob("*.md"):
        if "sync-conflict" in path.name:
            continue
        if "淘股吧" not in str(path):
            continue
        try:
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                continue
        except OSError:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.stat().st_mtime, reverse=True)


def build_report(records: list[dict[str, Any]], generated_at: str) -> str:
    latest_by_platform: dict[str, dict[str, Any]] = {}
    for record in records:
        for platform, rows in record.get("platforms", {}).items():
            current = latest_by_platform.get(platform)
            candidate = {
                "articleDate": record.get("articleDate", ""),
                "title": record.get("title", ""),
                "sourcePath": record.get("sourcePath", ""),
                "rows": rows,
            }
            if current is None:
                latest_by_platform[platform] = candidate
                continue
            current_complete = len(current.get("rows", [])) >= 8
            candidate_complete = len(rows) >= 8
            if candidate_complete and not current_complete:
                latest_by_platform[platform] = {
                    "articleDate": record.get("articleDate", ""),
                    "title": record.get("title", ""),
                    "sourcePath": record.get("sourcePath", ""),
                    "rows": rows,
                }
    lines = [
        "# 公众号三榜Top10交叉验证",
        "",
        f"更新时间：{generated_at}",
        "",
        "## 摘要",
        "",
        "```yaml",
        f"source_articles: {len(records)}",
        f"platforms_found: {len(latest_by_platform)}",
        "```",
        "",
    ]
    for platform in PLATFORMS:
        item = latest_by_platform.get(platform)
        lines.append(f"## {platform}")
        lines.append("")
        if not item:
            lines.append("- 暂无可解析榜单。")
            lines.append("")
            continue
        lines.append(f"- 日期：{item['articleDate']}")
        lines.append(f"- 文章：{item['title']}")
        lines.append(f"- RAW：`{item['sourcePath']}`")
        lines.append(f"- 完整度：{len(item['rows'])}/10")
        lines.append("")
        lines.append("| 排名 | 名称 |")
        lines.append("|---:|---|")
        for row in item["rows"]:
            lines.append(f"| {row.get('rank')} | {row.get('name')} |")
        lines.append("")
    lines.extend(
        [
            "## 用法",
            "",
            "- 与同花顺 API Top100、通达信 Top100 交叉验证。",
            "- 三榜同时出现的票，作为人气共振样本；只有公众号出现但 API 不出现的票，降权或人工复核。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    records: list[dict[str, Any]] = []
    for path in candidate_files(args.days):
        text = read_text(path)
        platforms = extract_blocks(text)
        if not platforms:
            continue
        records.append(
            {
                "articleDate": date_from_path(path),
                "title": title_from_text(text),
                "sourcePath": str(path.relative_to(ROOT)),
                "platforms": platforms,
            }
        )
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "schema": "73wiki-mp-hot-top10-extract-v1",
        "ok": True,
        "generatedAt": generated_at,
        "lookbackDays": args.days,
        "recordCount": len(records),
        "completeRecordCount": sum(
            1
            for record in records
            for rows in record.get("platforms", {}).values()
            if len(rows) >= 8
        ),
        "platformCount": len({platform for record in records for platform in record.get("platforms", {})}),
        "records": records,
        "outputs": {
            "json": ".llm-wiki/mp-hot-top10/latest-mp-hot-top10.json",
            "md": ".llm-wiki/mp-hot-top10/latest-mp-hot-top10.md",
            "wiki": "wiki/09-统计与进化/公众号三榜Top10交叉验证.md",
            "facts": "data/facts/mp_hot_top10_snapshots.jsonl",
        },
    }
    if args.write:
        write_json(OUT_DIR / "latest-mp-hot-top10.json", payload)
        (OUT_DIR / "latest-mp-hot-top10.md").write_text(build_report(records, generated_at), encoding="utf-8")
        WIKI_OUT.write_text(build_report(records, generated_at), encoding="utf-8")
        append_jsonl(FACTS, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
