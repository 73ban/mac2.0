#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
from collections import Counter
from pathlib import Path


ROOT = Path("/Users/qixinchaye/wiki/73神话")
HOTLIST_ROOT = ROOT / "raw/04-市场数据/热榜"
OUT_ROOT = ROOT / "raw/11-Codex分析产物/短线知识提炼"
WIKI_QUEUE = ROOT / "wiki/09-统计与进化/淘股吧情绪周期验证队列.md"


WORD_GROUPS = {
    "一致高潮": ["高潮", "一致", "逼空", "抢筹", "踏空", "买不到", "上车", "加速", "爆发", "无脑", "主升", "躺赢"],
    "分歧": ["分歧", "换手", "炸板", "开板", "分化", "承接", "去弱留强", "汰弱留强", "兑现", "冲高回落"],
    "退潮恐慌": ["退潮", "冰点", "核按钮", "大面", "天地板", "跌停", "杀跌", "亏钱效应", "崩", "闷杀", "补跌", "血亏"],
    "修复": ["修复", "反核", "弱转强", "回流", "止跌", "企稳", "反包", "低吸", "轮动", "回暖"],
    "观望防守": ["空仓", "管住手", "等一等", "看戏", "防守", "降低仓位", "控制仓位", "休息", "不出手"],
}


TOPIC_WORDS = [
    "机器人", "半导体", "芯片", "CPO", "PCB", "液冷", "算力", "AI", "光模块", "存储",
    "军工", "稀土", "有色", "锂电", "固态电池", "消费", "白酒", "医药", "创新药",
    "电力", "核电", "光伏", "风电", "数据中心", "华为", "国企改革", "低空经济",
]


def today() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def load_hotlist(date: str, slot: str | None) -> tuple[dict, Path]:
    day_dir = HOTLIST_ROOT / date
    if slot:
        path = day_dir / f"淘股吧热榜100-{slot}.json"
    else:
        path = day_dir / "淘股吧热榜100-latest.json"
    if not path.exists():
        raise FileNotFoundError(f"淘股吧热榜JSON不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8")), path


def clean_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def joined_discussion_text(discussions: list[dict]) -> str:
    parts = []
    for item in discussions:
        parts.append(clean_text(item.get("主题")))
        parts.append(clean_text(item.get("摘要")))
        parts.append(clean_text(item.get("主帖标题")))
        for stock in item.get("谈及股票") or []:
            parts.append(clean_text(stock.get("名称")))
        for concept in item.get("谈及概念") or []:
            parts.append(clean_text(concept.get("概念名称")))
    return "\n".join([p for p in parts if p])


def count_word_groups(text: str) -> dict[str, int]:
    result = {}
    for group, words in WORD_GROUPS.items():
        result[group] = sum(text.count(word) for word in words)
    return result


def top_topics(text: str) -> list[dict]:
    counter = Counter()
    for word in TOPIC_WORDS:
        count = len(re.findall(re.escape(word), text, flags=re.I))
        if count:
            counter[word] += count
    return [{"题材": k, "出现次数": v} for k, v in counter.most_common(20)]


def discussion_stock_crowding(discussions: list[dict]) -> list[dict]:
    counter = Counter()
    for item in discussions:
        seen = set()
        for stock in item.get("谈及股票") or []:
            code = stock.get("代码") or ""
            name = stock.get("名称") or ""
            if code or name:
                seen.add((code, name))
        for key in seen:
            counter[key] += 1
    return [
        {"排名": idx, "代码": code, "名称": name, "讨论出现次数": count}
        for idx, ((code, name), count) in enumerate(counter.most_common(30), 1)
    ]


def stock_hot_crowding(stocks: list[dict]) -> list[dict]:
    counter = Counter()
    meta: dict[tuple[str, str], dict] = {}
    for item in stocks:
        key = (item.get("代码") or "", item.get("名称") or "")
        if key == ("", ""):
            continue
        counter[key] += 1
        current = meta.get(key, {})
        candidate = {
            "涨跌幅": item.get("涨跌幅"),
            "连板标记": item.get("连板标记"),
            "成交额": item.get("成交额"),
        }
        meta[key] = {
            field: current.get(field) if current.get(field) not in (None, "") else candidate.get(field)
            for field in ("涨跌幅", "连板标记", "成交额")
        }
    return [
        {
            "排名": idx,
            "代码": code,
            "名称": name,
            "热榜出现榜单数": count,
            **meta.get((code, name), {}),
        }
        for idx, ((code, name), count) in enumerate(counter.most_common(30), 1)
    ]


