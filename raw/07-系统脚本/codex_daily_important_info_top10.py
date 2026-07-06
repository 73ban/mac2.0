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

LONG_VALUE_KEYS = {
    "量产": 10,
    "客户": 8,
    "订单": 9,
    "中标": 8,
    "认证": 7,
    "供货": 8,
    "合作": 6,
    "签署": 6,
    "产能": 7,
    "扩产": 7,
    "国产替代": 9,
    "先进封装": 9,
    "玻璃基板": 10,
    "电子级氢氟酸": 9,
    "G5级": 8,
    "供应链": 6,
}

VALUATION_KEYS = {
    "估值": 8,
    "重估": 10,
    "价值量": 8,
    "空间": 6,
    "渗透率": 7,
    "国产替代": 8,
    "先进封装": 8,
    "AI硬件": 8,
    "产业链": 5,
    "平台型": 6,
}

SHORT_SPEC_KEYS = {
    "热榜": 6,
    "涨停": 7,
    "连板": 8,
    "一字": 7,
    "异动": 5,
    "韬定律": 6,
    "概念": 4,
    "题材": 4,
    "发酵": 5,
    "引爆": 5,
}


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
    company_impact_type: str
    company_impact_summary: str
    shortline_view: str
    institution_view: str
    value_horizon: str
    evidence_level: str
    realization_path: str
    valuation_logic: str
    impact_risks: str


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


