#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Score message catalysts from multiple RAW sources into one table."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "raw/11-Codex分析产物/消息催化评分"
WIKI_ROOM = ROOT / "wiki/07-作战室"
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|8\d{5})(?!\d)")

SOURCE_ROOTS = [
    ("财联社", ROOT / "raw/05-研报新闻/财联社"),
    ("公告", ROOT / "raw/05-研报新闻/公告"),
    ("互动易", ROOT / "raw/05-研报新闻/互动问答"),
    ("龙虎榜", ROOT / "raw/04-市场数据/龙虎榜全量"),
    ("公告事件样本", ROOT / "raw/11-Codex分析产物/公告事件样本"),
]

KEYWORDS = {
    "政策": 12,
    "国务院": 14,
    "工信部": 12,
    "订单": 10,
    "中标": 10,
    "涨价": 12,
    "并购": 14,
    "重组": 14,
    "回购": 8,
    "增持": 8,
    "减持": -14,
    "问询": -12,
    "澄清": -10,
    "立案": -18,
    "AI": 5,
    "算力": 7,
    "半导体": 7,
    "机器人": 7,
    "稀土": 7,
    "创新药": 7,
    "龙虎榜": 6,
    "热榜": 5,
    "涨停": 12,
}


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".json":
        try:
            return json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False)
        except Exception:
            pass
    return path.read_text(encoding="utf-8", errors="ignore")


def files_for_date(date: str) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for source, root in SOURCE_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".json"}:
                continue
            if date in str(path) and ".stversions" not in path.parts and ".conflicts" not in path.parts:
                out.append((source, path))
    return out[:1200]


def score_text(source: str, text: str) -> dict[str, Any]:
    hits: list[str] = []
    score = 0
    for key, value in KEYWORDS.items():
        if key.lower() in text.lower():
            hits.append(key)
            score += value
    source_boost = {
        "公告事件样本": 18,
        "公告": 16,
        "互动易": 7,
        "财联社": 8,
        "龙虎榜": 7,
        "同花顺热榜": 4,
        "通达信热榜": 5,
    }.get(source, 0)
    if source == "互动易" and "投资者" in text and not any(key in text for key in ("公司回复", "回复：", "答复", "表示")):
        source_boost -= 8
        hits.append("互动问答未明确回复")
    if source in {"同花顺热榜", "通达信热榜"} and not any(key in text for key in ("今日", "涨停", "异动", "跃迁")):
        source_boost -= 6
        hits.append("热榜旧内容降权")
    if any(key in text for key in ("情绪票", "情绪信号")):
        score += 4
        hits.append("情绪信号")
    if any(key in text for key in ("反向", "负反馈")):
        score -= 14
        hits.append("反向信号")
    score += source_boost
    codes = sorted(set(CODE_RE.findall(text)))[:12]
    freshness = 10
    market_validation = 0
    if "涨停" in text:
        market_validation += 20
    if "热榜" in text or "龙虎榜" in source:
        market_validation += 10
    final = max(0, min(100, score + freshness + market_validation))
    limit_prob = "高" if final >= 75 else "中" if final >= 55 else "低"
    return {
        "score": final,
        "messageStrength": max(0, min(40, score)),
        "themeFreshness": freshness,
        "marketValidation": market_validation,
        "impactCodes": codes,
        "keywords": hits,
        "nextDayLimitUpProbability": limit_prob,
    }


def build(date: str) -> dict[str, Any]:
    rows = []
    for source, path in files_for_date(date):
        try:
            text = read_text(path)
        except Exception:
            continue
        if not text.strip():
            continue
        scored = score_text(source, text[:20000])
        if scored["score"] < 35 and not scored["impactCodes"]:
            continue
        title = path.stem
        for line in text.splitlines()[:30]:
            if line.startswith("# "):
                title = line[2:].strip()
                break
        rows.append({"source": source, "title": title[:120], "path": rel(path), **scored})
    rows.sort(key=lambda item: (-item["score"], item["source"], item["title"]))
    return {
        "schema": "73wiki-message-catalyst-score-v1",
        "date": date,
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rows": rows[:200],
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 消息催化统一评分",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        "",
        "| 分数 | 来源 | 标题 | 强度 | 新鲜度 | 市场验证 | 影响标的 | 次日涨停概率 |",
        "|---:|---|---|---:|---:|---:|---|---|",
    ]
    for row in payload["rows"][:80]:
        lines.append(
            f"| {row['score']} | {row['source']} | {row['title'].replace('|', '/')} | {row['messageStrength']} | {row['themeFreshness']} | {row['marketValidation']} | {', '.join(row['impactCodes']) or '-'} | {row['nextDayLimitUpProbability']} |"
        )
    if not payload["rows"]:
        lines.append("| - | - | 今日无高分消息 | - | - | - | - | - |")
    lines.extend(["", "## 使用规则", "", "- 评分只给线索优先级，不给买入权限。", "- 次日是否有效必须用竞价、涨停、热榜跃迁、板块扩散和 D+验证确认。"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="消息催化统一评分")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    if args.write:
        out = OUT_DIR / args.date
        out.mkdir(parents=True, exist_ok=True)
        (out / "message-catalyst-score.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "message-catalyst-score.md").write_text(render(payload), encoding="utf-8")
        WIKI_ROOM.mkdir(parents=True, exist_ok=True)
        (WIKI_ROOM / f"{args.date}-消息催化统一评分.md").write_text(render(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
