#!/usr/bin/env python3
"""Track fast-rising THS hotlist names and collect likely reasons.

Inputs:
- .llm-wiki/ths-hotlist/latest-ths-hotlist.json
- recent RAW news / WeChat markdown files

Outputs a compact report for manual review and future scoring.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LATEST_THS = ROOT / ".llm-wiki/ths-hotlist/latest-ths-hotlist.json"
OUT_DIR = ROOT / ".llm-wiki/ths-hotlist-movers"
FACTS = ROOT / "data/facts/ths_hotlist_movers.jsonl"
WIKI_ROOM = ROOT / "wiki/07-作战室"
RAW_ROOTS = [
    ROOT / "raw/05-研报新闻",
    ROOT / "raw/04-市场数据",
]


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.open("a", encoding="utf-8").write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def select_movers(rows: list[dict[str, Any]], top: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        rank = int(number(row.get("rank"), 9999))
        change = number(row.get("changePercent"))
        rank_change = number(row.get("hotRankChange"))
        hot_score = number(row.get("hotScore"))
        analyse = clean_text(row.get("analyse"))
        analyse_title = clean_text(row.get("analyseTitle"))
        concept_tags = row.get("conceptTags") if isinstance(row.get("conceptTags"), list) else []
        surprise_score = 0.0
        surprise_score += max(0.0, rank_change) * 4
        surprise_score += max(0.0, change) * 1.5
        surprise_score += max(0.0, 31 - rank) * 0.8
        if analyse or analyse_title:
            surprise_score += 12
        if row.get("popularityTag"):
            surprise_score += 5
        if concept_tags:
            surprise_score += min(8, len(concept_tags) * 3)
        candidates.append(
            {
                "rank": rank,
                "code": row.get("code"),
                "name": row.get("name"),
                "changePercent": change,
                "hotScore": hot_score,
                "hotRankChange": rank_change,
                "popularityTag": row.get("popularityTag") or "",
                "conceptTags": concept_tags,
                "analyseTitle": analyse_title,
                "analyse": analyse,
                "surpriseScore": round(surprise_score, 2),
            }
        )
    candidates.sort(key=lambda item: (item["surpriseScore"], item["hotRankChange"], item["changePercent"]), reverse=True)
    return candidates[:top]


def recent_raw_files(lookback_hours: int) -> list[Path]:
    cutoff = datetime.now() - timedelta(hours=lookback_hours)
    out: list[Path] = []
    for root in RAW_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            if "sync-conflict" in path.name:
                continue
            try:
                if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                    continue
            except OSError:
                continue
            out.append(path)
    return sorted(out, key=lambda item: item.stat().st_mtime, reverse=True)


def snippets_for_name(files: list[Path], name: str, limit: int = 3) -> list[dict[str, str]]:
    if not name:
        return []
    snippets: list[dict[str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        idx = text.find(name)
        if idx < 0:
            continue
        start = max(0, idx - 70)
        end = min(len(text), idx + 180)
        snippet = clean_text(text[start:end])
        snippets.append({"sourcePath": str(path.relative_to(ROOT)), "snippet": snippet})
        if len(snippets) >= limit:
            break
    return snippets


def reason_text(item: dict[str, Any], snippets: list[dict[str, str]]) -> str:
    if item.get("analyseTitle"):
        return item["analyseTitle"]
    if item.get("analyse"):
        return item["analyse"][:120]
    tags = [*item.get("conceptTags", [])]
    if item.get("popularityTag"):
        tags.append(item["popularityTag"])
    if tags:
        return "、".join(tags)
    if snippets:
        return snippets[0]["snippet"][:120]
    return "待补原因：热榜异动但本地资料暂未命中明确催化。"


def render_report(date: str, tracked: list[dict[str, Any]], generated_at: str) -> str:
    lines = [
        f"# {date} 同花顺热榜异动原因跟踪",
        "",
        f"更新时间：{generated_at}",
        "",
        "## 定位",
        "",
        "本页跟踪同花顺热榜里热度/排名/涨幅异动较大的个股，优先寻找预期差催化。",
        "",
        "## 摘要",
        "",
        "```yaml",
        f"tracked: {len(tracked)}",
        f"with_direct_reason: {sum(1 for x in tracked if x.get('analyseTitle') or x.get('analyse'))}",
        f"with_local_evidence: {sum(1 for x in tracked if x.get('localEvidence'))}",
        "```",
        "",
        "| 排名 | 代码 | 名称 | 涨跌幅% | 热榜变化 | 预期差分 | 初步原因 | 本地证据 |",
        "|---:|---|---|---:|---:|---:|---|---|",
    ]
    for item in tracked:
        evidence = item.get("localEvidence") or []
        evidence_text = evidence[0]["sourcePath"] if evidence else "-"
        lines.append(
            f"| {item['rank']} | {item['code']} | {item['name']} | {item['changePercent']:.2f} | {item['hotRankChange']:.0f} | {item['surpriseScore']:.2f} | {item['reason']} | `{evidence_text}` |"
        )
    lines.extend(
        [
            "",
            "## 使用规则",
            "",
            "- 热榜变化大且有清晰原因：纳入作战室复核。",
            "- 热榜变化大但原因不清：飞书/人工优先追问。",
            "- 只有热度没有涨停结构：不直接给买入权限，只加观察权重。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--lookback-hours", type=int, default=36)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    latest = read_json(LATEST_THS, {})
    rows = latest.get("rows", []) if isinstance(latest, dict) else []
    movers = select_movers(rows, args.top)
    files = recent_raw_files(args.lookback_hours)
    tracked = []
    for item in movers:
        evidence = snippets_for_name(files, str(item.get("name") or ""))
        item = {
            **item,
            "localEvidence": evidence,
        }
        item["reason"] = reason_text(item, evidence)
        tracked.append(item)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "schema": "73wiki-ths-hotlist-movers-v1",
        "ok": True,
        "date": args.date,
        "generatedAt": generated_at,
        "sourceSnapshot": latest.get("id") if isinstance(latest, dict) else None,
        "tracked": len(tracked),
        "withDirectReason": sum(1 for x in tracked if x.get("analyseTitle") or x.get("analyse")),
        "withLocalEvidence": sum(1 for x in tracked if x.get("localEvidence")),
        "items": tracked,
        "outputs": {
            "json": ".llm-wiki/ths-hotlist-movers/latest-ths-hotlist-movers.json",
            "md": ".llm-wiki/ths-hotlist-movers/latest-ths-hotlist-movers.md",
            "wiki": f"wiki/07-作战室/{args.date}-同花顺热榜异动原因跟踪.md",
            "facts": "data/facts/ths_hotlist_movers.jsonl",
        },
    }
    if args.write:
        report = render_report(args.date, tracked, generated_at)
        write_json(OUT_DIR / "latest-ths-hotlist-movers.json", payload)
        (OUT_DIR / "latest-ths-hotlist-movers.md").write_text(report, encoding="utf-8")
        (WIKI_ROOM / f"{args.date}-同花顺热榜异动原因跟踪.md").write_text(report, encoding="utf-8")
        append_jsonl(FACTS, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
