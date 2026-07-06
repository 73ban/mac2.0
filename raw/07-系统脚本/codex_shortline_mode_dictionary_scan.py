#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DICT_PATH = ROOT / "data/facts/shortline_mode_dictionary.json"
SCAN_DIRS = [
    ROOT / "raw/09-短线知识",
    ROOT / "raw/11-Codex分析产物/短线知识提炼",
    ROOT / "raw/11-Codex分析产物/超短自进化学习",
    ROOT / "wiki/04-L4交易模式与执行",
    ROOT / "wiki/05-错误库",
    ROOT / "wiki/09-统计与进化",
]
OUT_RAW_DIR = ROOT / f"raw/11-Codex分析产物/短线模式词典/{date.today().isoformat()}"
OUT_WIKI = ROOT / "wiki/04-L4交易模式与执行/模式词典总表.md"


def iter_text_files():
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".md", ".txt", ".json"}:
                yield path


def read_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="ignore")
    return text[:300_000]


def find_hits(text: str, terms: list[str]) -> dict[str, int]:
    hits = {}
    for term in terms:
        if not term:
            continue
        count = len(re.findall(re.escape(term), text))
        if count:
            hits[term] = count
    return hits


def main() -> None:
    dictionary = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    modes = dictionary["modes"]
    stats = {
        mode["standard_name"]: {
            "group": mode["group"],
            "aliases": mode.get("aliases", []),
            "definition": mode.get("definition", ""),
            "count": 0,
            "term_hits": defaultdict(int),
            "files": [],
        }
        for mode in modes
    }

    for path in iter_text_files():
        text = read_text(path)
        rel = path.relative_to(ROOT).as_posix()
        for mode in modes:
            standard = mode["standard_name"]
            terms = [standard] + mode.get("aliases", [])
            hits = find_hits(text, terms)
            if not hits:
                continue
            total = sum(hits.values())
            bucket = stats[standard]
            bucket["count"] += total
            for term, count in hits.items():
                bucket["term_hits"][term] += count
            if len(bucket["files"]) < 12:
                bucket["files"].append({"file": rel, "count": total, "terms": hits})

    ordered = sorted(stats.items(), key=lambda item: item[1]["count"], reverse=True)
    OUT_RAW_DIR.mkdir(parents=True, exist_ok=True)

    json_out = []
    for name, item in ordered:
        json_out.append({
            "standard_name": name,
            "group": item["group"],
            "count": item["count"],
            "aliases": item["aliases"],
            "definition": item["definition"],
            "term_hits": dict(sorted(item["term_hits"].items(), key=lambda kv: kv[1], reverse=True)),
            "files": item["files"],
        })

    (OUT_RAW_DIR / "模式词频扫描.json").write_text(
        json.dumps(json_out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        f"# 短线模式词典扫描-{date.today().isoformat()}",
        "",
        "## 结论",
        "",
        "- 这是从 RAW、短线提炼、错误库、统计与进化、L4交易模式中自动扫描出的模式词频。",
        "- 词频高不代表有效，只代表需要优先整理定义、适用环境、失效条件和交易统计口径。",
        "- 标准名用于统计；别名只用于识别原文叫法。",
        "",
        "## Top 模式",
        "",
        "| 排名 | 标准名 | 分组 | 命中次数 | 主要别名 | 处理动作 |",
        "|---:|---|---|---:|---|---|",
    ]
    for idx, (name, item) in enumerate(ordered, start=1):
        aliases = "、".join(item["aliases"][:5])
        action = "已有样本，优先完善模式页" if item["count"] else "待从淘股吧增量发现"
        lines.append(f"| {idx} | {name} | {item['group']} | {item['count']} | {aliases} | {action} |")

    lines += ["", "## 命中文件样本", ""]
    for name, item in ordered[:20]:
        if not item["files"]:
            continue
        lines.append(f"### {name}")
        for file_hit in item["files"][:6]:
            terms = "、".join(f"{k}:{v}" for k, v in file_hit["terms"].items())
            lines.append(f"- {file_hit['file']}（{terms}）")
        lines.append("")

    (OUT_RAW_DIR / "模式词频扫描.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    wiki_lines = [
        "# 模式词典总表",
        "",
        f"更新日期：{date.today().isoformat()}",
        "",
        "这个文件是交易模式的统一命名层：把淘股吧、游资号和用户复盘中的约定俗成叫法，映射成可统计的标准模式名。",
        "",
        "## 使用规则",
        "",
        "- 交易记录、作战室、D+验证统一写标准名。",
        "- 原文叫法写入“别名/来源语境”，不作为统计主键。",
        "- 每个标准模式必须有独立模式页，持续补充定义、适用环境、失效条件、买卖点、案例、反例和胜率。",
        "- 用户每笔交易至少标注一个主模式，可附加一个辅助模式。",
        "- 用户没有口述模式时，Codex 必须在复盘中推定主模式和辅助模式，并标注“Codex推定”和置信度。",
        "- 模式胜率必须按市场状态、情绪周期、题材阶段、股票角色拆分，不能用一个总胜率代表全部行情。",
        "- 后期修正模式定义、有效条件、失效条件时，只追加修正记录，不删除历史内容。",
        "",
        "## 词典",
        "",
        "| 标准名 | 分组 | 常见别名 | 当前命中 | 定义摘要 |",
        "|---|---|---|---:|---|",
    ]
    for name, item in ordered:
        aliases = "、".join(item["aliases"])
        wiki_lines.append(f"| {name} | {item['group']} | {aliases} | {item['count']} | {item['definition']} |")

    wiki_lines += [
        "",
        "## 下一步",
        "",
        "- 每天扫描新增 RAW，发现新叫法后先进入本词典观察。",
        "- 对命中高、与你交易相关、能被 D+验证的模式，建立或更新独立模式页。",
        "- 对高频但误导交易的叫法，写入错误库并标注反向样本。",
        "",
        f"RAW扫描结果：raw/11-Codex分析产物/短线模式词典/{date.today().isoformat()}/模式词频扫描.md",
    ]
    OUT_WIKI.write_text("\n".join(wiki_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
