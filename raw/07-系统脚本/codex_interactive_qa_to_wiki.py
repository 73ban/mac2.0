#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path("/Users/qixinchaye/wiki/73神话")
TZ = dt.timezone(dt.timedelta(hours=8))
RAW_QA = ROOT / "raw/05-研报新闻/互动问答"
L3_ROOT = ROOT / "wiki/03-L3个股档案"
L2_ROOT = ROOT / "wiki/02-L2方向题材"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
WIKI_ROOM = ROOT / "wiki/07-作战室"
SYSTEM = ROOT / ".system"

THEME_ALIASES = {
    "半导体": ["半导体", "芯片", "国产替代", "封测", "晶圆", "光刻", "电子特气", "湿化学品"],
    "先进封装": ["先进封装", "Chiplet", "3D堆叠", "封装", "FOPLP", "玻璃基板"],
    "PCB概念": ["PCB", "PCBA", "覆铜板", "电子布", "载板"],
    "机器人概念": ["机器人", "减速器", "伺服", "步进", "运动控制", "关节"],
    "AI算力": ["AI", "算力", "英伟达", "NVIDIA", "DGX", "服务器", "数据中心"],
    "存储芯片": ["存储", "SSD", "NAND", "DRAM", "HBM"],
    "光模块": ["光模块", "CPO", "1.6T", "光通信"],
    "固态电池": ["固态电池", "六氟磷酸锂", "电解液", "VC碳酸亚乙烯酯"],
    "贵金属": ["黄金", "钼", "贵金属", "金矿"],
    "并购重组": ["并购", "重组", "收购", "定增", "资产注入"],
    "商业航天": ["卫星", "商业航天", "SpaceX", "星链"],
}

THEME_PAGE_PREFERRED = {
    "半导体": ["半导体-反复炒作主题池-2026-06-12.md"],
    "先进封装": ["先进封装.md"],
    "PCB概念": ["PCB概念.md"],
    "机器人概念": ["机器人概念.md"],
    "AI算力": ["AI算力链.md", "AI算力概念板块.md"],
    "存储芯片": ["存储芯片.md"],
    "光模块": ["光模块赛道.md", "lpo与光模块技术路线.md"],
    "固态电池": ["固态电池.md"],
    "贵金属": ["贵金属.md"],
    "并购重组": ["并购重组.md"],
    "商业航天": ["商业航天.md"],
}

FACT_WORDS = ["已", "目前", "已经", "正在", "将", "预计", "计划", "具备", "完成", "通过", "合作", "供货", "订单", "量产"]
RISK_WORDS = ["澄清", "不属实", "未", "尚未", "不涉及", "风险", "终止", "问询", "监管", "减持", "亏损"]
MATERIAL_WORDS = [
    "量产", "供货", "订单", "中标", "客户", "产能", "涨价", "断供", "出口", "海外",
    "认证", "通过验证", "并购", "重组", "收购", "定增", "扩产", "送样", "良率",
    "半导体", "先进封装", "Chiplet", "FOPLP", "PCB", "CPO", "光模块", "机器人",
    "算力", "AI", "存储", "固态电池", "电子特气", "湿化学品",
]
ROUTINE_WORDS = [
    "股东人数", "股东户数", "截止", "截至", "董秘您好请问贵公司目前的股东人数",
    "祝您生活愉快", "股价", "市值管理", "什么时候涨", "为什么跌", "分红", "派息",
]
ROUTINE_ONLY_WORDS = ["股东人数", "股东户数", "分红", "派息", "市值管理", "什么时候涨", "为什么跌"]
IGNORE_DIRS = {"RAW增量个股卡", "作战室个股雷达卡", "公告事件档案", "总结", "持股态度卡"}


def now() -> dt.datetime:
    return dt.datetime.now(TZ)


def today() -> str:
    return now().date().isoformat()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def clean(value: Any, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("|", "/")).strip()
    return text[:limit] if limit else text


