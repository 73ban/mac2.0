#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a daily self-evolution report from short-term trading knowledge sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
SYSTEM = ROOT / ".system"
YOUZI_STATE = SYSTEM / "youzi-learning-state.json"
OUT_DIR = RAW / "11-Codex分析产物" / "超短自进化学习"
WIKI_YOUZI = ROOT / "wiki" / "04-L4交易模式与执行" / "游资认知体系"
WIKI_MODE = ROOT / "wiki" / "04-L4交易模式与执行"
WIKI_STATS = ROOT / "wiki" / "09-统计与进化"
PENDING = SYSTEM / "feishu-notify-pending"
NOTIFY_STATE = SYSTEM / "shortline-learning-progress-state.json"


GOOD_RULE_HINTS = ("必须", "只做", "不做", "不能", "等待", "确认", "低吸", "半路", "打板", "接力", "卖出", "空仓", "仓位", "失效")
BAD_RULE_HINTS = ("感觉", "可能", "应该", "大概", "看好", "关注", "有机会", "或许", "随便", "感觉还行")
ENV_KEYS = ("冰点", "分歧", "修复", "高潮", "退潮", "主升", "轮动", "缩量", "放量", "亏钱效应", "赚钱效应")
TRIGGER_KEYS = ("竞价", "高开", "低开", "承接", "封单", "回封", "炸板", "涨停", "热榜", "一字", "连板", "放量", "缩量")
ACTION_KEYS = ("买入", "卖出", "低吸", "半路", "打板", "接力", "减仓", "清仓", "空仓", "切换", "回避")
FAIL_KEYS = ("失效", "不及预期", "该强不强", "跌破", "补跌", "退潮", "澄清", "监管", "炸板")
THEME_KEYS = ("AI", "算力", "CPO", "光模块", "PCB", "HBM", "存储", "半导体", "机器人", "韬定律", "并购重组", "华为")
TRADE_RECORD_KEYS = ("持有：", "买入：", "卖出：", "今日盈亏", "总收益", "全组第")
EXPLANATION_KEYS = ("因为", "逻辑", "模式", "环境", "情绪", "主线", "分歧", "修复", "退潮", "预期", "超预期", "不及预期", "验证")
LIST_NOISE_RE = re.compile(r"^\d{2}-\d{2}\s+\d{2}:\d{2}\s*/.*\(\d+\)\s*$")
SELF_FEEDBACK_KEYS = ("飞书校准闭环", "市场阶段大局观校准", "消息强度连板高度校准", "自动化任务Watchdog", "重大消息雷达")
NOISE_TITLE_KEYS = ("原文", "抓取任务清单", "比赛列表")


