#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
WIKI = ROOT / "wiki/08-信息来源/信息来源分层规则.md"
OUT = ROOT / "raw/11-Codex分析产物/信息来源分层"

LAYER_RULES = {
    "公告/互动易": {"layer": "事实确认层", "wiki_target": "wiki/03-L3个股档案、wiki/02-L2方向题材", "use": "确认或否认市场炒作逻辑"},
    "财联社/韭研公社": {"layer": "研报新闻层", "wiki_target": "wiki/02-L2方向题材、wiki/07-作战室", "use": "题材催化、产业链、事件驱动"},
    "淘股吧": {"layer": "情绪/短线语言层", "wiki_target": "wiki/04-L4交易模式、wiki/01-L1市场环境", "use": "情绪周期、模式语言、高手行为"},
    "公众号": {"layer": "游资/产业观点层", "wiki_target": "wiki/04-L4交易模式、wiki/08-信息来源", "use": "观点学习，先RAW后验证"},
    "三榜/热榜": {"layer": "资金关注层", "wiki_target": "wiki/07-作战室、wiki/09-统计与进化", "use": "热度、拥挤度、共振验证"},
}


def classify(path: Path) -> str:
    s = str(path)
    if "互动问答" in s or "公告" in s:
        return "公告/互动易"
    if "韭研公社" in s or "财联社" in s:
        return "财联社/韭研公社"
    if "淘股吧" in s:
        return "淘股吧"
    if "公众号" in s:
        return "公众号"
    if "热榜" in s or "三榜" in s:
        return "三榜/热榜"
    return "其他"


def main() -> int:
    counts = defaultdict(int)
    examples = defaultdict(list)
    for path in RAW.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".jsonl"}:
            continue
        bucket = classify(path)
        counts[bucket] += 1
        if len(examples[bucket]) < 5:
            examples[bucket].append(str(path.relative_to(ROOT)))
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 信息来源分层规则",
        "",
        f"- 生成时间：{generated_at}",
        "- 目的：防止韭研公社、淘股吧、公众号、公告、热榜混层，保证不同资料进入正确wiki层级。",
        "",
        "| 来源 | 层级 | 写入目标 | 使用方式 | 当前RAW数量 |",
        "|---|---|---|---|---:|",
    ]
    for key, rule in LAYER_RULES.items():
        lines.append(f"| {key} | {rule['layer']} | {rule['wiki_target']} | {rule['use']} | {counts.get(key, 0)} |")
    lines += ["", "## 样例", ""]
    for key, vals in sorted(examples.items()):
        lines += [f"### {key}", ""]
        for val in vals:
            lines.append(f"- `{val}`")
        lines.append("")
    WIKI.parent.mkdir(parents=True, exist_ok=True)
    WIKI.write_text("\n".join(lines) + "\n", encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")
    OUT.joinpath(today).mkdir(parents=True, exist_ok=True)
    (OUT / today / "source-layering-audit.json").write_text(json.dumps({"counts": dict(counts), "rules": LAYER_RULES}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(WIKI.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
