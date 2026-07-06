#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从本机公告 RAW 中提取 Codex 初筛结果。"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|43\d{4}|83\d{4}|87\d{4}|92\d{4})(?!\d)")

POSITIVE_WORDS = ["业绩预增", "扭亏", "中标", "重大合同", "回购", "增持", "并购", "重组", "资产注入", "定增", "订单"]
RISK_WORDS = ["减持", "立案", "问询", "关注函", "监管函", "异动公告", "澄清", "亏损", "业绩修正", "终止", "风险提示"]


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def iter_records(obj: Any):
    if isinstance(obj, list):
        for item in obj:
            yield from iter_records(item)
    elif isinstance(obj, dict):
        if any(k in obj for k in ("公告标题", "title", "股票代码", "code", "公司名称", "name")):
            yield obj
        for key in ("数据", "记录", "公告", "items", "records", "data", "result", "list"):
            value = obj.get(key)
            if isinstance(value, (list, dict)):
                yield from iter_records(value)


def pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def normalize(row: dict[str, Any]) -> dict[str, Any]:
    title = clean(pick(row, "公告标题", "title", "标题"))
    code = clean(pick(row, "股票代码", "code", "证券代码"))
    if not CODE_RE.fullmatch(code):
        found = CODE_RE.search(json.dumps(row, ensure_ascii=False))
        code = found.group(0) if found else code
    name = clean(pick(row, "公司名称", "name", "股票名称", "证券简称"))
    date = clean(pick(row, "公告日期", "date", "日期", "time"))
    brief = clean(pick(row, "公告摘要", "brief", "摘要", "content"))
    category = pick(row, "分类标签", "category", "分类")
    if isinstance(category, str):
        category = [category] if category else []
    elif not isinstance(category, list):
        category = []
    keywords = pick(row, "命中关键词", "查询关键词", "keyword")
    if isinstance(keywords, str):
        keywords = [keywords] if keywords else []
    elif not isinstance(keywords, list):
        keywords = []
    return {
        "公告标题": title,
        "公司名称": name,
        "股票代码": code,
        "公告日期": date,
        "分类标签": [clean(x) for x in category if clean(x)],
        "命中关键词": [clean(x) for x in keywords if clean(x)],
        "公告摘要": brief,
        "公告链接": clean(pick(row, "公告链接", "url", "link")),
        "原始字段": row,
    }


def dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row.get("股票代码", ""), row.get("公告标题", ""), row.get("公告日期", ""))
        if key not in merged:
            merged[key] = row
            continue
        old = merged[key]
        old["分类标签"] = sorted(set(old.get("分类标签", []) + row.get("分类标签", [])))
        old["命中关键词"] = sorted(set(old.get("命中关键词", []) + row.get("命中关键词", [])))
    return list(merged.values())


def load_codes_from_json(path: Path, date: str, keys: list[str]) -> set[str]:
    payload = read_json(path, {})
    text = json.dumps(payload, ensure_ascii=False)
    return set(CODE_RE.findall(text))


def load_context_codes(date: str) -> dict[str, set[str]]:
    return {
        "同花顺热榜": load_codes_from_json(RAW / "04-市场数据" / "同花顺热榜" / date / "ths-hot-top100.json", date, []),
        "通达信热榜": load_codes_from_json(RAW / "04-市场数据" / "通达信热榜" / date / "tdx-hot-top100.json", date, []),
        "成交额Top100": load_codes_from_json(RAW / "04-市场数据" / "通达信成交额排名" / date / "tdx-成交额Top100.json", date, []),
        "涨停全景": load_codes_from_json(RAW / "04-市场数据" / "每日涨停全景" / date / "tdx-daily-limit.json", date, []),
        "连板天梯": load_codes_from_json(RAW / "04-市场数据" / "通达信连板天梯" / date / "tdx-limit-ladder.json", date, []),
    }


def classify(row: dict[str, Any], context: dict[str, set[str]]) -> dict[str, Any]:
    code = row.get("股票代码", "")
    text = f"{row.get('公告标题','')} {row.get('公告摘要','')} {' '.join(row.get('分类标签', []))}"
    tags = []
    for name, codes in context.items():
        if code and code in codes:
            tags.append(name)
    risk_hits = [word for word in RISK_WORDS if word in text]
    positive_hits = [word for word in POSITIVE_WORDS if word in text]
    priority = 0
    priority += len(tags) * 20
    priority += len(risk_hits) * 12
    priority += len(positive_hits) * 8
    if "连板天梯" in tags:
        priority += 20
    if "涨停全景" in tags:
        priority += 12
    if not tags and not risk_hits and not positive_hits:
        priority -= 5
    return {
        **row,
        "关联标签": tags,
        "风险关键词": risk_hits,
        "正向关键词": positive_hits,
        "初筛分": priority,
        "处理建议": "次日重点复核" if priority >= 25 else ("风险留意" if risk_hits else "归档观察"),
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['日期']} 公告催化初筛",
        "",
        f"- 生成时间：{payload['生成时间']}",
        f"- 原始公告数：{payload['原始公告数']}",
        f"- 去重后公告数：{payload['去重后公告数']}",
        "",
        "## 高优先公告",
        "",
        "| 分数 | 代码 | 公司 | 分类 | 标题 | 关联 | 风险词 | 正向词 | 建议 |",
        "|---:|---|---|---|---|---|---|---|---|",
    ]
    for row in payload["高优先公告"][:50]:
        lines.append(
            "| {score} | {code} | {name} | {cat} | {title} | {tags} | {risk} | {pos} | {adv} |".format(
                score=row.get("初筛分", ""),
                code=row.get("股票代码", ""),
                name=row.get("公司名称", ""),
                cat="、".join(row.get("分类标签", [])),
                title=row.get("公告标题", ""),
                tags="、".join(row.get("关联标签", [])),
                risk="、".join(row.get("风险关键词", [])),
                pos="、".join(row.get("正向关键词", [])),
                adv=row.get("处理建议", ""),
            )
        )
    lines += [
        "",
        "## 使用边界",
        "",
        "- 这是公告初筛，不是买入建议。",
        "- 高分公告必须继续看次日竞价、涨停结构、成交额和资金流。",
        "- 减持、问询、立案、异动澄清优先进入风险复核。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="公告RAW催化初筛")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    source = RAW / "05-研报新闻" / "公告" / args.date / "daily-announcements.json"
    raw_payload = read_json(source, {})
    raw_rows = [normalize(x) for x in iter_records(raw_payload)]
    rows = dedupe(raw_rows)
    context = load_context_codes(args.date)
    scored = [classify(row, context) for row in rows]
    scored.sort(key=lambda item: item.get("初筛分", 0), reverse=True)
    payload = {
        "日期": args.date,
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "数据源": str(source.relative_to(ROOT)),
        "原始公告数": len(raw_rows),
        "去重后公告数": len(rows),
        "上下文命中数量": {key: len(value) for key, value in context.items()},
        "高优先公告": [row for row in scored if row.get("初筛分", 0) >= 20],
        "全部公告": scored,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.write:
        out_dir = RAW / "11-Codex分析产物" / "公告催化" / args.date
        write_json(out_dir / "公告催化初筛.json", payload)
        (out_dir / "公告催化初筛.md").write_text(render_md(payload), encoding="utf-8")
        wiki_path = ROOT / "wiki" / "07-作战室" / f"{args.date}-公告催化初筛.md"
        wiki_path.write_text(render_md(payload), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