@dataclass
class LearningItem:
    fingerprint: str
    source: str
    author: str
    title: str
    date: str
    raw_path: str
    card_path: str
    kind: str
    rule: str
    themes: list[str]
    methods: list[str]
    score: int
    grade: str
    importance: str
    reason: str
    wiki_action: str
    verify: list[str]


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def clean(value: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().replace("|", "/")
    return text[:limit]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def rule_score(rule: str, themes: list[str], methods: list[str], source_score: int = 0) -> tuple[int, list[str]]:
    text = re.sub(r"\s+", "", rule)
    score = source_score
    reasons: list[str] = []
    is_trade_record = any(k.replace("：", "") in text for k in TRADE_RECORD_KEYS)
    has_explanation = any(k in text for k in EXPLANATION_KEYS)
    if is_trade_record and not has_explanation:
        return 18, ["纯买卖/持仓记录，只能做样本，不能当规则"]
    if any(k in text for k in GOOD_RULE_HINTS):
        score += 12
        reasons.append("有明确规则语气")
    if any(k in text for k in ENV_KEYS):
        score += 14
        reasons.append("包含适用环境")
    if any(k in text for k in TRIGGER_KEYS):
        score += 14
        reasons.append("包含触发信号")
    if any(k in text for k in ACTION_KEYS):
        score += 14
        reasons.append("包含动作")
    if any(k in text for k in FAIL_KEYS):
        score += 12
        reasons.append("包含失效/风险条件")
    if themes:
        score += min(10, 3 * len(themes))
        reasons.append("可落到题材")
    if methods:
        score += min(10, 4 * len(methods))
        reasons.append("可落到交易模式")
    if 16 <= len(text) <= 110:
        score += 8
        reasons.append("长度适合沉淀")
    if any(k in text for k in BAD_RULE_HINTS):
        score -= 18
        reasons.append("表达偏观点化")
    if len(text) < 12:
        score -= 15
        reasons.append("过短")
    return max(0, min(100, score)), reasons[:5]


def classify(score: int, reasons: list[str], source: str) -> tuple[str, str, str, list[str]]:
    if score >= 78 and "包含失效/风险条件" in reasons:
        return "S", "重要", "进入L4候选规则，D+验证通过后沉淀正式模式", ["D+1", "D+3", "D+5", "用户交易反馈"]
    if score >= 65:
        return "A", "重要", "进入验证队列，暂不写入正式模式", ["D+1", "D+3", "D+5"]
    if score >= 45:
        return "B", "一般", "保留在学习卡和验证看板，等待更多样本", ["D+3", "D+5"]
    return "C", "待理解", "写入RAW学习池，等待后续市场样本和用户校准，不进入正式Wiki", ["暂不验证"]


def themes_in(text: str, existing: list[str] | None = None) -> list[str]:
    out = list(existing or [])
    for key in THEME_KEYS:
        if key.lower() in text.lower() and key not in out:
            out.append(key)
    return out[:8]


def collect_youzi_items(date: str) -> list[LearningItem]:
    state = read_json(YOUZI_STATE, {})
    rows = state.get("items") if isinstance(state, dict) else []
    items: list[LearningItem] = []
    for row in rows or []:
        if row.get("date") != date:
            continue
        raw_rel = str(row.get("raw_rel") or "")
        source_name = str(row.get("source") or "")
        title = str(row.get("title") or "")
        if "raw/09-短线知识/飞书输入" in raw_rel:
            continue
        if source_name.isdigit() or any(key in title for key in SELF_FEEDBACK_KEYS):
            continue
        rules = row.get("rules") or []
        if not rules and row.get("core_points"):
            rules = row.get("core_points")[:2]
        source_score = 14 if row.get("validation", {}).get("level") == "high" else 8 if row.get("validation", {}).get("level") == "medium" else 2
        for rule in rules[:6]:
            themes = themes_in(rule, row.get("themes") or [])
            methods = list(row.get("methods") or [])[:6]
            score, reasons = rule_score(rule, themes, methods, source_score)
            grade, importance, action, verify = classify(score, reasons, "游资号")
            fp = hashlib.sha1(f"youzi|{row.get('source')}|{row.get('title')}|{rule}".encode("utf-8")).hexdigest()[:16]
            items.append(
                LearningItem(
                    fingerprint=fp,
                    source="游资号/公众号",
                    author=source_name,
                    title=title,
                    date=date,
                    raw_path=str(row.get("raw_rel") or ""),
                    card_path=str(row.get("card_rel") or ""),
                    kind="规则候选",
                    rule=clean(rule, 220),
                    themes=themes,
                    methods=methods,
                    score=score,
                    grade=grade,
                    importance=importance,
                    reason="、".join(reasons) or "低置信学习条目",
                    wiki_action=action,
                    verify=verify,
                )
            )
    return items


def collect_taoguba_items(date: str) -> list[LearningItem]:
    roots = [
        RAW / "11-Codex分析产物" / "短线知识提炼" / date,
        RAW / "09-短线知识" / "淘股吧实盘赛" / date,
        RAW / "09-短线知识" / "淘股吧" / date,
        RAW / "09-短线知识" / "淘股吧大游资名人堂" / date,
    ]
    items: list[LearningItem] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            if path.name in {"抓取记录.md"} or "source" in path.name:
                continue
            if any(noise in path.stem for noise in ("抓取任务清单", "比赛列表")):
                continue
            text = read_text(path)
            title = path.stem
            for line in text.splitlines()[:80]:
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            if title in NOISE_TITLE_KEYS or any(key in title for key in SELF_FEEDBACK_KEYS):
                continue
            candidates = []
            for line in text.splitlines():
                line = line.strip().lstrip("-").strip()
                compact = re.sub(r"\s+", "", line)
                if LIST_NOISE_RE.match(line):
                    continue
                if any(k.replace("：", "") in compact for k in TRADE_RECORD_KEYS) and not any(k in compact for k in EXPLANATION_KEYS):
                    continue
                if 12 <= len(line) <= 140 and any(k in line for k in GOOD_RULE_HINTS + TRIGGER_KEYS + ENV_KEYS + ACTION_KEYS):
                    candidates.append(line)
                if len(candidates) >= 5:
                    break
            if not candidates and any(k in title for k in ("情绪周期", "高手样本", "提炼")):
                candidates = [title]
            for rule in candidates[:5]:
                themes = themes_in(f"{title} {rule}")
                methods = [m for m in ("低吸", "半路", "打板", "接力", "弱转强", "反包", "二波", "趋势抱团", "轮动切换") if m in f"{title}{rule}"]
                source_score = 12 if "实盘赛" in str(path) or "高手" in title else 8
                score, reasons = rule_score(rule, themes, methods, source_score)
                grade, importance, action, verify = classify(score, reasons, "淘股吧")
                fp = hashlib.sha1(f"tgb|{rel(path)}|{rule}".encode("utf-8")).hexdigest()[:16]
                items.append(
                    LearningItem(
                        fingerprint=fp,
                        source="淘股吧高手/情绪",
                        author="淘股吧",
                        title=title,
                        date=date,
                        raw_path=rel(path),
                        card_path="",
                        kind="情绪/模式候选",
                        rule=clean(rule, 220),
                        themes=themes,
                        methods=methods,
                        score=score,
                        grade=grade,
                        importance=importance,
                        reason="、".join(reasons) or "淘股吧情绪样本",
                        wiki_action=action,
                        verify=verify,
                    )
                )
    return items


def diversify(items: list[LearningItem], limit: int = 10) -> list[LearningItem]:
    sorted_items = sorted(items, key=lambda x: (x.score, x.grade == "S"), reverse=True)
    selected: list[LearningItem] = []
    by_source: Counter[str] = Counter()
    by_title: Counter[str] = Counter()
    for item in sorted_items:
        if by_source[item.source] >= 5:
            continue
        if by_title[item.title] >= 2:
            continue
        selected.append(item)
        by_source[item.source] += 1
        by_title[item.title] += 1
        if len(selected) >= limit:
            break
    selected_ids = {item.fingerprint for item in selected}
    for item in sorted_items:
        if item.fingerprint in selected_ids:
            continue
        selected.append(item)
        selected_ids.add(item.fingerprint)
        if len(selected) >= limit:
            break
    return selected


def build(date: str) -> dict[str, Any]:
    items = collect_youzi_items(date) + collect_taoguba_items(date)
    dedup: dict[str, LearningItem] = {}
    for item in items:
        key = re.sub(r"\s+", "", item.rule).lower()
        if key not in dedup or item.score > dedup[key].score:
            dedup[key] = item
    rows = sorted(dedup.values(), key=lambda x: (x.score, x.grade == "S"), reverse=True)
    top = diversify(rows, 10)
    important = [x for x in rows if x.importance == "重要"]
    uncertain = [x for x in rows if x.importance == "一般"][:10]
    rejected = [x for x in rows if x.importance == "待理解"]
    return {
        "schema": "73wiki-shortline-self-evolution-v1",
        "date": date,
        "generatedAt": now_text(),
        "summary": {
            "candidates": len(rows),
            "important": len(important),
            "uncertain": len(uncertain),
            "rejected": len(rejected),
        },
        "logic": [
            "重要：必须能说清环境、触发、动作、失效条件中的至少两项，并能落到题材/模式/D+验证。",
            "一般：观点有参考，但缺少触发或失效条件，先留在验证队列。",
            "待理解：口号、观点、经验、无验证对象，先写入 RAW 学习池，不进入正式 Wiki。",
            "飞书每天固定发 10 条学习样本给用户校准；用户纠偏会回写权重。",
        ],
        "top10": [x.__dict__ for x in top],
        "all_candidates": [x.__dict__ for x in rows],
        "important": [x.__dict__ for x in important[:30]],
        "uncertain": [x.__dict__ for x in uncertain],
        "rejected": [x.__dict__ for x in rejected],
    }


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 超短知识自进化学习日报",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 候选规则：{payload['summary']['candidates']}",
        f"- 重要：{payload['summary']['important']}；一般：{payload['summary']['uncertain']}；待理解：{payload['summary']['rejected']}",
        "",
        "## 判断逻辑",
        "",
    ]
    for rule in payload["logic"]:
        lines.append(f"- {rule}")
    lines += [
        "",
        "## 今日Top10学习",
        "",
        "| 排名 | 分数 | 等级 | 重要性 | 来源 | 标题 | 学到的规则 | 为什么 | Wiki动作 | 验证 |",
        "|---:|---:|---|---|---|---|---|---|---|---|",
    ]
    for idx, row in enumerate(payload["top10"], start=1):
        lines.append(
            f"| {idx} | {row['score']} | {row['grade']} | {row['importance']} | {row['source']}:{row['author']} | {clean(row['title'], 48)} | {clean(row['rule'], 80)} | {clean(row['reason'], 80)} | {clean(row['wiki_action'], 70)} | {'、'.join(row['verify'])} |"
        )
    if not payload["top10"]:
        lines.append("| - | - | - | - | 今日没有新增高价值学习项 | - | - | - | - | - |")
    lines += [
        "",
        "## 需要用户校准",
        "",
        "请只校准我可能学错的地方：有效 / 一般 / 无效 / 反向。",
        "",
        "| 编号 | 规则 | 我当前判断 | 需要你看什么 |",
        "|---:|---|---|---|",
    ]
    review_rows = review_rows_for_notify(payload)
    for idx, row in enumerate(review_rows, start=1):
        lines.append(f"| {idx} | {clean(row['rule'], 90)} | {row['importance']} / {row['grade']} | 是否真的能指导你的超短交易，还是只是写得好听 |")
    if not review_rows:
        lines.append("| - | 无 | 无 | 无 |")
    lines += [
        "",
        "## 不写入正式Wiki的原因",
        "",
        "- 只讲观点、不讲触发条件的，进入 RAW 学习池，不升正式模式。",
        "- 没有失效条件的，先等用户校准和 D+样本。",
        "- 没有 D+ 验证的，只能算学习候选，不能算正式交易知识。",
    ]
    return "\n".join(lines) + "\n"