def emotion_stage(scores: dict[str, int], discussions_count: int) -> tuple[str, str]:
    if discussions_count <= 0:
        return "数据不足", "热门讨论为空，不能判断淘股吧情绪。"
    climax = scores["一致高潮"]
    panic = scores["退潮恐慌"]
    divergence = scores["分歧"]
    repair = scores["修复"]
    defense = scores["观望防守"]

    if panic >= max(climax, divergence, repair, defense) and panic >= 5:
        return "退潮/恐慌", "退潮恐慌词占优，重点看核按钮、补跌、天地板和亏钱效应是否扩散。"
    if climax >= max(panic, divergence, repair, defense) and climax >= 5:
        return "一致高潮/踏空", "一致高潮词占优，重点警惕次日分歧和后排补涨追高。"
    if divergence >= max(panic, climax, repair, defense) and divergence >= 5:
        return "分歧", "分歧词占优，重点看核心承接、去弱留强和主线是否回流。"
    if repair >= max(panic, climax, divergence, defense) and repair >= 4:
        return "修复/回流", "修复词占优，重点验证反核、弱转强、回流是否从局部扩散到板块。"
    if defense >= 3:
        return "观望/防守", "观望防守词较多，市场参与者出手意愿偏低。"
    return "混沌/弱信号", "情绪词没有明显单边占优，需要结合连板天梯、涨跌停和成交额验证。"


def disagreement_index(scores: dict[str, int]) -> float:
    active = scores["一致高潮"] + scores["退潮恐慌"] + scores["分歧"] + scores["修复"]
    if active <= 0:
        return 0.0
    bull = scores["一致高潮"] + scores["修复"]
    bear = scores["退潮恐慌"]
    div = scores["分歧"]
    balance = 1.0 - abs(bull - bear) / max(active, 1)
    return round(min(1.0, max(0.0, balance * 0.7 + min(div / active, 1.0) * 0.3)), 3)


def entropy(items: list[dict], key: str) -> float:
    counts = [float(item.get(key) or 0) for item in items if float(item.get(key) or 0) > 0]
    total = sum(counts)
    if total <= 0:
        return 0.0
    return round(-sum((c / total) * math.log(c / total, 2) for c in counts), 3)


def build_analysis(payload: dict, input_path: Path) -> dict:
    meta = payload.get("元数据") or {}
    discussions = payload.get("热门讨论100") or []
    stocks = payload.get("股票热榜") or []
    text = joined_discussion_text(discussions)
    scores = count_word_groups(text)
    stage, stage_reason = emotion_stage(scores, len(discussions))
    discussion_crowding = discussion_stock_crowding(discussions)
    hot_crowding = stock_hot_crowding(stocks)
    topic_rank = top_topics(text)
    return {
        "元数据": {
            "数据源": "淘股吧",
            "分析类型": "淘股吧情绪周期",
            "日期": meta.get("日期"),
            "时段": meta.get("时段"),
            "生成时间": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(),
            "输入文件": str(input_path.relative_to(ROOT)),
            "热门讨论条数": len(discussions),
            "股票热榜条数": len(stocks),
            "证据等级": "S3，市场情绪辅助层；必须被盘面和D+验证确认",
        },
        "情绪阶段初判": stage,
        "阶段理由": stage_reason,
        "情绪词计数": scores,
        "分歧度0到1": disagreement_index(scores),
        "题材词排行": topic_rank,
        "讨论股票拥挤度": discussion_crowding,
        "股票热榜拥挤度": hot_crowding,
        "拥挤度指标": {
            "讨论股票熵": entropy(discussion_crowding, "讨论出现次数"),
            "热榜股票熵": entropy(hot_crowding, "热榜出现榜单数"),
            "解释": "熵越低，讨论越集中；熵越高，轮动越散。"
        },
        "验证要求": [
            "D+1看高频股票是否有溢价、修复或负反馈。",
            "D+3看高频题材是否仍有板块生命力。",
            "D+5看情绪阶段判断是否延续、反转或失效。",
            "不能单独用淘股吧情绪做买入理由，必须叠加连板天梯、涨跌停、板块强度、成交额Top100、作战室规则。"
        ]
    }


