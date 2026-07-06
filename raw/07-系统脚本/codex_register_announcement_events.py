#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把每日公告 RAW 注册为可验证的公告事件样本。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from codex_trading_calendar import add_trade_days as calendar_add_trade_days
from codex_trading_calendar import next_trade_day


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
WIKI = ROOT / "wiki"
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|43\d{4}|83\d{4}|87\d{4}|92\d{4})(?!\d)")

POSITIVE_WORDS = ["业绩预增", "业绩快报", "扭亏", "中标", "重大合同", "回购", "增持", "并购", "重组", "资产注入", "定增", "订单"]
RISK_WORDS = ["减持", "立案", "问询", "关注函", "监管函", "异动公告", "澄清", "亏损", "业绩修正", "终止", "风险提示"]
HOT_THEMES = ["AI", "数据中心", "存储", "芯片", "半导体", "机器人", "新能源", "算力", "光模块", "液冷", "军工", "稀土"]
MANUAL_NAME_CODE = {
    "大连重工": "002204",
    "中电港": "001287",
    "天顺风能": "002531",
    "惟科科技": "301196",
    "唯科科技": "301196",
}
MANUAL_NAME_FIX = {
    "上海数据港股份有限公司股东减持股份计划公告": "数据港",
    "惟科科技": "唯科科技",
}


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


def sanitize_filename(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|#\n\r\t]", "-", value)
    value = re.sub(r"\s+", "", value)
    return value[:80] or "unknown"


def parse_date(value: str) -> date:
    m = re.search(r"\d{4}-\d{2}-\d{2}", value or "")
    if not m:
        return datetime.now().date()
    return datetime.strptime(m.group(0), "%Y-%m-%d").date()


def parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    m = re.search(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?", value)
    if not m:
        return None
    text = m.group(0).replace("T", " ")
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            pass
    return None


def first_validation_day(value: str, fallback: str) -> date:
    dt = parse_datetime(value) or parse_datetime(fallback) or datetime.now()
    if dt.hour >= 15:
        return next_trade_day(dt.date())
    return next_trade_day(dt.date(), include_self=True)


def next_weekday(day: date) -> date:
    return next_trade_day(day, include_self=True)


def add_trade_days(day: date, count: int) -> date:
    return calendar_add_trade_days(day, count)


def event_id(date_text: str, code: str, name: str, title: str) -> str:
    source = f"{date_text}|{code}|{name}|{title}"
    return hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]


def iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_dicts(value)


def build_name_code_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    roots = [
        RAW / "04-市场数据",
        WIKI / "03-L3个股档案",
    ]
    for base in roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix.lower() not in {".json", ".md"}:
                continue
            if ".stversions" in path.parts or ".conflicts" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if path.suffix.lower() == ".json":
                obj = read_json(path, None)
                if obj is not None:
                    for item in iter_dicts(obj):
                        code = clean(item.get("f12") or item.get("股票代码") or item.get("代码") or item.get("code"))
                        name = clean(item.get("f14") or item.get("股票名称") or item.get("名称") or item.get("公司名称") or item.get("name"))
                        if CODE_RE.fullmatch(code) and name and not code.startswith(("BK", "399", "000001")):
                            mapping.setdefault(name, code)
                    continue
            for code, name in re.findall(r"(?<!\d)((?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}))[-_ ]?([\u4e00-\u9fffA-Za-z0-9]{2,16})", text):
                mapping.setdefault(name, code)
    return mapping


def normalize_announcement(row: dict[str, Any], name_code: dict[str, str]) -> dict[str, Any]:
    title = clean(row.get("公告标题") or row.get("title") or row.get("标题"))
    name = clean(row.get("公司名称") or row.get("name") or row.get("股票名称") or row.get("证券简称"))
    name = MANUAL_NAME_FIX.get(name, name)
    code = clean(row.get("股票代码") or row.get("code") or row.get("证券代码"))
    raw_text = json.dumps(row, ensure_ascii=False)
    if not CODE_RE.fullmatch(code):
        found = CODE_RE.search(raw_text)
        code = found.group(0) if found else ""
    if name in MANUAL_NAME_CODE:
        code = MANUAL_NAME_CODE[name]
    if not code and name in name_code:
        code = name_code[name]
    ann_date = clean(row.get("公告日期") or row.get("date") or row.get("日期") or row.get("time"))
    category = row.get("分类标签") or row.get("category") or row.get("分类") or ""
    keyword = row.get("命中关键词") or row.get("查询关键词") or row.get("keyword") or ""
    if isinstance(category, list):
        categories = [clean(x) for x in category if clean(x)]
    else:
        categories = [clean(category)] if clean(category) else []
    if isinstance(keyword, list):
        keywords = [clean(x) for x in keyword if clean(x)]
    else:
        keywords = [clean(keyword)] if clean(keyword) else []
    return {
        "公告标题": title,
        "公司名称": name,
        "股票代码": code or "待补",
        "公告日期": ann_date,
        "分类标签": categories,
        "命中关键词": keywords,
        "公告摘要": clean(row.get("公告摘要") or row.get("brief") or row.get("摘要") or row.get("content")),
        "公告链接": clean(row.get("公告链接") or row.get("url") or row.get("link")),
        "原始字段": row,
        "代码待补": "是" if not code else "否",
    }


def iter_announcements(payload: Any):
    if isinstance(payload, dict):
        rows = payload.get("items") or payload.get("公告") or payload.get("records") or payload.get("data")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    yield row
            return
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict):
                yield row