def render_notify(payload: dict[str, Any]) -> str:
    lines = [
        "【超短知识自进化学习待校准】",
        f"时间：{payload['generatedAt']}",
        "",
        "判断对象：下面每一条是“学习样本”，不是股票买卖建议。",
        "你只需要帮我校准它属于哪一类：",
        "- 有效：可进入D+验证，未来可能沉淀为交易规则。",
        "- 一般：先保留RAW，暂不升权。",
        "- 无效：噪音/标题/废话，后续降权。",
        "- 反向：容易误导交易，要进错误样本。",
        "",
        "回复格式：第几条 + 有效/一般/无效/反向 + 一句话原因。",
        "",
    ]
    rows = review_rows_for_notify(payload)
    for idx, row in enumerate(rows, start=1):
        valid_action = "、".join(row["verify"]) if row.get("verify") and row.get("verify") != ["暂不验证"] else "改为进入D+验证队列"
        use_case = learning_use_case(row)
        uncertainty = learning_uncertainty(row)
        lines.extend(
            [
                f"{idx}. {row['rule']}",
                "   你要判断：这条样本对训练超短交易认知有没有用。",
                f"   来源：{row['source']} / {row['author']} / {row['title']}",
                f"   我当前判断：{row['importance']}，等级 {row['grade']}，分数 {row['score']}",
                f"   我把它当成：{use_case}",
                f"   我的判断逻辑：{row['reason']}",
                f"   我认为可能有用的点：{possible_value(row)}",
                f"   我不确定/需要你纠偏：{uncertainty}",
                f"   如果你判有效：{valid_action}；如果判无效：降权不再打扰。",
                "",
            ]
        )
    if not rows:
        lines.append("今天没有需要你校准的高价值规则候选。")
    return "\n".join(lines)


