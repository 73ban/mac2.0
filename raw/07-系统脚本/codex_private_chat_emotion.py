#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path("/Users/qixinchaye/wiki/73神话")
RAW_ROOT = ROOT / "raw/09-短线知识/群聊情绪"
OUT_ROOT = ROOT / "raw/11-Codex分析产物/短线知识提炼"
QUEUE = ROOT / "wiki/09-统计与进化/私域聊天情绪验证队列.md"

WORDS = {
    "追涨踏空": ["踏空", "抢", "上车", "买不到", "涨疯", "继续冲", "明天还能买吗"],
    "恐慌割肉": ["割肉", "核", "跌停", "大面", "完了", "崩了", "亏麻", "跑"],
    "观望防守": ["空仓", "不敢", "看戏", "休息", "管住手", "等"],
    "抄底修复": ["低吸", "反核", "修复", "抄底", "回流", "弱转强"],
}


def today() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_text(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if args.text:
        return args.text
    raise SystemExit("--text 或 --file 必须提供一个")


def extract(text: str) -> dict:
    stocks = sorted(set(re.findall(r"(?<!\d)(?:[036]\d{5}|8\d{5})(?!\d)", text)))
    names = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}", text)
    word_scores = {k: sum(text.count(w) for w in ws) for k, ws in WORDS.items()}
    topic_counter = Counter()
    for word in ["机器人", "半导体", "芯片", "CPO", "PCB", "液冷", "稀土", "有色", "锂电", "创新药", "电力", "华为", "国企改革"]:
        count = text.count(word)
        if count:
            topic_counter[word] += count
    return {
        "股票代码": stocks,
        "高频中文片段": Counter(names).most_common(50),
        "情绪词计数": word_scores,
        "题材词排行": [{"题材": k, "出现次数": v} for k, v in topic_counter.most_common(20)],
    }


def judge(scores: dict[str, int]) -> str:
    if not scores or max(scores.values() or [0]) == 0:
        return "弱信号"
    return max(scores.items(), key=lambda kv: kv[1])[0]


def write_outputs(date: str, source: str, text: str, info: dict) -> dict:
    stamp = dt.datetime.now().strftime("%H%M%S")
    raw_dir = RAW_ROOT / date
    out_dir = OUT_ROOT / date
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{stamp}-{source}.md"
    json_path = out_dir / f"私域聊天情绪-{stamp}.json"
    md_path = out_dir / f"私域聊天情绪-{stamp}.md"
    stage = judge(info["情绪词计数"])
    raw_path.write_text(
        "\n".join(
            [
                f"# {date} 私域聊天情绪RAW",
                "",
                "```yaml",
                f"source: {source}",
                f"created: {dt.datetime.now().isoformat()}",
                f"content_sha256: {sha(text)}",
                "truth_grade: S4",
                "use_grade: C",
                "rule: 只作群体预期和反指辅助，不作事实依据",
                "```",
                "",
                "## 原文",
                "",
                "```text",
                text.rstrip(),
                "```",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    payload = {
        "元数据": {
            "日期": date,
            "来源": source,
            "RAW": str(raw_path.relative_to(ROOT)),
            "证据等级": "S4，私域情绪辅助层",
        },
        "情绪阶段初判": stage,
        **info,
        "使用边界": [
            "只能判断群体温度、踏空/恐慌/一致性，不可当事实。",
            "必须与淘股吧热榜、盘面数据、高手行为层交叉验证。",
            "出现全群一致高潮或一致恐慌时，可作为反指候选，但仍需D+验证。"
        ],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                f"# {date} 私域聊天情绪分析",
                "",
                f"- 阶段初判：{stage}",
                f"- RAW：`{raw_path.relative_to(ROOT)}`",
                "- 证据等级：S4，只作辅助。",
                "",
                "## 情绪词计数",
                "",
                "| 类别 | 出现次数 |",
                "|---|---:|",
                *[f"| {k} | {v} |" for k, v in info["情绪词计数"].items()],
                "",
                "## 题材词排行",
                "",
                "| 题材 | 出现次数 |",
                "|---|---:|",
                *[f"| {x['题材']} | {x['出现次数']} |" for x in info["题材词排行"]],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    append_queue(date, stage, md_path)
    return {"raw": str(raw_path), "json": str(json_path), "md": str(md_path), "stage": stage}


def append_queue(date: str, stage: str, md_path: Path) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    if not QUEUE.exists():
        QUEUE.write_text(
            "\n".join(
                [
                    "# 私域聊天情绪验证队列",
                    "",
                    "微信群/QQ群/飞书聊天只作为 S4 群体温度和反指辅助。",
                    "",
                    "| 入队日期 | 情绪阶段 | 证据 | D+1 | D+3 | D+5 | 结论 |",
                    "|---|---|---|---|---|---|---|",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    line = f"| {date} | {stage} | `{md_path.relative_to(ROOT)}` | 待验证 | 待验证 | 待验证 | 待回填 |\n"
    existing = QUEUE.read_text(encoding="utf-8")
    if line not in existing:
        with QUEUE.open("a", encoding="utf-8") as f:
            f.write(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="写入微信群/QQ群/飞书私域聊天情绪RAW并生成低权重情绪分析。")
    parser.add_argument("--date", default=today())
    parser.add_argument("--source", default="private_chat")
    parser.add_argument("--text")
    parser.add_argument("--file")
    args = parser.parse_args()
    text = load_text(args)
    print(json.dumps(write_outputs(args.date, args.source, text, extract(text)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
