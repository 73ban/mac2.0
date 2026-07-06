#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rank the day's most important RAW information for trading review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
SYSTEM = ROOT / ".system"
OUT_DIR = RAW / "11-Codex分析产物" / "每日重要信息Top10"
WIKI_ROOM = ROOT / "wiki" / "07-作战室"
WIKI_STATS = ROOT / "wiki" / "09-统计与进化"
PENDING = SYSTEM / "feishu-notify-pending"
NOTIFY_STATE = SYSTEM / "daily-important-info-top10-notify-state.json"

CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|8\d{5})(?!\d)")
CN_NAME_RE = re.compile(r"[\u4e00-\u9fff]{2,12}")

POSITIVE_KEYS = {
    "国务院": 10,
    "发改委": 8,
    "工信部": 8,
    "政策": 6,
    "并购": 10,
    "重组": 10,
    "收购": 8,
    "资产注入": 10,
    "涨价": 9,
    "缺货": 8,
    "供给收缩": 8,
    "订单": 8,
    "中标": 8,
    "量产": 8,
    "客户": 6,
    "认证": 6,
    "英伟达": 7,
    "AI": 4,
    "算力": 5,
    "CPO": 7,
    "光模块": 7,
    "PCB": 6,
    "HBM": 7,
    "存储": 7,
    "半导体": 6,
    "机器人": 6,
    "固态电池": 6,
    "韬定律": 8,
}

RISK_KEYS = {
    "澄清": 9,
    "不属实": 10,
    "尚未": 6,
    "未合作": 9,
    "问询": 8,
    "监管": 8,
    "减持": 8,
    "立案": 12,
    "亏损": 7,
    "退潮": 8,
    "补跌": 8,
    "跌停": 8,
    "负反馈": 8,
    "异动": 5,
    "停牌": 6,
}

ROUTINE_NOISE = (
    "股东人数",
    "股东户数",
    "分红",
    "什么时候分红",
    "股价",
    "市值管理",
    "转融通",
    "请问董秘",
    "谢谢关注",
)

THEME_KEYS = (
    "AI",
    "算力",
    "CPO",
    "光模块",
    "PCB",
    "HBM",
    "存储",
    "半导体",
    "机器人",
    "固态电池",
    "并购重组",
    "韬定律",
    "华为",
    "低空经济",
    "创新药",
    "稀土",
)


@dataclass
class InfoItem:
    fingerprint: str
    title: str
    source: str
    category: str
    path: str
    stock_codes: list[str]
    stock_names: list[str]
    themes: list[str]
    summary: str
    score: int
    signal_score: int
    evidence_score: int
    market_score: int
    action_score: int
    risk_score: int
    direction: str
    reason: str
    suggested_action: str
    verify: list[str]


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


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def title_from_text(path: Path, text: str) -> str:
    for line in text.splitlines()[:80]:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return path.stem


def clean(value: str, limit: int = 160) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    value = value.replace("|", "/")
    return value[:limit]


def source_type(path: Path) -> str:
    text = rel(path)
    if "互动问答" in text:
        return "互动易"
    if "/公告/" in text or "公告" in text:
        return "公告"
    if "财联社" in text:
        return "财联社"
    if "三榜热度合并" in text:
        return "三榜合并"
    if "同花顺热榜" in text:
        return "同花顺热榜"
    if "淘股吧热榜" in text or "raw/04-市场数据/热榜" in text:
        return "淘股吧热榜"
    if "每日涨停全景" in text or "通达信涨停原因" in text:
        return "涨停原因"
    if "龙虎榜" in text:
        return "龙虎榜"
    if "淘股吧实盘赛" in text:
        return "淘股吧实盘赛"
    if "淘股吧大游资名人堂" in text:
        return "大游资名人堂"
    if "淘股吧" in text:
        return "淘股吧"
    if "韭研公社网页" in text:
        return "韭研公社网页"
    if "韭研公社" in text:
        return "韭研公社"
    if "公众号" in text:
        return "公众号"
    if "11-Codex分析产物" in text:
        return "Codex分析"
    return "RAW"