def learning_use_case(row: dict[str, Any]) -> str:
    text = f"{row.get('rule','')} {row.get('title','')}"
    if any(key in text for key in ("退潮", "亏钱效应", "补跌", "核按钮", "天地板")):
        return "情绪周期/防守信号样本"
    if any(key in text for key in ("弱转强", "低开转强", "回封", "一进二", "分歧转一致")):
        return "买点/确认信号样本"
    if any(key in text for key in ("趋势", "主升", "中军", "放量")):
        return "题材主升/中军趋势样本"
    if any(key in text for key in ("环境", "主线", "连板天梯", "热榜", "D+验证")):
        return "交易复盘框架样本"
    if row.get("source") == "游资号/公众号":
        return "产业认知/题材背景样本"
    return "短线知识待分类样本"


def possible_value(row: dict[str, Any]) -> str:
    text = f"{row.get('rule','')} {row.get('reason','')}"
    parts = []
    if "包含适用环境" in text or any(key in text for key in ("分歧", "退潮", "主升")):
        parts.append("能帮助判断适用市场阶段")
    if "包含触发信号" in text or any(key in text for key in ("竞价", "回封", "弱转强", "承接")):
        parts.append("能转成盘中观察条件")
    if "包含失效" in text or any(key in text for key in ("退潮", "补跌", "核按钮")):
        parts.append("能形成防守/失效条件")
    if row.get("source") == "游资号/公众号":
        parts.append("可能补充题材背景，但未必能直接指导买卖")
    return "；".join(parts) if parts else "暂时只值得保留为RAW样本"


