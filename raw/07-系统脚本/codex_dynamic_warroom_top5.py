#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a dynamic warroom Top5 with holding treatment and change notices."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
SYSTEM = ROOT / ".system"
OUT_ROOT = RAW / "11-Codex分析产物" / "动态作战室"
WIKI_ROOM = ROOT / "wiki" / "07-作战室"
WIKI_STOCK = ROOT / "wiki" / "03-L3个股档案"
WIKI_THEME = ROOT / "wiki" / "02-L2方向题材"
WIKI_STATS = ROOT / "wiki" / "09-统计与进化"
FACTS = ROOT / "data" / "facts" / "warroom_dynamic_versions.jsonl"
CHANGE_FACTS = ROOT / "data" / "facts" / "warroom_dynamic_change_events.jsonl"
PREDICTIONS = ROOT / "data" / "facts" / "warroom_candidate_predictions.jsonl"
QUEUE_MD = WIKI_STATS / "动态作战室Top5-D+验证队列.md"
CHANGE_MD = WIKI_STATS / "动态作战室Top5-变化流水.md"
PENDING = SYSTEM / "feishu-notify-pending"
STATE = SYSTEM / "dynamic-warroom-state.json"
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|8\d{5})(?!\d)")


RISK_WORDS = ("澄清", "问询", "监管", "减持", "亏损", "退潮", "补跌", "跌停", "异动", "不属实", "未合作", "风险")
STRONG_WORDS = ("涨停", "连板", "一字", "回封", "弱转强", "热榜", "实盘赛买入", "主线", "涨价", "订单", "量产", "并购", "重组", "英伟达", "算力", "机器人")
THEME_NOISE = set(RISK_WORDS) | {"停牌", "复牌", "异动公告", "公告", "热榜", "涨停", "跌停"}


@dataclass
class Candidate:
    code: str
    name: str = ""
    score: float = 0.0
    role: set[str] = field(default_factory=set)
    themes: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    risk_hits: set[str] = field(default_factory=set)
    strong_hits: set[str] = field(default_factory=set)
    company_impacts: list[dict[str, Any]] = field(default_factory=list)

    def add(self, score: float, reason: str, evidence: str = "", role: str = "", themes: list[str] | None = None, text: str = "") -> None:
        self.score += score
        if reason and reason not in self.reasons:
            self.reasons.append(reason)
        if evidence and evidence not in self.evidence:
            self.evidence.append(evidence)
        if role:
            self.role.add(role)
        for theme in themes or []:
            theme_text = str(theme).strip()
            if theme_text and theme_text not in THEME_NOISE and not CODE_RE.fullmatch(theme_text):
                self.themes.add(theme_text)
        hay = f"{reason} {text}"
        for word in RISK_WORDS:
            if word in hay:
                self.risk_hits.add(word)
        for word in STRONG_WORDS:
            if word in hay:
                self.strong_hits.add(word)

    def add_impact(self, row: dict[str, Any]) -> None:
        impact = {
            "title": clean(row.get("title"), 80),
            "type": row.get("company_impact_type") or "",
            "evidence": row.get("evidence_level") or "",
            "shortline": row.get("shortline_view") or "",
            "institution": row.get("institution_view") or "",
            "horizon": row.get("value_horizon") or "",
            "valuation": row.get("valuation_logic") or "",
            "path": row.get("realization_path") or "",
            "risks": row.get("impact_risks") or "",
            "source": row.get("path") or "",
        }
        key = (impact["title"], impact["type"], impact["source"])
        existing = {(x.get("title"), x.get("type"), x.get("source")) for x in self.company_impacts}
        if key not in existing:
            self.company_impacts.append(impact)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def session_name() -> str:
    hhmm = int(datetime.now().strftime("%H%M"))
    if hhmm < 900:
        return "盘前版"
    if hhmm < 930:
        return "竞价版"
    if hhmm <= 1130:
        return "早盘盘中版"
    if hhmm <= 1505:
        return "盘中版"
    if hhmm < 2200:
        return "盘后更新版"
    return "22:30夜间版"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def append_unique_jsonl(path: Path, value: dict[str, Any], key: str) -> bool:
    identity = value.get(key)
    if identity and any(row.get(key) == identity for row in iter_jsonl(path)):
        return False
    append_jsonl(path, value)
    return True