def classify_event(row: dict[str, Any]) -> dict[str, Any]:
    title_summary = f"{row['公告标题']} {row['公告摘要']}"
    text = f"{title_summary} {' '.join(row['分类标签'])}"
    risk_hits = [w for w in RISK_WORDS if w in title_summary]
    positive_hits = [w for w in POSITIVE_WORDS if w in text]
    theme_hits = [w for w in HOT_THEMES if w in text]
    if risk_hits:
        expected = "负向或压制，需验证是否低开低走或一日反抽"
    elif "业绩" in "".join(row["分类标签"]) and any(w in text for w in ["同比增", "预增", "扭亏", "增长"]):
        expected = "正向，需验证是否能被市场按行业景气定价"
    elif any(w in text for w in ["并购", "重组", "资产注入", "中标", "重大合同", "增持", "回购"]):
        expected = "正向或事件驱动，需验证是否有持续资金承接"
    else:
        expected = "中性待验证"
    if risk_hits:
        event_type = "风险公告"
    elif "业绩" in "".join(row["分类标签"]):
        event_type = "业绩公告"
    elif any(w in text for w in ["并购", "重组", "资产注入"]):
        event_type = "并购重组"
    elif any(w in text for w in ["中标", "合同", "订单"]):
        event_type = "合同订单"
    elif any(w in text for w in ["增持", "回购"]):
        event_type = "增持回购"
    else:
        event_type = "普通公告"
    return {
        "公告类型": event_type,
        "正向关键词": positive_hits,
        "风险关键词": risk_hits,
        "题材关键词": theme_hits,
        "初始假设": expected,
    }