def evidence_score(source: str, text: str) -> int:
    base = {
        "公告": 24,
        "互动易": 22 if any(k in text for k in ("回复", "答复", "表示", "公司")) else 12,
        "财联社": 20,
        "三榜合并": 16,
        "同花顺热榜": 14,
        "淘股吧热榜": 14,
        "涨停原因": 16,
        "龙虎榜": 18,
        "淘股吧实盘赛": 15,
        "大游资名人堂": 15,
        "淘股吧": 11,
        "韭研公社网页": 16,
        "韭研公社": 14,
        "公众号": 10,
        "Codex分析": 8,
    }.get(source, 6)
    if any(k in text for k in ("确认", "属实", "已合作", "已供货", "已量产", "中标", "签订")):
        base += 5
    if any(k in text for k in ("不属实", "未合作", "尚未", "澄清")):
        base += 4
    return min(base, 28)


def keyword_hits(text: str, weights: dict[str, int]) -> tuple[int, list[str]]:
    hits: list[str] = []
    score = 0
    lower = text.lower()
    for key, value in weights.items():
        count = lower.count(key.lower())
        if count:
            hits.append(key)
            score += min(3, count) * value
    return min(score, 35), hits


def collect_market_context(date: str) -> dict[str, dict[str, Any]]:
    context: dict[str, dict[str, Any]] = {}

    def add(code: str, name: str, source: str, rank: Any = None, reason: str = "") -> None:
        key = code or name
        if not key:
            return
        row = context.setdefault(key, {"code": code, "name": name, "sources": set(), "best_rank": 999, "reasons": []})
        if code:
            context.setdefault(code, row)
        if name:
            context.setdefault(name, row)
        row["sources"].add(source)
        try:
            row["best_rank"] = min(int(row.get("best_rank") or 999), int(rank))
        except Exception:
            pass
        if reason:
            row["reasons"].append(clean(reason, 80))

    candidates = [
        RAW / "04-市场数据" / "三榜热度合并" / date / "三榜热度合并.json",
        RAW / "04-市场数据" / "热榜" / date / "同花顺热榜Top100.json",
        RAW / "04-市场数据" / "热榜" / date / "淘股吧热榜100-latest.json",
        RAW / "04-市场数据" / "同花顺热榜" / date / "ths-hot-top100.json",
    ]
    for path in candidates:
        payload = read_json(path, None)
        if payload is None:
            continue
        for row in iter_dicts(payload):
            code = str(first(row, "代码", "code", "stockCode", "symbol") or "").strip()
            name = str(first(row, "名称", "name", "stockName", "股票名称") or "").strip()
            if not code and not name:
                continue
            rank = first(row, "排名", "rank", "hotRank", "热度排名")
            reason = str(first(row, "上榜理由", "reason", "涨停原因", "概念", "题材", "remark") or "")
            add(code, name, source_type(path), rank, reason)
    for row in context.values():
        if isinstance(row.get("sources"), set):
            row["sources"] = sorted(row["sources"])
    return context


def first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def files_for_date(date: str) -> list[Path]:
    roots = [
        RAW / "05-研报新闻",
        RAW / "04-市场数据",
        RAW / "09-短线知识",
        RAW / "11-Codex分析产物" / "短线知识提炼",
        RAW / "11-Codex分析产物" / "消息催化评分",
        RAW / "11-Codex分析产物" / "晚间个股线索",
    ]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".json"}:
                continue
            text_path = str(path)
            if date not in text_path or ".stversions" in path.parts or "Firecrawl评估" in path.parts:
                continue
            if "每日重要信息Top10" in text_path:
                continue
            if path.name in {"source.txt", "source.html", "firecrawl_raw.json"}:
                continue
            files.append(path)
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:2000]