def assess_company_impact(source: str, text: str, pos_hits: list[str], risk_hits: list[str], market_score: int) -> dict[str, str]:
    """Classify what a message means to the company, not just to tomorrow's tape."""
    long_score, long_hits = keyword_hits(text, LONG_VALUE_KEYS)
    valuation_score, valuation_hits = keyword_hits(text, VALUATION_KEYS)
    short_score, short_hits = keyword_hits(text, SHORT_SPEC_KEYS)
    has_company_evidence = source in {"公告", "互动易", "财联社"} or any(
        key in text for key in ("确认", "回复", "公告", "签订", "中标", "客户", "供货", "量产", "认证")
    )
    has_authoritative_company_evidence = source in {"公告", "互动易"} or (
        source == "财联社" and any(key in text for key in ("公司公告", "公司表示", "公司回复", "签订", "中标"))
    )

    if risk_hits:
        impact_type = "长期风险型" if has_company_evidence else "短线风险型"
    elif long_score >= 16 and valuation_score >= 8:
        impact_type = "估值重估型"
    elif long_score >= 14:
        impact_type = "长期利好/预期差型"
    elif any(key in text for key in ("涨价", "缺货", "供给收缩", "订单", "中标", "量产")):
        impact_type = "业绩弹性型"
    elif short_score >= 10 or market_score >= 14:
        impact_type = "短炒型"
    elif pos_hits:
        impact_type = "单点催化型"
    else:
        impact_type = "噪音/待观察"

    if has_authoritative_company_evidence and (long_score or risk_hits):
        evidence_level = "A-公司/权威证据"
    elif has_company_evidence and source in {"财联社", "韭研公社网页", "韭研公社", "公众号"}:
        evidence_level = "B-第三方产业资料待验证"
    elif source in {"财联社", "公告", "互动易"}:
        evidence_level = "B-高可信来源但需映射"
    elif source in {"三榜合并", "同花顺热榜", "淘股吧热榜", "涨停原因"}:
        evidence_level = "C-市场热度验证"
    else:
        evidence_level = "D-观点/传闻/情绪样本"

    if impact_type in {"估值重估型", "长期利好/预期差型"}:
        value_horizon = "中长期，需跟踪样品、客户、量产、收入确认"
    elif impact_type == "业绩弹性型":
        value_horizon = "短中期，需跟踪价格、订单、产能利用率和利润弹性"
    elif "风险" in impact_type:
        value_horizon = "立即影响风险偏好，后续看公司澄清和资金反馈"
    elif impact_type == "短炒型":
        value_horizon = "短线为主，若无公司证据容易退潮"
    else:
        value_horizon = "暂不能判断，需要更多证据"

    if impact_type == "估值重估型":
        institution_view = "机构可能关注业务边界和估值体系是否切换，但需要产业证据和财务映射。"
        valuation_logic = "旧业务估值可能被新产业链空间重估，重点看价值量、客户验证和量产路径。"
    elif impact_type == "长期利好/预期差型":
        institution_view = "机构会看预期能否变成订单、收入和利润；短期可能先按主题预期交易。"
        valuation_logic = "当前可能未贡献业绩，但若兑现会抬高远期收入空间或产业地位。"
    elif impact_type == "业绩弹性型":
        institution_view = "机构更容易用价格、销量、毛利率和订单去估算利润弹性。"
        valuation_logic = "按收入/利润弹性重估，而不是只看题材热度。"
    elif "风险" in impact_type:
        institution_view = "机构会先下修确定性或风险偏好，短线资金也可能抢跑撤退。"
        valuation_logic = "风险信息可能压低估值、打断题材，尤其是澄清、未合作、问询和需求不及预期。"
    elif impact_type == "短炒型":
        institution_view = "机构未必买账，更多是游资和散户情绪交易。"
        valuation_logic = "暂不改变公司内在价值，先按题材热度和资金博弈处理。"
    else:
        institution_view = "暂不能形成机构投资判断。"
        valuation_logic = "缺少收入、利润、客户、产能或估值映射。"

    if risk_hits:
        shortline_view = "短线先当风险处理，看竞价、跌停/补跌、热榜退潮和板块负反馈。"
    elif market_score >= 14 or short_hits:
        shortline_view = "短线有资金关注，必须用竞价、涨停质量、热榜跃迁和板块扩散确认。"
    else:
        shortline_view = "短线未充分验证，不能只因逻辑好就买。"

    path_bits = []
    if long_hits:
        path_bits.append("公司证据：" + "、".join(long_hits[:4]))
    if valuation_hits:
        path_bits.append("估值证据：" + "、".join(valuation_hits[:4]))
    if short_hits:
        path_bits.append("短线证据：" + "、".join(short_hits[:4]))
    if not path_bits:
        path_bits.append("后续补公告、互动易、研报、价格和市场反馈。")

    risks = []
    if risk_hits:
        risks.append("风险词：" + "、".join(risk_hits[:4]))
    if evidence_level.startswith("D"):
        risks.append("证据弱，可能只是观点传播。")
    if impact_type in {"估值重估型", "长期利好/预期差型"}:
        risks.append("兑现周期长，短线容易先炒预期后回落。")

    return {
        "company_impact_type": impact_type,
        "company_impact_summary": f"这条消息主要属于{impact_type}，判断重点不是热度本身，而是是否改变收入、利润、估值体系或产业地位。",
        "shortline_view": shortline_view,
        "institution_view": institution_view,
        "value_horizon": value_horizon,
        "evidence_level": evidence_level,
        "realization_path": "；".join(path_bits),
        "valuation_logic": valuation_logic,
        "impact_risks": "；".join(risks) or "主要风险是市场不认可或缺少后续验证。",
    }


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
            impact = assess_company_impact(source, text, pos_hits, risk_hits, mkt_score)
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
                    **impact,
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
            "company_impact": "所有消息都必须判断对公司意味着什么：短炒、预期差、业绩弹性、估值重估、长期风险或噪音。热榜只是市场验证，不是判断起点。",
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
        "- 所有消息都必须单独判断“对公司意味着什么”：短炒、预期差、业绩弹性、估值重估、长期风险或噪音。",
        "- 互动易只有在确认或否认当下炒作逻辑时才进入个股卡；普通股东人数、分红、股价问答不入榜。",
        "",
        "## Top10",
        "",
        "| 排名 | 分数 | 类型 | 公司影响 | 证据 | 信息 | 关联标的/题材 | 短线判断 | 机构/价值判断 | 验证 | 来源 |",
        "|---:|---:|---|---|---|---|---|---|---|---|---|",
    ]
    for idx, row in enumerate(payload["top10"], start=1):
        stocks = "、".join([*(row.get("stock_names") or []), *(row.get("stock_codes") or []), *(row.get("themes") or [])]) or "-"
        lines.append(
            f"| {idx} | {row['score']} | {row['category']} | {row.get('company_impact_type','-')} | {row.get('evidence_level','-')} | {clean(row['title'], 70)} | {clean(stocks, 90)} | {clean(row.get('shortline_view',''), 100)} | {clean(row.get('institution_view',''), 120)} | {'、'.join(row.get('verify') or [])} | `{row['path']}` |"
        )
    if not payload["top10"]:
        lines.append("| - | - | - | - | - | 今日无达到阈值的重要信息 | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## 使用边界",
            "",
            "- 这个 Top10 是信息优先级，不是买入清单。",
            "- 价值判断也不是长线买入结论；它只是判断消息是否可能改变公司收入、利润、估值或产业地位。",
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
        "判断对象：下面每一条是“消息对公司和股价的影响判断”，不是股票买卖建议。",
        "你只需要校准两件事：1）短线资金会不会认；2）这条消息是否真的改变公司长期价值/估值。",
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
                f"   公司影响分类：{row.get('company_impact_type')}；证据等级：{row.get('evidence_level')}；兑现周期：{row.get('value_horizon')}",
                f"   我的判断逻辑：{'; '.join(logic_parts)}；{row.get('reason')}",
                f"   短线资金逻辑：{row.get('shortline_view')}",
                f"   机构/价值逻辑：{row.get('institution_view')}",
                f"   估值/业绩映射：{row.get('valuation_logic')}",
                f"   兑现路径：{row.get('realization_path')}",
                f"   主要风险：{row.get('impact_risks')}",
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
    parser.add_argument("--limit", type=int, default=200)
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