def make_events(date_text: str, announcements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in announcements:
        ann_day = parse_date(row["公告日期"] or date_text)
        first_trade = first_validation_day(row["公告日期"], date_text)
        eid = event_id(row["公告日期"] or date_text, row["股票代码"], row["公司名称"], row["公告标题"])
        classified = classify_event(row)
        events.append({
            "事件ID": eid,
            "公告日": ann_day.isoformat(),
            "首个可交易验证日": first_trade.isoformat(),
            "D+1": add_trade_days(first_trade, 1).isoformat(),
            "D+3": add_trade_days(first_trade, 3).isoformat(),
            "D+5": add_trade_days(first_trade, 5).isoformat(),
            "D+10": add_trade_days(first_trade, 10).isoformat(),
            **row,
            **classified,
            "后续验证字段": {
                "D+0竞价": "",
                "D+0收盘": "",
                "D+1表现": "",
                "D+3表现": "",
                "D+5表现": "",
                "D+10表现": "",
                "是否持续": "",
                "是否一日游": "",
                "规律提取": "",
            },
        })
    return events


def render_events_md(date_text: str, events: list[dict[str, Any]]) -> str:
    lines = [
        f"# {date_text} 公告事件样本",
        "",
        "用途：把公告变成可验证样本，用于训练“哪些公告能持续大涨，哪些是一日游”。",
        "",
        f"- 样本数：{len(events)}",
        "",
        "| 事件ID | 代码 | 名称 | 类型 | 公告日 | 首个验证日 | 初始假设 | 标题 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for e in events:
        lines.append(
            f"| {e['事件ID']} | {e['股票代码']} | {e['公司名称']} | {e['公告类型']} | {e['公告日']} | {e['首个可交易验证日']} | {e['初始假设']} | {e['公告标题']} |"
        )
    lines += [
        "",
        "## 验证口径",
        "",
        "- D+0：看竞价、开盘方向、是否高开低走、是否涨停或冲高回落。",
        "- D+1/D+3/D+5/D+10：看相对大盘、相对板块、成交额、资金承接、是否进入热榜或涨停。",
        "- 最终只沉淀被市场验证过的规律；公告本身不等于买点。",
    ]
    return "\n".join(lines) + "\n"


def find_existing_stock_cards(code: str, name: str) -> list[Path]:
    if code == "待补" and not name:
        return []
    patterns = []
    if code != "待补":
        patterns += [f"*{code}*{name}*.md", f"*{name}*{code}*.md"]
    if name:
        patterns.append(f"*{name}*.md")
    found: list[Path] = []
    base = WIKI / "03-L3个股档案"
    for pattern in patterns:
        for path in base.rglob(pattern):
            if path.is_file() and "公告事件档案" not in path.parts and path not in found:
                found.append(path)
    return found[:3]


def append_once(path: Path, marker: str, block: str, header: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="ignore")
    else:
        text = ""
    if marker in text:
        return
    if header and header not in text:
        text = text.rstrip() + "\n\n" + header + "\n"
    text = text.rstrip() + "\n\n" + block.rstrip() + "\n"
    path.write_text(text, encoding="utf-8")


def render_stock_event_block(e: dict[str, Any]) -> str:
    return f"""### {e['公告日']} {e['公告类型']}：{e['公告标题']}

<!-- announcement-event:{e['事件ID']} -->

- 事件ID：{e['事件ID']}
- 股票：{e['股票代码']} {e['公司名称']}
- 公告日期：{e['公告日']}
- 首个可交易验证日：{e['首个可交易验证日']}
- D+1/D+3/D+5/D+10：{e['D+1']} / {e['D+3']} / {e['D+5']} / {e['D+10']}
- 初始假设：{e['初始假设']}
- 正向关键词：{'、'.join(e['正向关键词']) or '无'}
- 风险关键词：{'、'.join(e['风险关键词']) or '无'}
- 题材关键词：{'、'.join(e['题材关键词']) or '无'}
- 公告摘要：{e['公告摘要'] or '无'}
- 公告链接：{e['公告链接'] or '无'}
- 后续表现：待 D+验证回填
"""


def update_stock_files(events: list[dict[str, Any]]) -> list[str]:
    touched: list[str] = []
    dossier_dir = WIKI / "03-L3个股档案" / "公告事件档案"
    dossier_dir.mkdir(parents=True, exist_ok=True)
    for e in events:
        code = e["股票代码"]
        name = e["公司名称"] or "未知公司"
        filename = f"{code}-{sanitize_filename(name)}-公告事件档案.md" if code != "待补" else f"待补代码-{sanitize_filename(name)}-公告事件档案.md"
        dossier = dossier_dir / filename
        if not dossier.exists():
            title_code = code if code != "待补" else "代码待补"
            dossier.write_text(
                f"# {name}（{title_code}）公告事件档案\n\n"
                "用途：记录该股公告事件、初始假设、后续股价验证和规律提取。\n",
                encoding="utf-8",
            )
        block = render_stock_event_block(e)
        append_once(dossier, f"announcement-event:{e['事件ID']}", block, "## 公告事件记录")
        touched.append(str(dossier.relative_to(ROOT)))
        for card in find_existing_stock_cards(code, name):
            short = (
                f"- {e['公告日']} | {e['公告类型']} | {e['公告标题']} | "
                f"首个验证日 {e['首个可交易验证日']} | 事件ID {e['事件ID']} | "
                f"详见 [[{dossier.stem}]]\n"
                f"  <!-- announcement-event:{e['事件ID']} -->"
            )
            append_once(card, f"announcement-event:{e['事件ID']}", short, "## 公告事件跟踪")
            touched.append(str(card.relative_to(ROOT)))
    return sorted(set(touched))


def update_validation_queue(events: list[dict[str, Any]]) -> Path:
    path = WIKI / "09-统计与进化" / "公告事件D+验证队列.md"
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="ignore")
    else:
        text = (
            "# 公告事件D+验证队列\n\n"
            "用途：所有重要公告必须进入 D+验证，验证公告是否能带来持续行情，还是只是一日游。\n\n"
            "| 入队日 | 事件ID | 代码 | 名称 | 公告类型 | 首个验证日 | D+1 | D+3 | D+5 | D+10 | 初始假设 | 状态 |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        )
    lines = []
    today = datetime.now().strftime("%Y-%m-%d")
    for e in events:
        marker = f"| {today} | {e['事件ID']} |"
        if marker in text or f"| {e['事件ID']} |" in text:
            continue
        lines.append(
            f"| {today} | {e['事件ID']} | {e['股票代码']} | {e['公司名称']} | {e['公告类型']} | "
            f"{e['首个可交易验证日']} | {e['D+1']} | {e['D+3']} | {e['D+5']} | {e['D+10']} | {e['初始假设']} | active |"
        )
    if lines:
        text = text.rstrip() + "\n" + "\n".join(lines) + "\n"
        path.write_text(text, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="公告事件入库与D+验证队列注册")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    source = RAW / "05-研报新闻" / "公告" / args.date / "daily-announcements.json"
    payload = read_json(source, {})
    name_code = build_name_code_map()
    announcements = [normalize_announcement(row, name_code) for row in iter_announcements(payload)]
    events = make_events(args.date, announcements)
    out = {
        "日期": args.date,
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "数据源": str(source.relative_to(ROOT)),
        "公告数": len(announcements),
        "事件数": len(events),
        "代码待补数": sum(1 for e in events if e["代码待补"] == "是"),
        "事件样本": events,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.write:
        out_dir = RAW / "11-Codex分析产物" / "公告事件样本" / args.date
        write_json(out_dir / "公告事件样本.json", out)
        (out_dir / "公告事件样本.md").write_text(render_events_md(args.date, events), encoding="utf-8")
        touched = update_stock_files(events)
        queue = update_validation_queue(events)
        report = {
            "日期": args.date,
            "事件数": len(events),
            "代码待补数": out["代码待补数"],
            "更新文件数": len(touched) + 1,
            "验证队列": str(queue.relative_to(ROOT)),
            "更新文件": touched,
        }
        write_json(RAW / "11-Codex分析产物" / "公告催化" / args.date / "公告事件入库报告.json", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