def strip_routine_phrases(text: str) -> str:
    text = clean(text)
    patterns = [
        r"您好[，,]?\s*请问贵公司目前的股东人数是多少[？?]?",
        r"请问贵公司目前的股东人数是多少[？?]?",
        r"请问公司目前的股东人数是多少[？?]?",
        r"请问.*?股东人数.*?[？?]",
        r"截至.*?股东.*?[？?]",
        r"截止.*?股东.*?[？?]",
        r"祝您生活愉快",
        r"谢谢[！!。]?$",
        r"感谢[！!。]?$",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    return clean(text)


def important_question(row: dict[str, Any], limit: int | None = None) -> str:
    text = strip_routine_phrases(str(row.get("投资者问题") or ""))
    return text[:limit] if limit else text


def sha(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:12]


def next_trade_date(date: str) -> str:
    day = dt.datetime.strptime(date, "%Y-%m-%d").date() + dt.timedelta(days=1)
    while day.weekday() >= 5:
        day += dt.timedelta(days=1)
    return day.isoformat()


def parse_meta(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    meta: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def existing_stock_profile(code: str, name: str) -> Path | None:
    if not L3_ROOT.exists():
        return None
    candidates: list[Path] = []
    for path in L3_ROOT.rglob("*.md"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.name.startswith(".") or "资料映射" in path.name:
            continue
        text = read_text(path)
        meta = parse_meta(text)
        stem = path.stem
        aliases = {stem, meta.get("code", ""), meta.get("name", "")}
        if code:
            aliases.add(code)
        if name:
            aliases.add(name)
        if code and (code in stem or meta.get("code") == code):
            candidates.append(path)
        elif name and (name in stem or meta.get("name") == name):
            candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda p: (0 if re.search(r"\d{6}", p.stem) else 1, len(p.stem)))
    return candidates[0]


def fallback_stock_card(code: str, name: str) -> Path:
    safe_name = name or code
    return L3_ROOT / "RAW增量个股卡" / f"{code}-{safe_name}-互动易增量骨架.md"


def find_theme_page(theme: str) -> Path | None:
    for name in THEME_PAGE_PREFERRED.get(theme, []):
        path = L2_ROOT / name
        if path.exists():
            return path
    exact = L2_ROOT / f"{theme}.md"
    if exact.exists():
        return exact
    candidates = []
    for path in L2_ROOT.glob("*.md"):
        if "RAW" in path.name:
            continue
        if theme in path.stem:
            candidates.append(path)
    if not candidates:
        return None
    candidates.sort(key=lambda p: (len(p.stem), p.name))
    return candidates[0]


def classify_row(row: dict[str, Any]) -> str:
    answer = clean(row.get("公司回复原文"))
    question = clean(row.get("投资者问题"))
    if answer:
        if any(word in answer for word in RISK_WORDS):
            return "公司澄清/风险"
        if any(word in answer for word in FACT_WORDS):
            return "公司回复确认"
        return "公司回复待解读"
    if any(word in question for word in RISK_WORDS):
        return "市场传闻/风险关注"
    return "投资者关注点"


def material_terms(row: dict[str, Any]) -> list[str]:
    text = clean(row.get("投资者问题")) + " " + clean(row.get("公司回复原文")) + " " + " ".join(row.get("命中关键词") or [])
    return [word for word in MATERIAL_WORDS if word.lower() in text.lower()]


def norm_code(value: Any) -> str:
    m = re.search(r"(\d{6})", str(value or ""))
    return m.group(1) if m else ""


def date_window(date: str) -> set[str]:
    base = dt.datetime.strptime(date, "%Y-%m-%d").date()
    return {(base + dt.timedelta(days=i)).isoformat() for i in range(-2, 3)}


def add_market_hit(ctx: dict[str, list[dict[str, Any]]], code: str, name: str, source: str, reason: str, rank: Any = "") -> None:
    code6 = norm_code(code)
    name = clean(name)
    reason = clean(reason, 260)
    if not code6 and not name:
        return
    if not reason:
        return
    item = {"来源": source, "排名": rank, "叙事": reason}
    keys = {code6, name}
    for key in keys:
        if key:
            ctx.setdefault(key, []).append(item)


def collect_market_context(date: str) -> dict[str, list[dict[str, Any]]]:
    dates = date_window(date)
    ctx: dict[str, list[dict[str, Any]]] = {}

    for d in dates:
        merged = ROOT / f"raw/04-市场数据/三榜热度合并/{d}/三榜热度合并.json"
        payload = read_json(merged)
        for row in payload.get("股票") or []:
            concepts = "、".join(str(x) for x in row.get("概念标签") or [])
            reason = clean(row.get("淘股吧关注理由")) or concepts
            extra = []
            if row.get("连板标记"):
                extra.append(str(row.get("连板标记")))
            if row.get("来源榜单"):
                extra.append("、".join(str(x) for x in row.get("来源榜单") or []))
            if reason or extra:
                add_market_hit(
                    ctx,
                    str(row.get("代码") or ""),
                    str(row.get("名称") or ""),
                    f"三榜热度合并/{d}",
                    "；".join([x for x in [reason, concepts, "；".join(extra)] if x]),
                    row.get("综合排名", ""),
                )

        tgb = ROOT / f"raw/04-市场数据/热榜/{d}/淘股吧热榜100-latest.json"
        payload = read_json(tgb)
        for row in payload.get("股票热榜") or []:
            reason = clean(row.get("关注理由")) or clean(row.get("连板标记"))
            add_market_hit(ctx, row.get("代码", ""), row.get("名称", ""), f"淘股吧热榜/{d}", reason, row.get("排名", ""))
        for row in payload.get("淘股吧6维补充") or []:
            reason = clean(row.get("关注理由") or row.get("reason") or row.get("概念") or row.get("concept"))
            add_market_hit(ctx, row.get("代码") or row.get("code"), row.get("名称") or row.get("name"), f"淘股吧6维/{d}", reason, row.get("排名") or row.get("rank") or "")
        for row in payload.get("实盘赛热门买入") or []:
            reason = f"实盘赛热门买入，买入人数={row.get('买入人数','')}"
            add_market_hit(ctx, row.get("代码", ""), row.get("名称", ""), f"淘股吧实盘赛买入/{d}", reason, row.get("排名", ""))

        for path in [
            ROOT / f"raw/04-市场数据/每日涨停全景/{d}/tdx-daily-limit.json",
            ROOT / f"raw/04-市场数据/每日涨停全景/{d}/通达信涨停全景.json",
            ROOT / f"raw/04-市场数据/通达信涨停原因/{d}/通达信涨停原因6维.json",
        ]:
            payload = read_json(path)
            rows = payload.get("记录") or payload.get("rows") or payload.get("数据") or []
            if not isinstance(rows, list):
                continue
            for row in rows:
                reason = clean(row.get("涨停原因") or row.get("原因揭秘") or row.get("reason") or row.get("上榜原因"))
                add_market_hit(ctx, row.get("代码") or row.get("code"), row.get("名称") or row.get("name"), f"涨停原因/{d}", reason, row.get("排名") or "")

    return ctx


def market_hits_for_row(row: dict[str, Any], ctx: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    code = norm_code(row.get("股票代码"))
    name = clean(row.get("股票名称"))
    hits = []
    seen = set()
    for key in (code, name):
        for hit in ctx.get(key, []):
            fp = (hit.get("来源"), hit.get("叙事"))
            if fp not in seen:
                seen.add(fp)
                hits.append(hit)
    return hits[:8]


def narrative_terms(hits: list[dict[str, Any]]) -> list[str]:
    text = " ".join(clean(hit.get("叙事")) for hit in hits)
    out = []
    for theme, words in THEME_ALIASES.items():
        if any(word.lower() in text.lower() for word in words):
            out.append(theme)
    for word in MATERIAL_WORDS:
        if word.lower() in text.lower() and word not in out:
            out.append(word)
    return out[:12]


def interactive_confirms_or_denies_market(row: dict[str, Any], hits: list[dict[str, Any]]) -> bool:
    if not hits:
        return False
    answer = clean(row.get("公司回复原文"))
    if not answer:
        return False
    answer_has_fact = any(word in answer for word in FACT_WORDS + MATERIAL_WORDS)
    answer_has_risk = any(word in answer for word in RISK_WORDS)
    return answer_has_fact or answer_has_risk


def is_routine_only(row: dict[str, Any]) -> bool:
    text = clean(row.get("投资者问题")) + " " + clean(row.get("公司回复原文"))
    has_routine = any(word in text for word in ROUTINE_ONLY_WORDS)
    if not has_routine:
        return False
    has_material = bool(material_terms(row))
    has_risk = any(word in text for word in RISK_WORDS)
    return not has_material and not has_risk


def is_material_row(row: dict[str, Any]) -> bool:
    if is_routine_only(row):
        return False
    themes = themes_for_row(row)
    terms = material_terms(row)
    answer = clean(row.get("公司回复原文"))
    text = clean(row.get("投资者问题")) + " " + answer
    has_risk = any(word in text for word in RISK_WORDS)
    if has_risk and themes:
        return True
    if answer and (terms or themes):
        return True
    if themes and terms:
        return True
    return False


def themes_for_row(row: dict[str, Any]) -> list[str]:
    text = clean(row.get("投资者问题")) + " " + clean(row.get("公司回复原文")) + " " + " ".join(row.get("命中关键词") or [])
    out = []
    for theme, words in THEME_ALIASES.items():
        if any(word.lower() in text.lower() for word in words):
            out.append(theme)
    return out[:6]


def source_path(date: str) -> str:
    return f"raw/05-研报新闻/互动问答/{date}/interactive-qa.json"


def row_marker(date: str, row: dict[str, Any]) -> str:
    base = "|".join([
        date,
        clean(row.get("平台")),
        clean(row.get("股票代码")),
        clean(row.get("问题时间")),
        clean(row.get("投资者问题")),
        clean(row.get("公司回复原文")),
    ])
    return f"interactive-qa:{sha(base)}"


def row_block(date: str, row: dict[str, Any]) -> str:
    marker = row_marker(date, row)
    status = classify_row(row)
    question = important_question(row, 280)
    answer = clean(row.get("公司回复原文"), 320) or "未抓到公司回复；仅代表投资者/市场关注点，不等于公司确认。"
    keywords = "、".join((row.get("命中关键词") or []) + (row.get("风险关键词") or [])) or "无"
    themes = "、".join(themes_for_row(row)) or "未归类"
    material = "、".join(material_terms(row)) or "无"
    market_hits = row.get("_market_hits") or []
    market_text = "；".join(f"{hit.get('来源')}：{hit.get('叙事')}" for hit in market_hits[:4]) or "未命中市场叙事"
    score = row.get("重要度评分", "")
    return "\n".join([
        f"## {date} 互动易/上证e互动增量",
        "",
        f"- 状态：{status}",
        f"- 平台：{clean(row.get('平台'))}",
        f"- 问题时间：{clean(row.get('问题时间'))}",
        f"- 重要度评分：{score}",
        f"- 关键词：{keywords}",
        f"- 交易相关点：{material}",
        f"- 题材归属：{themes}",
        f"- 市场叙事来源：{market_text}",
        f"- 来源文件：`{source_path(date)}`",
        f"- 原始链接：{clean(row.get('原始链接'))}",
        f"- 去重标记：{marker}",
        "",
        "### 投资者问题",
        "",
        question,
        "",
        "### 公司回复/确认状态",
        "",
        answer,
        "",
        "### 交易含义",
        "",
        "- 若无公司回复，只作为市场关注点和题材预期观察，不作为事实确认。",
        "- 若公司回复确认订单、客户、量产、产能、收购等，再进入催化验证。",
        "- 若公司回复澄清、不属实、尚未合作，写入风险/打脸样本。",
        "- 只有与热榜、涨停原因、淘股吧叙事发生交叉，并被公司回复确认/辟谣的信息，才写入正式个股卡。",
        "- 例行问答如股东人数、分红、股价诉求不进入个股卡；混合问题只保留其中的题材/产业链关注点。",
    ])


def append_once(path: Path, marker: str, block: str) -> bool:
    text = read_text(path)
    if marker in text:
        return False
    if not text:
        text = "\n".join([
            "---",
            f"type: {'RAW增量个股卡' if 'RAW增量个股卡' in str(path) else '个股档案'}",
            f"created: {today()}",
            "source: interactive_qa",
            "---",
            "",
            f"# {path.stem}",
            "",
        ])
    if not text.endswith("\n"):
        text += "\n"
    write_text(path, text + "\n" + block.strip() + "\n")
    return True


def build(date: str, min_score: int, limit: int) -> dict[str, Any]:
    payload = read_json(RAW_QA / date / "interactive-qa.json")
    market_ctx = collect_market_context(date)
    rows = payload.get("高优先线索") or []
    if not isinstance(rows, list):
        rows = []
    skipped: list[dict[str, Any]] = []
    filtered_rows: list[dict[str, Any]] = []
    for row in rows:
        if int(row.get("重要度评分") or 0) < min_score:
            continue
        hits = market_hits_for_row(row, market_ctx)
        row["_market_hits"] = hits
        if is_material_row(row) and hits:
            filtered_rows.append(row)
        else:
            skipped.append({
                "代码": clean(row.get("股票代码")),
                "名称": clean(row.get("股票名称")),
                "原因": "未命中热榜/涨停原因/淘股吧市场叙事，或无交易相关题材",
                "问题": important_question(row, 120),
            })
    rows = filtered_rows
    rows = rows[:limit]
    stock_updates: list[dict[str, Any]] = []
    theme_hits: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        code = clean(row.get("股票代码"))
        name = clean(row.get("股票名称"))
        profile = existing_stock_profile(code, name)
        target = profile or fallback_stock_card(code, name)
        status = classify_row(row)
        hits = row.get("_market_hits") or []
        confirmed = interactive_confirms_or_denies_market(row, hits)
        write_level = "个股卡" if confirmed else "作战室复核"
        item = {
            "代码": code,
            "名称": name,
            "状态": status,
            "分数": int(row.get("重要度评分") or 0),
            "关键词": (row.get("命中关键词") or []) + (row.get("风险关键词") or []),
            "题材": themes_for_row(row),
            "市场叙事": "；".join(clean(hit.get("叙事"), 80) for hit in hits[:3]),
            "叙事来源": "、".join(clean(hit.get("来源")) for hit in hits[:3]),
            "叙事关键词": narrative_terms(hits),
            "写入级别": write_level,
            "目标文件": rel(target),
            "问题": important_question(row, 120),
            "回复": clean(row.get("公司回复原文"), 120),
            "marker": row_marker(date, row),
            "row": row,
        }
        stock_updates.append(item)
        for theme in item["题材"]:
            theme_hits.setdefault(theme, []).append(item)
    return {
        "schema": "73wiki-interactive-qa-to-wiki-v1",
        "日期": date,
        "生成时间": now().isoformat(timespec="seconds"),
        "输入": rel(RAW_QA / date / "interactive-qa.json"),
        "阈值": min_score,
        "个股更新": stock_updates,
        "题材关注点": theme_hits,
        "跳过线索": skipped,
        "规则": [
            "投资者问题代表市场关注点，不等于公司确认。",
            "互动易必须命中热榜、涨停原因、淘股吧、三榜合并中的当下市场叙事，才进入复核。",
            "公司回复为空时，只进入作战室复核，不写入正式个股卡。",
            "公司回复出现不属实、尚未、澄清等，写入风险/打脸样本。",
            "公司回复确认或辟谣当下市场叙事，才写入个股卡。",
            "互动易高频关键词用于更新题材关注点和作战室复核，不直接给买入权限。",
            "股东人数、分红、股价诉求等例行问答不写入个股卡；混合问题只保留题材/产业链相关部分。",
        ],
    }


def md_table(headers: list[str], rows: list[dict[str, Any]], keys: list[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    if not rows:
        return "\n".join(lines + ["| " + " | ".join(["无"] + [""] * (len(headers) - 1)) + " |"])
    for row in rows:
        lines.append("| " + " | ".join(clean(row.get(key), 160) for key in keys) + " |")
    return "\n".join(lines)


def write_report(data: dict[str, Any]) -> tuple[Path, Path]:
    date = data["日期"]
    WIKI_STATS.mkdir(parents=True, exist_ok=True)
    json_path = WIKI_STATS / f"{date}-互动易关注点入Wiki报告.json"
    md_path = WIKI_STATS / f"{date}-互动易关注点入Wiki报告.md"
    write_text(json_path, json.dumps({k: v for k, v in data.items() if k != "_rows"}, ensure_ascii=False, indent=2) + "\n")
    lines = [
        f"# {date} 互动易关注点入Wiki报告",
        "",
        f"- 生成时间：{data['生成时间']}",
        f"- 输入：`{data['输入']}`",
        f"- 阈值：{data['阈值']}",
        "",
        "## 规则",
        "",
    ]
    lines.extend(f"- {rule}" for rule in data["规则"])
    lines += ["", "## 个股更新", ""]
    lines.append(md_table(["代码", "名称", "写入级别", "状态", "分数", "题材", "市场叙事", "问题"], data["个股更新"], ["代码", "名称", "写入级别", "状态", "分数", "题材", "市场叙事", "问题"]))
    lines += ["", "## 题材关注点", ""]
    theme_rows = []
    for theme, items in data["题材关注点"].items():
        theme_rows.append({
            "题材": theme,
            "线索数": len(items),
            "代表个股": "、".join(f"{x['名称'] or x['代码']}" for x in items[:6]),
            "关键词": "、".join(sorted({kw for item in items for kw in item["关键词"]})[:12]),
        })
    lines.append(md_table(["题材", "线索数", "代表个股", "关键词"], theme_rows, ["题材", "线索数", "代表个股", "关键词"]))
    lines += ["", "## 跳过线索", ""]
    lines.append(md_table(["代码", "名称", "原因", "问题"], data["跳过线索"], ["代码", "名称", "原因", "问题"]))
    lines.append("")
    write_text(md_path, "\n".join(lines))
    return json_path, md_path


def write_warroom(data: dict[str, Any]) -> Path:
    date = data["日期"]
    out = WIKI_ROOM / f"{next_trade_date(date)}-互动易关注点复核.md"
    rows = data["个股更新"][:40]
    lines = [
        f"# {next_trade_date(date)} 互动易关注点复核",
        "",
        f"- 生成时间：{data['生成时间']}",
        f"- 来源报告：`wiki/09-统计与进化/{date}-互动易关注点入Wiki报告.md`",
        "",
        "## 高优先个股",
        "",
        md_table(["代码", "名称", "写入级别", "状态", "分数", "题材", "市场叙事", "问题"], rows, ["代码", "名称", "写入级别", "状态", "分数", "题材", "市场叙事", "问题"]),
        "",
        "## 使用规则",
        "",
        "- 互动易必须先和热榜、涨停原因、淘股吧叙事交叉，才有复核价值。",
        "- 公司回复确认量产、订单、客户、产能、收购，才可升为事实催化并写入个股卡。",
        "- 公司回复澄清或否认，优先写入风险/错误库候选。",
        "- 未回复的市场叙事问答只进复核，不写入正式个股卡。",
        "- 次日只用它辅助观察竞价、板块、题材热度和承接。",
        "",
    ]
    write_text(out, "\n".join(lines))
    return out


def apply_updates(data: dict[str, Any], max_apply: int) -> list[dict[str, str]]:
    applied: list[dict[str, str]] = []
    for item in data["个股更新"][:max_apply]:
        if item.get("写入级别") != "个股卡":
            continue
        target = ROOT / item["目标文件"]
        if append_once(target, item["marker"], row_block(data["日期"], item["row"])):
            applied.append({"类型": "个股", "对象": f"{item['代码']} {item['名称']}", "文件": item["目标文件"]})
    for theme, items in data["题材关注点"].items():
        page = find_theme_page(theme)
        if not page:
            continue
        marker = f"interactive-qa-theme:{data['日期']}:{sha(theme + ''.join(x['marker'] for x in items[:12]))}"
        examples = "\n".join(
            f"- {x['代码']} {x['名称']}：{x['状态']}；关键词={ '、'.join(x['关键词'][:8]) }；问题={x['问题']}"
            for x in items[:8]
        )
        block = "\n".join([
            f"## {data['日期']} 互动易关注点增量",
            "",
            f"- 来源文件：`{data['输入']}`",
            f"- 去重标记：{marker}",
            "- 定性：投资者/市场关注点聚合，不等于公司事实确认。",
            "",
            examples,
            "",
            "### 待验证",
            "",
            "- 是否进入热榜/话题榜/实盘赛热门买入。",
            "- 是否被公司回复确认，或被澄清否认。",
            "- 次日是否有板块承接和核心股正反馈。",
        ])
        if append_once(page, marker, block):
            applied.append({"类型": "题材", "对象": theme, "文件": rel(page)})
    return applied


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=today())
    parser.add_argument("--min-score", type=int, default=24)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--apply-wiki", action="store_true")
    parser.add_argument("--max-apply", type=int, default=40)
    args = parser.parse_args()
    data = build(args.date, args.min_score, args.limit)
    if args.write:
        _, report = write_report(data)
        room = write_warroom(data)
        applied = apply_updates(data, args.max_apply) if args.apply_wiki else []
        write_text(SYSTEM / "interactive-qa-to-wiki.json", json.dumps({
            "日期": data["日期"],
            "生成时间": data["生成时间"],
            "个股更新数": len(data["个股更新"]),
            "题材数": len(data["题材关注点"]),
            "自动写入": applied,
        }, ensure_ascii=False, indent=2) + "\n")
        print(str(report))
        print(str(room))
        if applied:
            print(json.dumps({"自动写入": applied}, ensure_ascii=False))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