def row_items_from_json(path: Path, source: str, date: str) -> list[dict[str, str]]:
    payload = read_json(path, None)
    if payload is None:
        return []
    rows = []
    for row in iter_dicts(payload):
        if not isinstance(row, dict):
            continue
        title = first(row, "标题", "title", "消息", "name", "名称", "stockName", "股票名称", "question")
        reason = first(row, "上榜理由", "reason", "涨停原因", "summary", "answer", "reply", "回复", "content", "概念")
        code = str(first(row, "代码", "code", "stockCode", "symbol", "股票代码") or "")
        rank = first(row, "排名", "rank", "hotRank", "热度排名")
        if not title and not reason:
            continue
        text = clean(f"{title} {reason}", 360)
        if len(text) < 8:
            continue
        if source.endswith("热榜") and rank not in (None, ""):
            title = f"{source} Rank{rank} {clean(str(title), 40)}"
        rows.append({"title": clean(str(title or path.stem), 120), "text": text, "code": code, "rank": str(rank or "")})
        if len(rows) >= 120:
            break
    return rows


def markdown_item(path: Path) -> dict[str, str]:
    text = read_text(path)
    title = title_from_text(path, text)
    summary = ""
    for line in text.splitlines()[:120]:
        line = line.strip()
        if not line or line.startswith(("#", "|", "-", "---")):
            continue
        summary = line
        break
    return {"title": clean(title, 120), "text": clean(f"{title} {summary} {text[:1800]}", 2200), "code": "", "rank": ""}