def clean(value: Any, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().replace("|", "/")[:limit]


def next_weekday(date: str, offset: int) -> str:
    day = datetime.strptime(date, "%Y-%m-%d").date()
    count = 0
    while count < offset:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return day.isoformat()


def code_norm(value: Any) -> str:
    raw = str(value or "")
    match = CODE_RE.search(raw)
    return match.group(0) if match else ""


def get_candidate(candidates: dict[str, Candidate], code: str, name: str = "") -> Candidate:
    code = code_norm(code)
    if not code:
        return Candidate("")
    item = candidates.setdefault(code, Candidate(code=code))
    if name and not item.name:
        item.name = clean(name, 16)
    return item


def latest_existing(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def load_evening(date: str) -> dict[str, Any]:
    return read_json(OUT_ROOT.parent / "晚间个股线索" / date / "evening-stock-news-radar.json", {})


def extract_name_near_code(text: str, code: str) -> str:
    for pattern in [
        rf"\|\s*{code}\s*\|\s*([^|\n]+?)\s*\|",
        rf"{code}\s*\|\s*([\u4e00-\u9fa5A-Za-z0-9＊*STst]{{2,12}})",
        rf"{code}\s+([\u4e00-\u9fa5A-Za-z0-9＊*STst]{{2,12}})",
    ]:
        m = re.search(pattern, text)
        if m:
            name = clean(m.group(1), 16)
            if 1 < len(name) <= 16 and name not in {"名称", "股票名称"}:
                return name
    return ""


def parse_holdings_section(text: str, source: str, markers: tuple[str, ...]) -> list[dict[str, str]]:
    for marker in markers:
        if marker not in text:
            continue
        section = text.split(marker, 1)[1]
        section = re.split(r"\n##\s+", section, maxsplit=1)[0]
        rows: list[dict[str, str]] = []
        for line in section.splitlines():
            if "|" not in line or not CODE_RE.search(line):
                continue
            code = code_norm(line)
            if not code:
                continue
            if re.search(r"清仓|已清|期末\s*0|预估期末\s*\|\s*0|0（清仓）", line):
                continue
            if not re.search(r"持有|新建|加仓|\+\d|期末|当前持仓|终态持仓", line):
                continue
            rows.append({"code": code, "name": extract_name_near_code(line, code), "source": source})
        if rows:
            dedup: dict[str, dict[str, str]] = {}
            for row in rows:
                dedup[row["code"]] = row
            return list(dedup.values())
    return []


def collect_holdings_from_terminal_sources(date: str) -> list[dict[str, str]]:
    files = [
        RAW / "02-每日复盘" / f"{date}-复盘.md",
        ROOT / "wiki" / "06-持仓与资金管理" / f"{date}-交割单.md",
        RAW / "01-交割单" / date / "交割单.md",
    ]
    markers = (
        "## 终态持仓",
        "## 当前持仓表",
        "## 5. 持仓与资金",
        "## 三、当日持仓变动",
        "## 当日持仓变动",
    )
    for path in files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rows = parse_holdings_section(text, rel(path), markers)
        if rows:
            return rows
    return []


def collect_holdings(date: str) -> list[dict[str, str]]:
    terminal_rows = collect_holdings_from_terminal_sources(date)
    if terminal_rows:
        return terminal_rows
    evening = load_evening(date)
    rows = evening.get("持仓票") or []
    if rows:
        return [{"code": code_norm(row.get("股票代码")), "name": row.get("股票名称") or "", "source": row.get("来源文件") or ""} for row in rows if code_norm(row.get("股票代码"))]
    return []


def add_three_board(candidates: dict[str, Candidate], date: str) -> None:
    path = RAW / "04-市场数据/三榜热度合并" / date / "三榜热度合并.json"
    data = read_json(path, {})
    for row in data.get("股票") or []:
        code = code_norm(row.get("代码"))
        if not code:
            continue
        item = get_candidate(candidates, code, row.get("名称") or "")
        rank = int(row.get("综合排名") or 99)
        source_count = int(row.get("来源数量") or len(row.get("来源榜单") or []))
        score = max(0, 38 - rank) + source_count * 8
        if row.get("连板标记"):
            score += 18
        reason = f"三榜合并综合排名{rank}，来源{source_count}个"
        if row.get("连板标记"):
            reason += f"，{row.get('连板标记')}"
        item.add(score, reason, rel(path), "热度强度", row.get("概念标签") or [], json.dumps(row, ensure_ascii=False))


def add_daily_info(candidates: dict[str, Candidate], date: str) -> None:
    path = RAW / "11-Codex分析产物/每日重要信息Top10" / date / "daily-important-info-top10.json"
    data = read_json(path, {})
    for row in data.get("rows") or []:
        codes = [code_norm(x) for x in row.get("stock_codes") or []]
        codes = [x for x in codes if x]
        if not codes:
            continue
        for code in codes:
            item = get_candidate(candidates, code)
            base = min(35, float(row.get("score") or 0) * 0.25)
            if row.get("direction") == "负向/风险":
                base -= 10
            impact_type = row.get("company_impact_type") or ""
            evidence_level = row.get("evidence_level") or ""
            if impact_type in {"估值重估型", "长期利好/预期差型", "业绩弹性型"}:
                base += 8
            if "风险" in impact_type:
                base -= 8
            if str(evidence_level).startswith("A-"):
                base += 5
            elif str(evidence_level).startswith("D-"):
                base -= 4
            item.add(base, f"重要信息：{clean(row.get('title'), 60)}；{clean(row.get('reason'), 80)}", row.get("path") or rel(path), "消息催化", row.get("themes") or [], json.dumps(row, ensure_ascii=False))
            item.add_impact(row)


def add_evening_clues(candidates: dict[str, Candidate], date: str) -> None:
    path = OUT_ROOT.parent / "晚间个股线索" / date / "evening-stock-news-radar.json"
    data = read_json(path, {})
    for key in ("高优先线索", "全部线索"):
        for row in data.get(key) or []:
            code = code_norm(row.get("股票代码"))
            if not code:
                continue
            item = get_candidate(candidates, code, row.get("股票名称") or "")
            score = min(30, float(row.get("重要度评分") or 0) * 0.45)
            if row.get("风险词"):
                score -= 8
            item.add(score, f"晚间线索：{clean(row.get('标题'), 70)}", row.get("来源文件") or rel(path), "晚间线索", row.get("题材词") or [], json.dumps(row, ensure_ascii=False))


def add_hotlists(candidates: dict[str, Candidate], date: str) -> None:
    paths = [
        RAW / "04-市场数据/热榜" / date / "淘股吧热榜100-latest.json",
        RAW / "04-市场数据/同花顺热榜" / date / "ths-hot-top100.json",
    ]
    for path in paths:
        data = read_json(path, {})
        rows = []
        if isinstance(data, dict):
            for key in ("股票热榜", "rows", "data", "list"):
                value = data.get(key)
                if isinstance(value, list):
                    rows.extend(value)
        elif isinstance(data, list):
            rows = data
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = code_norm(row.get("代码") or row.get("code") or row.get("股票代码") or row.get("f12"))
            if not code:
                continue
            name = row.get("名称") or row.get("name") or row.get("股票名称") or row.get("f14") or ""
            rank = row.get("排名") or row.get("rank") or row.get("序号") or 99
            try:
                rank_i = int(rank)
            except Exception:
                rank_i = 99
            if rank_i > 80:
                continue
            item = get_candidate(candidates, code, name)
            score = max(0, 30 - rank_i * 0.35)
            reason = f"{path.stem}排名{rank_i}"
            if row.get("连板标记"):
                reason += f"，{row.get('连板标记')}"
                score += 12
            item.add(score, reason, rel(path), "热榜", row.get("概念标签") or [], json.dumps(row, ensure_ascii=False))


def add_catalysts(candidates: dict[str, Candidate], date: str) -> None:
    paths = [
        ROOT / ".llm-wiki/catalyst-radar/latest-catalyst-radar.json",
        RAW / "11-Codex分析产物/消息催化评分" / date / "message-catalyst-score.json",
    ]
    for path in paths:
        data = read_json(path, {})
        rows = data.get("top") or data.get("rows") or []
        for row in rows:
            text = json.dumps(row, ensure_ascii=False)
            codes = sorted(set(CODE_RE.findall(text)))
            for code in codes[:16]:
                item = get_candidate(candidates, code)
                direct_text = f"{row.get('title','')} {row.get('reason','')} {' '.join(row.get('keywords') or [])}"
                score = min(12, float(row.get("score") or 60) * 0.08)
                if any(word in direct_text for word in RISK_WORDS):
                    score -= 5
                item.add(score, f"消息雷达：{clean(row.get('title'), 70)}", row.get("path") or rel(path), "消息雷达", row.get("keywords") or [], direct_text)


def add_room_text_candidates(candidates: dict[str, Candidate], date: str) -> None:
    paths = []
    for pattern in [
        f"wiki/07-作战室/{date}-*.md",
        f"wiki/07-作战室/{date.replace('-', '')}-*.md",
    ]:
        paths.extend(ROOT.glob(pattern))
    for path in paths:
        if any(key in path.name for key in ("动态作战室", "每日重要信息Top10", "盘中重大消息雷达", "AI上下文包", "作战总控", "同花顺热榜异动原因")):
            continue
        if not any(key in path.name for key in ("输入候选", "旧题材二次催化候选", "互动易关注点复核", "作战室候选票评分表", "韬定律")):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for code in sorted(set(CODE_RE.findall(text))):
            item = get_candidate(candidates, code)
            item.add(5, f"已进入作战室资料：{path.stem}", rel(path), "作战室已有关注", [], path.stem)


def holding_plan(item: Candidate) -> dict[str, str]:
    risk = "、".join(sorted(item.risk_hits)) or "暂无明显风险词"
    strong = "、".join(sorted(item.strong_hits)) or "暂无明显强势词"
    if item.risk_hits and item.score < 65:
        stance = "偏防守，明天先看竞价和开盘承接，不主动加仓"
        sell = "低开且开盘5-10分钟不能收回均线、板块同步走弱、热榜下滑时，优先减仓或退出。"
    elif item.score >= 85 and item.strong_hits:
        stance = "偏强，持仓有继续观察价值"
        sell = "冲高放量但不能封板/不能带动板块时分批兑现；炸板回落且板块分歧扩大时降低仓位。"
    else:
        stance = "中性观察，按板块和竞价决定去留"
        sell = "竞价不及预期或开盘弱于同题材核心时先去弱；只有承接强、热度继续上升才保留。"
    return {
        "当前定位": "持仓票优先处理",
        "我的判断": stance,
        "强势依据": strong,
        "风险依据": risk,
        "明天处理": sell,
        "加权条件": "仅在竞价强于板块、热榜/题材继续升温、开盘承接不破分时均线时考虑加权；否则不加。",
        "不确定点": "需要用9:15/9:20/9:25竞价、板块强度和开盘承接校准。",
    }


def candidate_plan(item: Candidate, rank: int) -> dict[str, str]:
    if rank == 1:
        role = "主计划候选"
    elif rank <= 3:
        role = "强备选候选"
    else:
        role = "观察候选"
    if item.risk_hits:
        role = "风险复核候选"
    return {
        "角色": role,
        "我的判断": "当前强度靠前，但必须等竞价和板块验证，不能无条件买入。",
        "买入触发": "竞价排名/热度继续靠前，所属题材有2只以上强反馈，开盘承接强或换手回封，且不是单票孤立冲高。",
        "禁止买入": "低开低走、热榜明显下滑、板块无扩散、核心票炸板/补跌、消息被澄清或只是泛热度。",
        "卖出/止损": "买后不能快速脱离成本区、板块转弱、炸板回落、同题材核心走弱时，不恋战；冲高无板块跟随时分批兑现。",
        "验证点": "竞价强度、涨停质量、热榜跃迁、板块扩散、D+1溢价。",
        "不确定点": "当前是资料强度排序，不等同于盘口确认；需要你校准是否符合你的最强票模式。",
    }


def infer_warroom_mode(item: Candidate, is_holding: bool) -> dict[str, Any]:
    hay = " ".join([*item.reasons, *item.role, *item.themes, *item.strong_hits, *item.risk_hits])
    secondary: list[str] = []
    if is_holding:
        secondary.append("持仓处理优先")
    if "一字" in hay:
        primary = "一字定方向扩散"
        entry_type = "换手前排确认"
        evidence = "出现一字/强封单信号，优先看同题材换手前排扩散。"
    elif "弱转强" in hay or "回封" in hay:
        primary = "分歧转一致"
        entry_type = "弱转强/回封确认"
        evidence = "出现弱转强或回封信号，核心是分歧后重新转强。"
    elif "机器人" in hay and ("低位" in hay or "补涨" in hay):
        primary = "高低切补涨"
        entry_type = "低位前排确认"
        evidence = "主线高位分歧时，机器人低位/补涨语境更强。"
    elif "中军" in hay or "容量" in hay or "趋势" in hay:
        primary = "趋势主升"
        entry_type = "容量中军趋势确认"
        evidence = "出现趋势/容量/中军语境，重点看持续放量和板块承接。"
        secondary.append("容量中军锚定")
    elif "连板" in hay or "涨停" in hay or "实盘赛买入" in hay:
        primary = "前排确认打板"
        entry_type = "涨停确认/前排换手"
        evidence = "出现涨停、连板或实盘赛买入信号，重点验证前排地位和封板质量。"
    else:
        primary = "强板块前排半路"
        entry_type = "板块共振半路"
        evidence = "资料强度靠前但模式未充分确认，先按强板块前排半路观察。"

    if "主线" in hay:
        secondary.append("题材主升核心持股")
    if "退潮" in hay or "补跌" in hay or "跌停" in hay:
        secondary.append("风险锚减仓")
    if "监管" in hay or "异动" in hay:
        secondary.append("绕异动控节奏")
    secondary = list(dict.fromkeys(x for x in secondary if x != primary))
    return {
        "primaryMode": primary,
        "secondaryModes": secondary[:4],
        "entryType": entry_type,
        "buyPoint": "只在竞价强于同题材核心、板块有2只以上强反馈、开盘承接不弱时触发；否则只观察。",
        "sellPoint": "冲高不能封板/不能带动板块、炸板不回封、板块转弱或热榜明显下滑时兑现或降仓。",
        "invalidCondition": "低开低走、单票孤立、消息被澄清、核心票补跌、退潮亏钱效应扩散。",
        "modeEvidence": evidence,
    }


def entry_reason(item: Candidate, is_holding: bool, rank: int) -> str:
    parts = []
    if is_holding:
        parts.append("持仓票优先，必须先给出明日处理方案")
    if rank <= 5:
        parts.append(f"动态总分第{rank}")
    if any("三榜合并综合排名" in reason for reason in item.reasons):
        parts.append("三榜/热榜资金关注靠前")
    if item.strong_hits:
        parts.append(f"强势信号：{'、'.join(sorted(item.strong_hits)[:6])}")
    if item.risk_hits:
        parts.append(f"需风险复核：{'、'.join(sorted(item.risk_hits)[:5])}")
    if not parts:
        parts.append("综合资料强度进入候选池")
    return "；".join(parts)


def verify_basis(row: dict[str, Any]) -> list[str]:
    plan = row.get("plan") or {}
    return [
        "竞价是否强于同题材核心",
        "开盘5-10分钟是否有承接",
        "是否继续进入三榜/淘股吧/同花顺热榜前排",
        "所属题材是否扩散到2只以上强反馈",
        "D+1是否有溢价或至少不弱于板块",
        clean(plan.get("禁止买入") or plan.get("明天处理"), 120),
    ]


def company_impact_summary(item: Candidate) -> dict[str, str]:
    impacts = item.company_impacts[:5]
    if not impacts:
        return {
            "type": "未形成公司价值判断",
            "evidence": "-",
            "shortline": "仅按热榜/消息/持仓强度观察，尚未形成独立公司影响判断。",
            "institution": "缺少公司价值映射，不能写成长线或估值重估逻辑。",
            "horizon": "-",
            "valuation": "-",
            "path": "-",
            "risks": "主要风险是只有热度、没有公司证据。",
        }
    priority = {"长期风险型": 6, "短线风险型": 6, "估值重估型": 5, "长期利好/预期差型": 4, "业绩弹性型": 4, "短炒型": 2}
    if item.risk_hits:
        risk_impacts = [x for x in impacts if "风险" in str(x.get("type") or "")]
        best = sorted(risk_impacts or impacts, key=lambda x: priority.get(str(x.get("type")), 1), reverse=True)[0]
    else:
        best = sorted(impacts, key=lambda x: priority.get(str(x.get("type")), 1), reverse=True)[0]
    evidence = "、".join(dict.fromkeys(str(x.get("evidence") or "-") for x in impacts))[:120]
    return {
        "type": str(best.get("type") or "-"),
        "evidence": evidence or "-",
        "shortline": clean(best.get("shortline"), 150),
        "institution": clean(best.get("institution"), 180),
        "horizon": clean(best.get("horizon"), 120),
        "valuation": clean(best.get("valuation"), 180),
        "path": clean(best.get("path"), 180),
        "risks": clean(best.get("risks"), 180),
    }


def build(date: str) -> dict[str, Any]:
    candidates: dict[str, Candidate] = {}
    holdings = collect_holdings(date)
    for row in holdings:
        item = get_candidate(candidates, row["code"], row.get("name", ""))
        item.add(28, "当前持仓票，优先分析明日处理", row.get("source", ""), "持仓")
    add_three_board(candidates, date)
    add_hotlists(candidates, date)
    add_daily_info(candidates, date)
    add_evening_clues(candidates, date)
    add_catalysts(candidates, date)
    add_room_text_candidates(candidates, date)

    rows = [item for item in candidates.values() if item.code]
    rows.sort(key=lambda x: x.score, reverse=True)
    top5 = rows[:5]
    holding_codes = {row["code"] for row in holdings}
    payload_rows = []
    for idx, item in enumerate(rows, start=1):
        plan = holding_plan(item) if item.code in holding_codes else candidate_plan(item, idx)
        mode = infer_warroom_mode(item, item.code in holding_codes)
        plan.update(
            {
                "主模式": mode["primaryMode"],
                "买点类型": mode["entryType"],
                "模式买点": mode["buyPoint"],
                "模式卖点": mode["sellPoint"],
                "模式失效": mode["invalidCondition"],
            }
        )
        payload_rows.append(
            {
                "rank": idx,
                "code": item.code,
                "name": item.name,
                "score": round(item.score, 2),
                "roles": sorted(item.role),
                "themes": sorted(item.themes)[:10],
                "reasons": item.reasons[:8],
                "evidence": item.evidence[:8],
                "riskHits": sorted(item.risk_hits),
                "strongHits": sorted(item.strong_hits),
                "companyImpacts": item.company_impacts[:8],
                "companyImpactSummary": company_impact_summary(item),
                "plan": plan,
                "isHolding": item.code in holding_codes,
                "entryReason": entry_reason(item, item.code in holding_codes, idx),
                **mode,
            }
        )
        payload_rows[-1]["verifyBasis"] = verify_basis(payload_rows[-1])
    top_codes = [row["code"] for row in payload_rows[:5]]
    signature = hashlib.sha1("|".join(top_codes + [str((payload_rows[i].get("plan") or {}).get("我的判断", "")) for i in range(min(5, len(payload_rows))) ]).encode("utf-8")).hexdigest()[:16]
    return {
        "schema": "73wiki-dynamic-warroom-top5-v1",
        "date": date,
        "generatedAt": now_text(),
        "session": session_name(),
        "signature": signature,
        "holdings": holdings,
        "top5": payload_rows[:5],
        "holdingsAnalysis": [row for row in payload_rows if row["isHolding"]],
        "allCandidates": payload_rows[:50],
        "change": {},
        "rules": {
            "boundary": "这是动态作战室候选和持仓处理方案，不是自动交易指令；最终以竞价、板块、盘口和用户仓位纪律确认。",
            "changeLogic": "每次运行重新吸收热榜、消息、持仓、作战室、晚间线索；Top5或持仓观点变化才发飞书。",
        },
    }


def change_details(payload: dict[str, Any], old: dict[str, Any]) -> dict[str, Any]:
    old_rows = {row.get("code"): row for row in old.get("top5Rows") or [] if isinstance(row, dict)}
    old_codes = old.get("top5") or list(old_rows)
    new_rows = {row.get("code"): row for row in payload.get("top5") or []}
    new_codes = list(new_rows)
    added = [code for code in new_codes if code not in old_codes]
    removed = [code for code in old_codes if code not in new_codes]
    stayed = [code for code in new_codes if code in old_codes]
    rank_changes = []
    for code in stayed:
        old_rank = int((old_rows.get(code) or {}).get("rank") or old_codes.index(code) + 1)
        new_rank = int((new_rows.get(code) or {}).get("rank") or new_codes.index(code) + 1)
        if old_rank != new_rank:
            rank_changes.append({"code": code, "oldRank": old_rank, "newRank": new_rank, "reason": f"动态分数/证据变化导致排名从{old_rank}到{new_rank}"})
    added_detail = []
    for code in added:
        row = new_rows.get(code) or {}
        added_detail.append(
            {
                "code": code,
                "name": row.get("name") or "",
                "reason": row.get("entryReason") or clean("; ".join(row.get("reasons") or []), 160),
                "score": row.get("score"),
            }
        )
    removed_detail = []
    for code in removed:
        old_row = old_rows.get(code) or {"code": code}
        removed_detail.append(
            {
                "code": code,
                "name": old_row.get("name") or "",
                "reason": "跌出当前Top5，原因通常是新候选分数/热度/持仓优先级超过它；后续若重新进热榜或有新催化再调入。",
                "oldScore": old_row.get("score"),
            }
        )
    return {
        "added": added,
        "removed": removed,
        "rankChanges": rank_changes,
        "addedDetail": added_detail,
        "removedDetail": removed_detail,
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 动态作战室Top5",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 版本：{payload['session']}",
        f"- 签名：{payload['signature']}",
        f"- 使用边界：{payload['rules']['boundary']}",
        "",
        "## 本次变化",
        "",
    ]
    change = payload.get("change") or {}
    added_detail = change.get("addedDetail") or []
    removed_detail = change.get("removedDetail") or []
    rank_changes = change.get("rankChanges") or []
    if not (added_detail or removed_detail or rank_changes):
        lines.append("- Top5和上次通知相比无明显变化，继续保留当前排序。")
    for item in added_detail:
        lines.append(f"- 调入：{item.get('name') or item.get('code')} {item.get('code')}，原因：{item.get('reason')}")
    for item in removed_detail:
        lines.append(f"- 调出：{item.get('name') or item.get('code')} {item.get('code')}，原因：{item.get('reason')}")
    for item in rank_changes:
        lines.append(f"- 排名变化：{item.get('code')}，{item.get('reason')}")
    lines.extend(
        [
            "",
        "## 持仓票处理优先",
        "",
        ]
    )
    if not payload["holdingsAnalysis"]:
        lines.append("- 未识别到持仓票，或持仓票暂未进入候选资料池。")
    for row in payload["holdingsAnalysis"]:
        plan = row["plan"]
        impact = row.get("companyImpactSummary") or {}
        lines.extend(
            [
                f"### {row['name'] or row['code']} {row['code']}",
                "",
                f"- 当前分：{row['score']}；角色：{', '.join(row['roles']) or '-'}",
                f"- 主模式：{row.get('primaryMode')}；买点类型：{row.get('entryType')}",
                f"- 公司影响：{impact.get('type')}；证据：{impact.get('evidence')}；兑现周期：{impact.get('horizon')}",
                f"- 机构/价值逻辑：{impact.get('institution')}",
                f"- 估值/业绩映射：{impact.get('valuation')}",
                f"- 兑现路径：{impact.get('path')}",
                f"- 公司影响风险：{impact.get('risks')}",
                f"- 我的判断：{plan['我的判断']}",
                f"- 模式证据：{row.get('modeEvidence')}",
                f"- 强势依据：{plan['强势依据']}",
                f"- 风险依据：{plan['风险依据']}",
                f"- 明天处理：{plan['明天处理']}",
                f"- 加权条件：{plan['加权条件']}",
                f"- 不确定点：{plan['不确定点']}",
                f"- 事后验证依据：{'；'.join(row.get('verifyBasis') or [])}",
                f"- 主要证据：{'; '.join(row['reasons'][:4])}",
                "",
            ]
        )
    lines.extend(["## 当前Top5", "", "| 排名 | 股票 | 分数 | 角色 | 公司影响 | 证据 | 主模式 | 买点类型 | 入选原因 | 短线触发 | 机构/价值判断 | 禁止买入/退出 |", "|---:|---|---:|---|---|---|---|---|---|---|---|---|"])
    for row in payload["top5"]:
        plan = row["plan"]
        impact = row.get("companyImpactSummary") or {}
        lines.append(
            f"| {row['rank']} | {row['name'] or row['code']} {row['code']} | {row['score']} | {plan.get('角色') or plan.get('当前定位')} | {impact.get('type','-')} | {clean(impact.get('evidence','-'), 60)} | {row.get('primaryMode')} | {row.get('entryType')} | {clean(row.get('entryReason'), 120)} | {clean(plan.get('买入触发') or plan.get('加权条件'), 100)} | {clean(impact.get('institution','-'), 110)} | {clean(plan.get('禁止买入') or plan.get('明天处理'), 100)} |"
        )
    lines.extend(["", "## 调用证据", "", "| 股票 | 证据 |", "|---|---|"])
    for row in payload["top5"]:
        lines.append(f"| {row['name'] or row['code']} | {'; '.join('`'+x+'`' for x in row['evidence'][:5]) or '-'} |")
    return "\n".join(lines) + "\n"


def render_notify(payload: dict[str, Any], changed: dict[str, Any]) -> str:
    holdings = [row for row in payload["top5"] if row.get("isHolding")]
    non_holdings = [row for row in payload["top5"] if not row.get("isHolding")]
    lines = [
        "【动态作战室Top5变更待校准】",
        f"时间：{payload['generatedAt']}",
        f"版本：{payload['session']}",
        "",
        "这条通知的目的：让你校准“动态作战室排序和持仓处理逻辑”，不是让你现在决定买卖。",
        "",
        "你只需要判断两件事：",
        "1. 持仓票：我给的明日处理思路是否合理，是否高估/低估风险。",
        "2. 非持仓票：它是否值得继续放在作战室观察，不是让你直接买。",
        "",
        "推荐回复格式：",
        "- 持仓：第几条 + 处理合理/高估/低估/反向 + 一句话原因。",
        "- 候选：第几条 + 保留/剔除/高估/低估 + 一句话原因。",
        "",
        f"变化：调入 {', '.join(changed.get('added') or []) or '-'}；调出 {', '.join(changed.get('removed') or []) or '-'}",
        "",
    ]
    for item in changed.get("addedDetail") or []:
        lines.append(f"调入原因：{item.get('name') or item.get('code')} {item.get('code')}：{item.get('reason')}")
    for item in changed.get("removedDetail") or []:
        lines.append(f"调出原因：{item.get('name') or item.get('code')} {item.get('code')}：{item.get('reason')}")
    if changed.get("rankChanges"):
        for item in changed["rankChanges"]:
            lines.append(f"排名变化：{item.get('code')}：{item.get('reason')}")
    if changed.get("addedDetail") or changed.get("removedDetail") or changed.get("rankChanges"):
        lines.append("")
    if holdings:
        lines.extend(["一、持仓票优先校准", ""])
    item_no = 1
    for row in holdings:
        plan = row["plan"]
        impact = row.get("companyImpactSummary") or {}
        lines.extend(
            [
                f"{item_no}. {row['name'] or row['code']} {row['code']}（持仓处理）",
                f"   系统结论：{plan.get('我的判断')}；不是无条件加仓。",
                "   请你校准：明天按这个处理是否合理？风险是不是被我高估/低估？",
                f"   公司影响：{impact.get('type')}；证据等级：{impact.get('evidence')}；兑现周期：{impact.get('horizon')}",
                f"   机构/价值逻辑：{impact.get('institution')}",
                f"   估值/业绩映射：{impact.get('valuation')}",
                f"   兑现路径：{impact.get('path')}",
                f"   公司影响风险：{impact.get('risks')}",
                f"   主模式/买点：{row.get('primaryMode')} / {row.get('entryType')}。",
                f"   模式证据：{clean(row.get('modeEvidence'), 150)}",
                f"   我为什么这么想：{clean(row.get('entryReason'), 160)}。",
                f"   模式买点：{clean(row.get('buyPoint'), 150)}",
                f"   明天只有这样才偏强：{clean(plan.get('加权条件'), 150)}",
                f"   走弱处理：{clean(plan.get('明天处理'), 150)}",
                f"   模式失效：{clean(row.get('invalidCondition'), 150)}",
                f"   需要你重点纠偏：{plan.get('不确定点')}",
                "",
            ]
        )
        item_no += 1

    if non_holdings:
        lines.extend(["二、新开仓/观察候选校准", ""])
    for row in non_holdings:
        plan = row["plan"]
        impact = row.get("companyImpactSummary") or {}
        if row.get("riskHits"):
            conclusion = "只进入风险复核观察，不是买点"
        elif row.get("rank", 99) <= 3:
            conclusion = "可保留强备选，但必须等竞价和板块确认"
        else:
            conclusion = "观察候选，除非明天继续升温，否则不主动买"
        lines.extend(
            [
                f"{item_no}. {row['name'] or row['code']} {row['code']}（候选观察）",
                f"   系统结论：{conclusion}。",
                "   请你校准：它应不应该继续留在作战室Top5？是否只是热度噪音？",
                f"   公司影响：{impact.get('type')}；证据等级：{impact.get('evidence')}；兑现周期：{impact.get('horizon')}",
                f"   机构/价值逻辑：{impact.get('institution')}",
                f"   估值/业绩映射：{impact.get('valuation')}",
                f"   兑现路径：{impact.get('path')}",
                f"   公司影响风险：{impact.get('risks')}",
                f"   主模式/买点：{row.get('primaryMode')} / {row.get('entryType')}。",
                f"   模式证据：{clean(row.get('modeEvidence'), 150)}",
                f"   入选原因：{clean(row.get('entryReason'), 160)}。",
                f"   模式买点：{clean(row.get('buyPoint'), 150)}",
                f"   明天触发条件：{clean(plan.get('买入触发'), 150)}",
                f"   禁止/剔除条件：{clean(plan.get('禁止买入'), 150)}",
                f"   模式失效：{clean(row.get('invalidCondition'), 150)}",
                f"   需要你重点纠偏：{plan.get('不确定点')}",
                "",
            ]
        )
        item_no += 1
    lines.extend(
        [
            "三、我这套排序当前的已知缺陷",
            "",
            "- 这是资料强度排序，主要吃热榜、三榜、持仓、消息、作战室线索，不等于盘口买点。",
            "- 周末/盘后没有竞价和分时承接，只能做候选筛选，不能替代明天 9:15/9:20/9:25 校验。",
            "- 如果你觉得某票只是热度噪音，直接回复“第几条 + 剔除/高估 + 原因”，我会回写降权。",
            "",
        ]
    )
    return "\n".join(lines)


def should_notify_change(changed: dict[str, Any], force: bool) -> tuple[bool, str]:
    if force:
        return True, "force_notify"
    if changed.get("addedDetail") or changed.get("removedDetail"):
        return True, "top5_added_or_removed"
    rank_changes = changed.get("rankChanges") or []
    if not rank_changes:
        return False, "same_signature_or_no_material_change"
    material = [
        item for item in rank_changes
        if min(int(item.get("oldRank") or 99), int(item.get("newRank") or 99)) <= 3
        or abs(int(item.get("oldRank") or 0) - int(item.get("newRank") or 0)) >= 2
    ]
    if material:
        return True, "material_rank_change"
    return False, "minor_rank_change_only"


def render_notify_legacy(payload: dict[str, Any], changed: dict[str, Any]) -> str:
    lines = [
        "【动态作战室Top5变更待校准】",
        f"时间：{payload['generatedAt']}",
        f"版本：{payload['session']}",
        "",
        "判断对象：下面每一条是“作战室候选/持仓处理方案”，不是自动交易指令。",
        "你要校准的是：我选得对不对、逻辑是否高估/低估、买卖条件是否合理。",
        "回复格式：第几条 + 有效/一般/无效/反向/高估/低估 + 一句话原因。",
        "",
        f"变化：调入 {', '.join(changed.get('added') or []) or '-'}；调出 {', '.join(changed.get('removed') or []) or '-'}",
        "",
    ]
    for item in changed.get("addedDetail") or []:
        lines.append(f"调入原因：{item.get('name') or item.get('code')} {item.get('code')}：{item.get('reason')}")
    for item in changed.get("removedDetail") or []:
        lines.append(f"调出原因：{item.get('name') or item.get('code')} {item.get('code')}：{item.get('reason')}")
    if changed.get("rankChanges"):
        for item in changed["rankChanges"]:
            lines.append(f"排名变化：{item.get('code')}：{item.get('reason')}")
    if changed.get("addedDetail") or changed.get("removedDetail") or changed.get("rankChanges"):
        lines.append("")
    for idx, row in enumerate(payload["top5"], start=1):
        plan = row["plan"]
        current = "有效" if row["score"] >= 85 and not row["riskHits"] else "一般" if not row["riskHits"] else "待风险复核"
        lines.extend(
            [
                f"{idx}. {row['name'] or row['code']} {row['code']}",
                f"   你要判断：它是否应该进入当前动态作战室Top5，或持仓是否该按这个方案处理。",
                f"   我当前判断：{current}，分数 {row['score']}，角色 {plan.get('角色') or plan.get('当前定位')}",
                f"   我的判断逻辑：{clean('; '.join(row['reasons'][:4]), 220)}",
                f"   入选原因：{clean(row.get('entryReason'), 180)}",
                f"   我认为可能有用的点：{clean(plan.get('买入触发') or plan.get('加权条件'), 180)}",
                f"   我不确定/需要你纠偏：{plan.get('不确定点')}",
                f"   禁止/退出条件：{clean(plan.get('禁止买入') or plan.get('明天处理'), 180)}",
                f"   事后验证依据：{clean('；'.join(row.get('verifyBasis') or []), 180)}",
                "",
            ]
        )
    return "\n".join(lines)


def write_outputs(payload: dict[str, Any], apply_wiki: bool) -> None:
    out = OUT_ROOT / payload["date"]
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "dynamic-warroom-top5.json", payload)
    md = render_md(payload)
    (out / "dynamic-warroom-top5.md").write_text(md, encoding="utf-8")
    WIKI_ROOM.mkdir(parents=True, exist_ok=True)
    (WIKI_ROOM / f"{payload['date']}-动态作战室Top5.md").write_text(md, encoding="utf-8")
    (WIKI_ROOM / "当前动态作战室Top5.md").write_text(md, encoding="utf-8")
    append_unique_jsonl(FACTS, {"version_id": f"{payload['date']}:{payload['signature']}", **payload}, "version_id")
    write_change_log(payload)
    backfill_change_log_from_versions()
    write_predictions(payload)
    if apply_wiki:
        update_stock_cards(payload)
        update_theme_cards(payload)
        update_dynamic_queue(payload)


def update_stock_cards(payload: dict[str, Any]) -> None:
    WIKI_STOCK.mkdir(parents=True, exist_ok=True)
    for row in [*payload.get("holdingsAnalysis", []), *payload.get("top5", [])]:
        code = row["code"]
        name = row.get("name") or code
        path = WIKI_STOCK / f"{name}-{code}.md"
        marker = f"<!-- dynamic-warroom:{payload['date']}:{code} -->"
        impact = row.get("companyImpactSummary") or {}
        block = "\n".join(
            [
                "",
                marker,
                f"## {payload['date']} 动态作战室更新",
                "",
                f"- 更新时间：{payload['generatedAt']}（{payload['session']}）",
                f"- 当前分：{row['score']}",
                f"- 角色：{', '.join(row['roles']) or '-'}",
                f"- 题材：{', '.join(row['themes']) or '-'}",
                f"- 公司影响：{impact.get('type','-')}；证据：{impact.get('evidence','-')}；兑现周期：{impact.get('horizon','-')}",
                f"- 短线资金逻辑：{impact.get('shortline','-')}",
                f"- 机构/价值逻辑：{impact.get('institution','-')}",
                f"- 估值/业绩映射：{impact.get('valuation','-')}",
                f"- 兑现路径：{impact.get('path','-')}",
                f"- 公司影响风险：{impact.get('risks','-')}",
                f"- 我的判断：{row['plan'].get('我的判断')}",
                f"- 处理/触发：{row['plan'].get('买入触发') or row['plan'].get('加权条件')}",
                f"- 禁止/退出：{row['plan'].get('禁止买入') or row['plan'].get('明天处理')}",
                f"- 证据：{'; '.join(row['reasons'][:5]) or '-'}",
                f"- 来源：`wiki/07-作战室/{payload['date']}-动态作战室Top5.md`",
                "",
            ]
        )
        if not path.exists():
            path.write_text(f"# {name} {code}\n\n> 自动创建：动态作战室首次覆盖该股。正式个股卡后续可补全公司、题材、模式和风险结构。\n{block}", encoding="utf-8")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if marker in text:
            text = re.sub(rf"\n?{re.escape(marker)}\n## {re.escape(payload['date'])} 动态作战室更新\n.*?(?=\n<!-- dynamic-warroom:|\n## |\Z)", block.strip() + "\n", text, flags=re.S)
        else:
            text = text.rstrip() + "\n" + block
        path.write_text(text, encoding="utf-8")


def safe_filename(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]", "-", value.strip())
    value = re.sub(r"\s+", "", value)
    return value[:60] or "未分类题材"


def update_theme_cards(payload: dict[str, Any]) -> None:
    WIKI_THEME.mkdir(parents=True, exist_ok=True)
    by_theme: dict[str, list[dict[str, Any]]] = {}
    for row in [*payload.get("holdingsAnalysis", []), *payload.get("top5", [])]:
        for theme in row.get("themes") or []:
            theme = clean(theme, 30)
            if not theme or CODE_RE.fullmatch(theme):
                continue
            by_theme.setdefault(theme, []).append(row)
    for theme, rows in by_theme.items():
        path = WIKI_THEME / f"{safe_filename(theme)}.md"
        marker = f"<!-- dynamic-warroom-theme:{payload['date']}:{theme} -->"
        names = "、".join(f"{row.get('name') or row['code']}({row['code']})" for row in rows[:8])
        evidence = "；".join(clean(reason, 60) for row in rows[:5] for reason in row.get("reasons", [])[:2])
        block = "\n".join(
            [
                "",
                marker,
                f"## {payload['date']} 动态作战室题材更新",
                "",
                f"- 更新时间：{payload['generatedAt']}（{payload['session']}）",
                f"- 关联个股：{names or '-'}",
                f"- 题材状态：进入动态作战室证据链，需结合热榜、竞价、涨停扩散和持仓反馈验证。",
                f"- 主要证据：{evidence or '-'}",
                f"- 来源：`wiki/07-作战室/{payload['date']}-动态作战室Top5.md`",
                "",
            ]
        )
        if not path.exists():
            path.write_text(f"# {theme}\n\n> 自动创建：动态作战室首次覆盖该题材。后续补充题材定义、核心股、扩散路径、失效条件。\n{block}", encoding="utf-8")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if marker in text:
            text = re.sub(rf"\n?{re.escape(marker)}\n## {re.escape(payload['date'])} 动态作战室题材更新\n.*?(?=\n<!-- dynamic-warroom-theme:|\n## |\Z)", block.strip() + "\n", text, flags=re.S)
        else:
            text = text.rstrip() + "\n" + block
        path.write_text(text, encoding="utf-8")


def write_predictions(payload: dict[str, Any]) -> None:
    for row in payload.get("top5") or []:
        plan = row.get("plan") or {}
        prediction = {
            "schema": "73wiki-warroom-candidate-prediction-v1",
            "predictionId": f"dynamic-warroom:{payload['date']}:{payload['signature']}:{row['code']}",
            "date": payload["date"],
            "code": row["code"],
            "name": row.get("name") or "",
            "rank": row.get("rank"),
            "role": plan.get("角色") or plan.get("当前定位") or "",
            "score": row.get("score"),
            "permission": "持仓处理优先" if row.get("isHolding") else plan.get("角色") or "动态候选",
            "condition": plan.get("买入触发") or plan.get("加权条件") or "",
            "forbiddenCondition": plan.get("禁止买入") or plan.get("明天处理") or "",
            "primaryMode": row.get("primaryMode") or "",
            "secondaryModes": row.get("secondaryModes") or [],
            "entryType": row.get("entryType") or "",
            "buyPoint": row.get("buyPoint") or "",
            "sellPoint": row.get("sellPoint") or "",
            "invalidCondition": row.get("invalidCondition") or "",
            "modeEvidence": row.get("modeEvidence") or "",
            "companyImpactSummary": row.get("companyImpactSummary") or {},
            "companyImpacts": row.get("companyImpacts") or [],
            "entryReason": row.get("entryReason") or "",
            "verifyBasis": row.get("verifyBasis") or [],
            "sourcePath": f"wiki/07-作战室/{payload['date']}-动态作战室Top5.md",
            "validationDates": {
                "D+1": next_weekday(payload["date"], 1),
                "D+3": next_weekday(payload["date"], 3),
                "D+5": next_weekday(payload["date"], 5),
            },
            "status": "active",
        }
        append_unique_jsonl(PREDICTIONS, prediction, "predictionId")


def update_dynamic_queue(payload: dict[str, Any]) -> None:
    WIKI_STATS.mkdir(parents=True, exist_ok=True)
    existing_text = QUEUE_MD.read_text(encoding="utf-8", errors="ignore") if QUEUE_MD.exists() else ""
    old_header = "| 版本日 | 签名 | 排名 | 代码 | 名称 | 角色 | 分数 | 入选原因 | 触发条件 | 禁止/退出 | D+1 | D+3 | D+5 | 状态 |\n|---|---|---:|---|---|---|---:|---|---|---|---|---|---|---|"
    new_header = "| 版本日 | 签名 | 排名 | 代码 | 名称 | 角色 | 主模式 | 买点类型 | 分数 | 入选原因 | 触发条件 | 禁止/退出 | D+1 | D+3 | D+5 | 状态 |\n|---|---|---:|---|---|---|---|---|---:|---|---|---|---|---|---|---|"
    if old_header in existing_text:
        existing_text = existing_text.replace(old_header, new_header)
        QUEUE_MD.write_text(existing_text, encoding="utf-8")
    if not QUEUE_MD.exists():
        QUEUE_MD.write_text(
            "\n".join(
                [
                    "# 动态作战室Top5 D+验证队列",
                    "",
                    "用途：记录动态作战室每次Top5入选理由、买卖条件和D+验证节点，避免半年后只记得结果、不记得当时依据。",
                    "",
                    new_header,
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        existing_text = QUEUE_MD.read_text(encoding="utf-8", errors="ignore")
    lines = []
    for row in payload.get("top5") or []:
        key = f"| {payload['date']} | {payload['signature']} | {row.get('rank')} | {row.get('code')} |"
        if key in existing_text:
            continue
        plan = row.get("plan") or {}
        dates = {
            "D+1": next_weekday(payload["date"], 1),
            "D+3": next_weekday(payload["date"], 3),
            "D+5": next_weekday(payload["date"], 5),
        }
        lines.append(
            f"| {payload['date']} | {payload['signature']} | {row.get('rank')} | {row.get('code')} | {row.get('name') or ''} | {clean(plan.get('角色') or plan.get('当前定位'), 40)} | {row.get('primaryMode') or ''} | {row.get('entryType') or ''} | {row.get('score')} | {clean(row.get('entryReason'), 120)} | {clean(plan.get('买入触发') or plan.get('加权条件'), 120)} | {clean(plan.get('禁止买入') or plan.get('明天处理'), 120)} | {dates['D+1']} | {dates['D+3']} | {dates['D+5']} | active |\n"
        )
    if lines:
        with QUEUE_MD.open("a", encoding="utf-8") as handle:
            handle.writelines(lines)


def write_change_log(payload: dict[str, Any]) -> None:
    change = payload.get("change") or {}
    if not any(change.get(key) for key in ("addedDetail", "removedDetail", "rankChanges")):
        return
    event = change_event(payload)
    added = append_unique_jsonl(CHANGE_FACTS, event, "eventId")
    if not added:
        return
    append_change_md_row(event)


def change_event(payload: dict[str, Any]) -> dict[str, Any]:
    change = payload.get("change") or {}
    return {
        "schema": "73wiki-warroom-dynamic-change-v1",
        "eventId": f"{payload['date']}:{payload['signature']}",
        "date": payload["date"],
        "generatedAt": payload["generatedAt"],
        "session": payload["session"],
        "signature": payload["signature"],
        "change": change,
        "top5": [
            {
                "rank": row.get("rank"),
                "code": row.get("code"),
                "name": row.get("name"),
                "score": row.get("score"),
                "primaryMode": row.get("primaryMode"),
                "entryType": row.get("entryType"),
                "entryReason": row.get("entryReason"),
            }
            for row in payload.get("top5") or []
        ],
    }


def append_change_md_row(event: dict[str, Any]) -> None:
    WIKI_STATS.mkdir(parents=True, exist_ok=True)
    if not CHANGE_MD.exists():
        CHANGE_MD.write_text(
            "\n".join(
                [
                    "# 动态作战室Top5 变化流水",
                    "",
                    "用途：永久记录Top5调入、调出和排名变化，避免当前页被刷新后丢失当时变化原因。",
                    "",
                    "| 时间 | 版本 | 变化 | 当前Top5 |",
                    "|---|---|---|---|",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    existing = CHANGE_MD.read_text(encoding="utf-8", errors="ignore")
    if f"| {event.get('generatedAt')} | {event.get('signature')} |" in existing:
        return
    change = event.get("change") or {}
    change_texts = []
    for item in change.get("addedDetail") or []:
        change_texts.append(f"调入 {item.get('name') or item.get('code')} {item.get('code')}：{item.get('reason')}")
    for item in change.get("removedDetail") or []:
        change_texts.append(f"调出 {item.get('name') or item.get('code')} {item.get('code')}：{item.get('reason')}")
    for item in change.get("rankChanges") or []:
        change_texts.append(f"排名 {item.get('code')}：{item.get('reason')}")
    top_text = "、".join(f"{row.get('rank')}.{row.get('name') or row.get('code')}({row.get('code')})" for row in event.get("top5") or [])
    with CHANGE_MD.open("a", encoding="utf-8") as handle:
        handle.write(f"| {event['generatedAt']} | {event['signature']} | {clean('；'.join(change_texts), 500)} | {top_text} |\n")


def backfill_change_log_from_versions() -> None:
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    last_rows: dict[str, dict[str, Any]] = {}
    for row in iter_jsonl(FACTS):
        for item in row.get("top5") or []:
            if item.get("code"):
                last_rows[str(item.get("code"))] = item
        change = row.get("change") or {}
        if not any(change.get(key) for key in ("addedDetail", "removedDetail", "rankChanges")):
            continue
        event = change_event(row)
        for item in (event.get("change") or {}).get("removedDetail") or []:
            code = str(item.get("code") or "")
            old_row = last_rows.get(code) or {}
            if old_row:
                item["name"] = item.get("name") or old_row.get("name") or ""
                item["oldScore"] = item.get("oldScore") if item.get("oldScore") is not None else old_row.get("score")
                item["reason"] = item.get("reason") or f"跌出当前Top5；上一版排名{old_row.get('rank')}，旧分{old_row.get('score')}。"
        event_id = event.get("eventId")
        if event_id and event_id not in seen:
            seen.add(event_id)
            events.append(event)
    if not events:
        return
    CHANGE_FACTS.parent.mkdir(parents=True, exist_ok=True)
    CHANGE_FACTS.write_text("".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events), encoding="utf-8")
    if CHANGE_MD.exists():
        CHANGE_MD.unlink()
    for event in events:
        append_change_md_row(event)


def notify_if_changed(payload: dict[str, Any], force: bool) -> dict[str, Any]:
    old = read_json(STATE, {})
    changed = payload.get("change") or change_details(payload, old)
    if not force and old.get("signature") == payload["signature"]:
        return {"created": False, "reason": "same_signature"}
    should_notify, reason = should_notify_change(changed, force)
    if not should_notify:
        write_json(
            STATE,
            {
                "signature": payload["signature"],
                "top5": [row["code"] for row in payload["top5"]],
                "top5Rows": payload["top5"],
                "updatedAt": payload["generatedAt"],
                "lastSilentReason": reason,
            },
        )
        return {"created": False, "reason": reason, "rankChanges": changed.get("rankChanges") or []}
    PENDING.mkdir(parents=True, exist_ok=True)
    path = PENDING / f"{datetime.now().strftime('%Y%m%d%H%M%S')}-动态作战室Top5变更待校准.md"
    path.write_text(render_notify(payload, changed), encoding="utf-8")
    write_json(
        STATE,
        {
            "signature": payload["signature"],
            "top5": [row["code"] for row in payload["top5"]],
            "top5Rows": payload["top5"],
            "updatedAt": payload["generatedAt"],
        },
    )
    return {"created": True, "file": rel(path), "added": changed.get("added") or [], "removed": changed.get("removed") or [], "rankChanges": changed.get("rankChanges") or []}


def send_pending() -> None:
    sender = ROOT / ".system/scripts/send-feishu-pending-notifications.py"
    if sender.exists():
        subprocess.run(["/usr/bin/python3", str(sender)], cwd=str(ROOT), capture_output=True, text=True, timeout=60)


def main() -> int:
    parser = argparse.ArgumentParser(description="动态作战室Top5与持仓处理")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--apply-wiki", action="store_true")
    parser.add_argument("--notify", action="store_true")
    parser.add_argument("--force-notify", action="store_true")
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    payload["change"] = change_details(payload, read_json(STATE, {}))
    notify = {"created": False, "reason": "not_requested"}
    if args.write:
        write_outputs(payload, args.apply_wiki)
        if args.notify:
            notify = notify_if_changed(payload, args.force_notify)
            if args.send and notify.get("created"):
                send_pending()
    print(json.dumps({"ok": True, "date": args.date, "session": payload["session"], "top5": [f"{x['name'] or x['code']}{x['code']}" for x in payload["top5"]], "holdings": [f"{x.get('name') or x['code']}{x['code']}" for x in payload["holdingsAnalysis"]], "notify": notify}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