def learning_uncertainty(row: dict[str, Any]) -> str:
    text = f"{row.get('rule','')} {row.get('title','')}"
    if row.get("source") == "游资号/公众号" and not any(key in text for key in ("买入", "卖出", "低吸", "打板", "接力", "竞价")):
        return "它可能只是产业观点，不一定是超短交易规则；请判断应保留还是降权。"
    if row.get("importance") == "待理解":
        return "我还不能确认它是真规则还是术语/口号；请判断是否值得后续验证。"
    if "D+验证" in text:
        return "这是流程规则，不是具体买点；请判断是否值得作为系统纪律保留。"
    return "请判断我的等级是否高估或低估。"


def write_pending_once(payload: dict[str, Any]) -> dict[str, Any]:
    state = read_json(NOTIFY_STATE, {"notified_dates": []})
    notified = set(state.get("notified_dates") or [])
    date = payload["date"]
    if date in notified:
        return {"created": False, "reason": "already_notified"}
    rows = review_rows_for_notify(payload)
    if not rows:
        return {"created": False, "reason": "no_candidates"}
    PENDING.mkdir(parents=True, exist_ok=True)
    name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-超短知识自进化学习待校准.md"
    (PENDING / name).write_text(render_notify(payload), encoding="utf-8")
    state["notified_dates"] = sorted([*notified, date])[-60:]
    write_json(NOTIFY_STATE, state)
    return {"created": True, "file": rel(PENDING / name)}


def review_rows_for_notify(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list(payload.get("top10") or [])
    if len(rows) >= 10:
        return rows[:10]
    seen = {row.get("fingerprint") for row in rows}
    for row in payload.get("all_candidates") or []:
        if row.get("fingerprint") in seen:
            continue
        rows.append(row)
        seen.add(row.get("fingerprint"))
        if len(rows) >= 10:
            break
    return rows[:10]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate shortline self-evolution learning progress.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    notify = {"created": False, "reason": "not_requested"}
    if args.write:
        out = OUT_DIR / args.date
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / "shortline-learning-progress.json", payload)
        (out / "shortline-learning-progress.md").write_text(render(payload), encoding="utf-8")
        WIKI_YOUZI.mkdir(parents=True, exist_ok=True)
        (WIKI_YOUZI / f"超短自进化学习日报-{args.date}.md").write_text(render(payload), encoding="utf-8")
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / f"{args.date}-超短知识自进化验证队列.md").write_text(render(payload), encoding="utf-8")
        if args.notify:
            notify = write_pending_once(payload)
    print(json.dumps({"ok": True, "date": args.date, "summary": payload["summary"], "notify": notify}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