def extract_names(text: str, market: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    codes = sorted(set(CODE_RE.findall(text)))[:10]
    names: list[str] = []
    for key, row in market.items():
        name = str(row.get("name") or "")
        code = str(row.get("code") or "")
        if name and name in text and name not in names:
            names.append(name)
        if code and code in text and name and name not in names:
            names.append(name)
    return codes, names[:10]


def themes_in(text: str) -> list[str]:
    return [key for key in THEME_KEYS if key.lower() in text.lower()][:8]


def market_validation_score(codes: list[str], names: list[str], text: str, market: dict[str, dict[str, Any]]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    seen = set(codes + names)
    for key in seen:
        row = market.get(key)
        if not row:
            continue
        sources = row.get("sources") or []
        best_rank = int(row.get("best_rank") or 999)
        if sources:
            score += min(12, 4 * len(sources))
            reasons.append("热榜共振：" + "、".join(sources[:3]))
        if best_rank <= 10:
            score += 10
            reasons.append(f"热榜Top{best_rank}")
        elif best_rank <= 30:
            score += 6
            reasons.append(f"热榜Top{best_rank}")
    if "涨停" in text:
        score += 8
        reasons.append("涨停验证")
    if "一字" in text:
        score += 6
        reasons.append("一字/强一致")
    if "连板" in text:
        score += 6
        reasons.append("连板验证")
    return min(score, 30), list(dict.fromkeys(reasons))[:4]


def is_noise(text: str, source: str) -> bool:
    if source == "互动易" and any(key in text for key in ROUTINE_NOISE) and not any(key in text for key in POSITIVE_KEYS | RISK_KEYS):
        return True
    if any(key in text for key in ("山火", "地铁列车脱轨", "击退武装分子", "高温影响")) and not any(key in text for key in THEME_KEYS):
        return True
    if len(text.strip()) < 12:
        return True
    return False


def classify(source: str, text: str, pos_hits: list[str], risk_hits: list[str]) -> tuple[str, str, str, list[str]]:
    if source == "互动易" and risk_hits:
        return "官方确认/辟谣", "反向/风险", "更新个股卡风险事实，进入作战室排雷", ["竞价", "热榜退潮", "板块负反馈"]
    if source == "互动易":
        return "官方确认/辟谣", "正向/待验证", "若命中当日热点，更新个股卡和题材卡", ["热榜跃迁", "竞价", "板块扩散"]
    if source in {"公告", "财联社"} and risk_hits and not pos_hits:
        return "风险信号", "负向", "进入风险池，复核是否打断题材", ["竞价", "跌停", "板块负反馈"]
    if source in {"三榜合并", "同花顺热榜", "淘股吧热榜", "涨停原因"}:
        return "市场验证", "背景/验证", "进入情绪周期和题材扩散跟踪，不单独给买入权限", ["热榜跃迁", "涨停", "板块扩散"]
    if source in {"淘股吧实盘赛", "大游资名人堂", "淘股吧"}:
        return "高手/情绪样本", "方法/情绪", "进入短线知识提炼，D+验证后再沉淀L4", ["D+1", "D+3", "D+5"]
    return "单条催化", "正向/待验证" if pos_hits else "观察", "进入作战室候选复核", ["竞价", "涨停", "热榜跃迁", "板块扩散"]


def build(date: str, limit: int) -> dict[str, Any]:
    market = collect_market_context(date)
    items: list[InfoItem] = []
    for path in files_for_date(date):
        source = source_type(path)
        raw_rows = row_items_from_json(path, source, date) if path.suffix.lower() == ".json" else []
        if not raw_rows:
            raw_rows = [markdown_item(path)]
        for raw in raw_rows:
            text = raw["text"]
            if is_noise(text, source):
                continue
            codes, names = extract_names(text, market)
            if raw.get("code") and raw["code"] not in codes:
                codes.insert(0, raw["code"])
            themes = themes_in(text)
            pos_score, pos_hits = keyword_hits(text, POSITIVE_KEYS)
            risk_score, risk_hits = keyword_hits(text, RISK_KEYS)
            ev_score = evidence_score(source, text)
            mkt_score, mkt_reasons = market_validation_score(codes, names, text, market)
            action_score = 0
            if codes or names:
                action_score += 8
            if themes:
                action_score += 5
            if any(key in text for key in ("确认", "澄清", "不属实", "订单", "涨价", "重组", "收购", "中标")):
                action_score += 6
            action_score = min(action_score, 16)
            signal_score = max(pos_score, min(28, risk_score + 4))
            score = min(100, signal_score + ev_score + mkt_score + action_score)
            if score < 35:
                continue
            category, direction, action, verify = classify(source, text, pos_hits, risk_hits)
            reason_bits = []
            if pos_hits:
                reason_bits.append("催化词：" + "、".join(pos_hits[:5]))
            if risk_hits:
                reason_bits.append("风险词：" + "、".join(risk_hits[:4]))
            if mkt_reasons:
                reason_bits.append("市场验证：" + "、".join(mkt_reasons[:3]))
            if not reason_bits:
                reason_bits.append("资料源权重较高，进入当日重要信息池。")
            fp_raw = f"{source}|{raw['title']}|{rel(path)}|{','.join(codes)}"
            items.append(
                InfoItem(
                    fingerprint=hashlib.sha1(fp_raw.encode("utf-8")).hexdigest()[:16],
                    title=raw["title"],
                    source=source,
                    category=category,
                    path=rel(path),
                    stock_codes=codes[:8],
                    stock_names=names[:8],
                    themes=themes,
                    summary=clean(text, 180),
                    score=score,
                    signal_score=signal_score,
                    evidence_score=ev_score,
                    market_score=mkt_score,
                    action_score=action_score,
                    risk_score=risk_score,
                    direction=direction,
                    reason="；".join(reason_bits),
                    suggested_action=action,
                    verify=verify,
                )
            )
    dedup: dict[str, InfoItem] = {}
    for item in items:
        key = re.sub(r"\s+", "", f"{item.category}|{item.title}|{','.join(item.stock_codes or item.stock_names)}").lower()
        if key not in dedup or item.score > dedup[key].score:
            dedup[key] = item
    rows = sorted(dedup.values(), key=lambda item: (item.score, item.market_score, item.evidence_score), reverse=True)
    top10 = diversified_top10(rows)
    return {
        "schema": "73wiki-daily-important-info-top10-v1",
        "date": date,
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "logic": {
            "score": "总分=信号强度+证据强度+市场验证+可行动性；风险信息也按重要性入榜，但方向标为负向/反向。",
            "signal": "政策/并购重组/涨价/订单/AI算力/半导体/机器人/韬定律等催化词，或澄清/问询/减持/退潮/跌停等风险词。",
            "evidence": "公告/互动易/财联社最高，热榜/涨停/龙虎榜次之，淘股吧高手和公众号作为情绪与模式样本。",
            "market": "三榜共振、热榜Top、涨停/一字/连板提高权重。",
            "action": "能落到个股卡、题材卡、作战室或D+验证的条目加权。",
        },
        "rows": [item.__dict__ for item in rows[:limit]],
        "top10": [item.__dict__ for item in top10],
    }


def diversified_top10(rows: list[InfoItem]) -> list[InfoItem]:
    """Keep the daily view useful: no single information type can occupy the whole list."""
    category_caps = {
        "单条催化": 5,
        "官方确认/辟谣": 3,
        "风险信号": 3,
        "市场验证": 2,
        "高手/情绪样本": 2,
    }
    source_caps = {
        "淘股吧实盘赛": 2,
        "淘股吧": 2,
        "韭研公社网页": 2,
        "韭研公社": 2,
        "Codex分析": 2,
        "公众号": 2,
    }
    selected: list[InfoItem] = []
    by_category: dict[str, int] = {}
    by_source: dict[str, int] = {}
    seen_stocks: dict[str, int] = {}
    for item in rows:
        if by_category.get(item.category, 0) >= category_caps.get(item.category, 4):
            continue
        if by_source.get(item.source, 0) >= source_caps.get(item.source, 4):
            continue
        key_stocks = [x for x in [*item.stock_codes, *item.stock_names] if x]
        if key_stocks and all(seen_stocks.get(x, 0) >= 2 for x in key_stocks):
            continue
        selected.append(item)
        by_category[item.category] = by_category.get(item.category, 0) + 1
        by_source[item.source] = by_source.get(item.source, 0) + 1
        for stock in key_stocks:
            seen_stocks[stock] = seen_stocks.get(stock, 0) + 1
        if len(selected) >= 10:
            return selected
    for item in rows:
        if item not in selected:
            selected.append(item)
        if len(selected) >= 10:
            break
    return selected


def render(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 每日重要信息Top10",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        "- 用途：从当天 RAW 中挑出最值得进入作战室、个股卡、题材卡、D+验证的 10 条信息。",
        "",
        "## 评分逻辑",
        "",
        "- 总分 = 信号强度 + 证据强度 + 市场验证 + 可行动性。",
        "- 热榜/三榜/涨停原因是市场背景和验证，不等于单条催化。",
        "- 互动易只有在确认或否认当下炒作逻辑时才进入个股卡；普通股东人数、分红、股价问答不入榜。",
        "",
        "## Top10",
        "",
        "| 排名 | 分数 | 类型 | 方向 | 信息 | 关联标的/题材 | 为什么重要 | 动作 | 验证 | 来源 |",
        "|---:|---:|---|---|---|---|---|---|---|---|",
    ]
    for idx, row in enumerate(payload["top10"], start=1):
        stocks = "、".join([*(row.get("stock_names") or []), *(row.get("stock_codes") or []), *(row.get("themes") or [])]) or "-"
        lines.append(
            f"| {idx} | {row['score']} | {row['category']} | {row['direction']} | {clean(row['title'], 70)} | {clean(stocks, 90)} | {clean(row['reason'], 120)} | {clean(row['suggested_action'], 80)} | {'、'.join(row.get('verify') or [])} | `{row['path']}` |"
        )
    if not payload["top10"]:
        lines.append("| - | - | - | - | 今日无达到阈值的重要信息 | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## 使用边界",
            "",
            "- 这个 Top10 是信息优先级，不是买入清单。",
            "- 入榜后仍要看竞价、涨停、一字、热榜跃迁、板块扩散和 D+验证。",
            "- 只有通过验证的内容才沉淀到正式 Wiki 个股卡、题材卡、模式库或错误库。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_notify(payload: dict[str, Any]) -> str:
    lines = [
        "【每日消息判断Top10待校准】",
        f"时间：{payload['generatedAt']}",
        "",
        "判断对象：下面每一条是“消息/题材/个股信息的短线价值判断”，不是股票买卖建议。",
        "你只需要校准我对消息价值的判断：有效 / 一般 / 无效 / 反向；也可以说高估/低估。",
        "",
        "回复格式：第几条 + 有效/一般/无效/反向/高估/低估 + 一句话原因。",
        "",
    ]
    for idx, row in enumerate(payload.get("top10") or [], start=1):
        stocks = "、".join([*(row.get("stock_names") or []), *(row.get("stock_codes") or []), *(row.get("themes") or [])]) or "-"
        conclusion = "有效" if row.get("score", 0) >= 75 else "一般" if row.get("score", 0) >= 55 else "待理解"
        logic_parts = [
            f"信号强度{row.get('signal_score', 0)}",
            f"证据强度{row.get('evidence_score', 0)}",
            f"市场验证{row.get('market_score', 0)}",
            f"可行动性{row.get('action_score', 0)}",
        ]
        uncertainty = "如果只是热榜/整包材料而不是单条催化，请判一般或无效；如果是澄清/退潮风险，请重点看是否反向。"
        if row.get("direction") == "负向/风险":
            uncertainty = "这可能是风险信号，不是利好；请判断应当降权、回避，还是作为反向样本。"
        lines.extend(
            [
                f"{idx}. {clean(row.get('title'), 120)}",
                "   你要判断：这条消息本身对明日短线有没有价值，不是判断所有关联票能不能买。",
                f"   关联标的/题材：{clean(stocks, 120)}",
                f"   我当前判断：{conclusion}，分数 {row.get('score', 0)}，方向 {row.get('direction')}",
                f"   我的判断逻辑：{'; '.join(logic_parts)}；{row.get('reason')}",
                f"   我认为可能有用的点：{row.get('suggested_action')}",
                f"   我不确定/需要你纠偏：{uncertainty}",
                f"   后续验证：{'、'.join(row.get('verify') or []) or '竞价、涨停、热榜跃迁、板块扩散'}",
                "",
            ]
        )
    if not payload.get("top10"):
        lines.append("今天没有达到阈值的消息判断样本。")
    return "\n".join(lines)


def write_pending_once(payload: dict[str, Any]) -> dict[str, Any]:
    state = read_json(NOTIFY_STATE, {"notified_dates": []})
    notified = set(state.get("notified_dates") or [])
    date = payload["date"]
    if date in notified:
        return {"created": False, "reason": "already_notified"}
    if not payload.get("top10"):
        return {"created": False, "reason": "no_candidates"}
    PENDING.mkdir(parents=True, exist_ok=True)
    name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-每日消息判断Top10待校准.md"
    path = PENDING / name
    path.write_text(render_notify(payload), encoding="utf-8")
    state["notified_dates"] = sorted([*notified, date])[-60:]
    write_json(NOTIFY_STATE, state)
    return {"created": True, "file": rel(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate daily important RAW information Top10.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()
    payload = build(args.date, args.limit)
    notify = {"created": False, "reason": "not_requested"}
    if args.write:
        out = OUT_DIR / args.date
        out.mkdir(parents=True, exist_ok=True)
        write_json(out / "daily-important-info-top10.json", payload)
        (out / "daily-important-info-top10.md").write_text(render(payload), encoding="utf-8")
        WIKI_ROOM.mkdir(parents=True, exist_ok=True)
        (WIKI_ROOM / f"{args.date}-每日重要信息Top10.md").write_text(render(payload), encoding="utf-8")
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / f"{args.date}-每日重要信息排序逻辑.md").write_text(render(payload), encoding="utf-8")
        if args.notify:
            notify = write_pending_once(payload)
    print(json.dumps({"ok": True, "date": args.date, "topCount": len(payload["top10"]), "topScore": payload["top10"][0]["score"] if payload["top10"] else 0, "notify": notify}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