def md_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell if cell is not None else "").replace("|", "/") for cell in row) + " |")
    return "\n".join(lines)


def write_markdown(path: Path, analysis: dict) -> None:
    meta = analysis["元数据"]
    lines = [
        f"# {meta['日期']} 淘股吧情绪周期判断（{meta['时段']}）",
        "",
        "## 结论",
        "",
        f"- 阶段初判：{analysis['情绪阶段初判']}",
        f"- 理由：{analysis['阶段理由']}",
        f"- 分歧度：{analysis['分歧度0到1']}",
        f"- 输入文件：`{meta['输入文件']}`",
        f"- 证据等级：{meta['证据等级']}",
        "",
        "## 情绪词计数",
        "",
        md_table(["类别", "出现次数"], [[k, v] for k, v in analysis["情绪词计数"].items()]),
        "",
        "## 题材词排行",
        "",
        md_table(["题材", "出现次数"], [[x["题材"], x["出现次数"]] for x in analysis["题材词排行"][:20]]),
        "",
        "## 讨论股票拥挤度",
        "",
        md_table(
            ["排名", "代码", "名称", "讨论出现次数"],
            [[x["排名"], x["代码"], x["名称"], x["讨论出现次数"]] for x in analysis["讨论股票拥挤度"][:20]],
        ),
        "",
        "## 股票热榜拥挤度",
        "",
        md_table(
            ["排名", "代码", "名称", "榜单数", "涨跌幅", "连板标记"],
            [[x["排名"], x["代码"], x["名称"], x["热榜出现榜单数"], x.get("涨跌幅"), x.get("连板标记")] for x in analysis["股票热榜拥挤度"][:20]],
        ),
        "",
        "## D+验证要求",
        "",
    ]
    lines.extend([f"- {x}" for x in analysis["验证要求"]])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_queue(analysis: dict, md_path: Path) -> None:
    meta = analysis["元数据"]
    WIKI_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    if not WIKI_QUEUE.exists():
        WIKI_QUEUE.write_text(
            "\n".join(
                [
                    "# 淘股吧情绪周期验证队列",
                    "",
                    "本页只跟踪淘股吧情绪层判断是否被后续盘面验证，不把淘股吧讨论直接当买入依据。",
                    "",
                    "| 入队日期 | 时段 | 情绪阶段 | 分歧度 | 关键证据 | D+1 | D+3 | D+5 | 结论 |",
                    "|---|---:|---|---:|---|---|---|---|---|",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    line = (
        f"| {meta['日期']} | {meta['时段']} | {analysis['情绪阶段初判']} | {analysis['分歧度0到1']} | "
        f"`{md_path.relative_to(ROOT)}` | 待验证 | 待验证 | 待验证 | 待回填 |\n"
    )
    existing = WIKI_QUEUE.read_text(encoding="utf-8")
    if line not in existing:
        with WIKI_QUEUE.open("a", encoding="utf-8") as f:
            f.write(line)


def run(date: str, slot: str | None) -> dict:
    payload, input_path = load_hotlist(date, slot)
    analysis = build_analysis(payload, input_path)
    slot_value = analysis["元数据"].get("时段") or slot or "latest"
    out_dir = OUT_ROOT / date
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"淘股吧情绪周期-{slot_value}.json"
    md_path = out_dir / f"淘股吧情绪周期-{slot_value}.md"
    json_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(md_path, analysis)
    latest_json = out_dir / "淘股吧情绪周期-latest.json"
    latest_md = out_dir / "淘股吧情绪周期-latest.md"
    latest_json.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(latest_md, analysis)
    append_queue(analysis, md_path)
    return {"json": str(json_path), "md": str(md_path), "stage": analysis["情绪阶段初判"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="基于淘股吧热榜100生成情绪周期判断。")
    parser.add_argument("--date", default=today())
    parser.add_argument("--slot")
    args = parser.parse_args()
    print(json.dumps(run(args.date, args.slot), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
