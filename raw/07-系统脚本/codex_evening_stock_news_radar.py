#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""22:30 持仓票/明日计划票线索雷达。

读取本机 RAW 信息池，筛出需要用户决策的个股新闻线索，并写入飞书待通知目录。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
SYSTEM = ROOT / ".system"
PENDING = SYSTEM / "feishu-notify-pending"
SENT = SYSTEM / "feishu-notify-sent"
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|43\d{4}|83\d{4}|87\d{4}|92\d{4})(?!\d)")

POSITIVE = ["中标", "订单", "供货", "量产", "涨价", "断供", "认证", "客户", "海外", "出口", "并购", "重组", "收购", "定增", "回购", "增持", "业绩预增", "扭亏", "突破", "批量"]
RISK = ["减持", "立案", "问询", "关注函", "监管函", "异动公告", "澄清", "亏损", "终止", "风险提示", "诉讼", "退市", "下修", "延期"]
THEMES = ["机器人", "半导体", "算力", "CPO", "PCB", "存储", "MLCC", "液冷", "光刻", "稀土", "贵金属", "固态电池", "并购重组", "商业航天", "电力"]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def latest_files(patterns: list[str], limit: int = 12) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(ROOT.glob(pattern))
    return sorted([x for x in files if x.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def date_from_path(path: Path) -> str:
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", str(path))
    return m.group(1) if m else ""


def latest_dated_files(patterns: list[str], limit: int = 8) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(ROOT.glob(pattern))
    dated = [x for x in files if x.is_file() and date_from_path(x)]
    dated.sort(key=lambda p: (date_from_path(p), p.stat().st_mtime), reverse=True)
    return dated[:limit]


def next_trade_date(date: str) -> str:
    day = datetime.strptime(date, "%Y-%m-%d").date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.strftime("%Y-%m-%d")


def date_range(days: int) -> set[str]:
    today = datetime.now().date()
    return {(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days + 1)}


def extract_name_near_code(text: str, code: str) -> str:
    for pattern in [
        rf"([\u4e00-\u9fa5A-Za-z0-9＊*STst]+)\s+{code}",
        rf"{code}\s*\|\s*([\u4e00-\u9fa5A-Za-z0-9＊*STst]{{2,12}})",
        rf"{code}\s+([\u4e00-\u9fa5A-Za-z0-9＊*STst]{{2,12}})",
    ]:
        m = re.search(pattern, text)
        if m:
            name = m.group(1).strip()
            if 1 < len(name) <= 12:
                return name
    return ""


def collect_holdings() -> dict[str, dict[str, str]]:
    by_code: dict[str, dict[str, str]] = {}
    files = latest_dated_files(["raw/01-交割单/*/交割单.md"], limit=1)
    for path in files:
        text = read_text(path)
        # 只优先终态持仓区，避免把当日已卖票误算成持仓。
        parts = re.split(r"##\s*终态持仓|##\s*当前持仓表", text)
        scan = parts[-1] if len(parts) > 1 else text
        scan = scan.split("## 按个股")[0].split("## 备注")[0]
        for code in CODE_RE.findall(scan):
            by_code.setdefault(
                code,
                {
                    "股票代码": code,
                    "股票名称": extract_name_near_code(scan, code),
                    "来源类型": "持仓票",
                    "来源文件": str(path.relative_to(ROOT)),
                },
            )
        if by_code:
            break
    return by_code


def collect_plan_stocks(date: str) -> dict[str, dict[str, str]]:
    by_code: dict[str, dict[str, str]] = {}
    next_date = next_trade_date(date)
    files: list[Path] = []
    for pattern in [
        f"raw/03-每日计划/{date}*.md",
        f"raw/03-每日计划/{next_date}*.md",
        f"wiki/07-作战室/{date}-作战室候选票评分表.md",
        f"wiki/07-作战室/{next_date}-作战室候选票评分表.md",
        f"wiki/07-作战室/{date}-作战室输入候选.md",
        f"wiki/07-作战室/{next_date}-作战室输入候选.md",
    ]:
        files.extend([x for x in ROOT.glob(pattern) if x.is_file()])
    if not files:
        files = latest_dated_files(["raw/03-每日计划/*.md", "wiki/07-作战室/*.md"], limit=4)
    for path in files:
        text = read_text(path)
        for code in CODE_RE.findall(text):
            name = extract_name_near_code(text, code)
            if name in {"明日计划", "风险线索", "正向线索", "高优先线索"}:
                name = ""
            by_code.setdefault(
                code,
                {
                    "股票代码": code,
                    "股票名称": name,
                    "来源类型": "明日计划/作战室票",
                    "来源文件": str(path.relative_to(ROOT)),
                },
            )
    return by_code


def candidate_sources(date: str, days: int) -> list[Path]:
    dates = date_range(days)
    roots = [
        RAW / "05-研报新闻" / "公告",
        RAW / "05-研报新闻" / "互动问答",
        RAW / "05-研报新闻" / "财联社",
        RAW / "05-研报新闻" / "公众号",
        RAW / "11-Codex分析产物" / "公告事件样本",
        RAW / "04-市场数据" / "同花顺热榜",
        RAW / "04-市场数据" / "通达信热榜",
        RAW / "04-市场数据" / "每日涨停全景",
        RAW / "04-市场数据" / "龙虎榜全量",
    ]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".jsonl", ".txt"}:
                continue
            rel = str(path)
            if any(d in rel for d in dates):
                files.append(path)
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:1200]


def source_type(path: Path) -> str:
    text = str(path.relative_to(ROOT))
    if "互动问答" in text:
        return "互动问答"
    if "/公告/" in text or "公告" in text:
        return "公告"
    if "财联社" in text:
        return "财联社"
    if "公众号" in text:
        return "公众号"
    if "龙虎榜" in text:
        return "龙虎榜"
    if "热榜" in text:
        return "热榜"
    if "涨停" in text:
        return "涨停数据"
    return "本地RAW"


def iter_json_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_json_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_json_dicts(child)


def snippets_for_stock(path: Path, stock: dict[str, str]) -> list[str]:
    code = stock["股票代码"]
    name = stock.get("股票名称", "")
    if path.suffix.lower() == ".json":
        payload = read_json(path, None)
        snippets: list[str] = []
        if payload is None:
            return snippets
        for item in iter_json_dicts(payload):
            text = json.dumps(item, ensure_ascii=False)
            item_code = str(
                item.get("股票代码")
                or item.get("代码")
                or item.get("code")
                or item.get("f12")
                or ""
            )
            item_name = str(
                item.get("股票名称")
                or item.get("公司名称")
                or item.get("名称")
                or item.get("name")
                or item.get("f14")
                or ""
            )
            if item_code == code or (name and item_name == name):
                snippets.append(text[:4000])
        return snippets[:8]

    text = read_text(path)
    if not text:
        return []
    lines = text.splitlines()
    snippets = []
    for idx, line in enumerate(lines):
        if code in line or (name and name in line):
            if "|" in line:
                snippets.append(line)
            else:
                start = max(0, idx - 1)
                end = min(len(lines), idx + 3)
                snippets.append("\n".join(lines[start:end]))
    if snippets:
        return snippets[:8]
    compact = text.replace(" ", "")
    if code in compact or (name and name in compact):
        return [text[:1200]]
    return []


def score_hit(stock: dict[str, str], path: Path, text: str) -> dict[str, Any] | None:
    code = stock["股票代码"]
    name = stock.get("股票名称", "")
    haystack = text.replace(" ", "")
    if code not in haystack and (not name or name not in haystack):
        return None
    title = path.stem
    for line in text.splitlines()[:80]:
        clean = line.strip().lstrip("#").strip()
        if clean and len(clean) > 8:
            title = clean[:120]
            break
    positive = [w for w in POSITIVE if w in text]
    risk = [w for w in RISK if w in text]
    themes = [w for w in THEMES if w.lower() in text.lower()]
    score = 10 + len(positive) * 8 + len(risk) * 12 + len(themes) * 3
    if stock.get("来源类型") == "持仓票":
        score += 12
    if source_type(path) in {"公告", "互动问答", "龙虎榜"}:
        score += 10
    if source_type(path) == "热榜":
        score += 6
    compact = re.sub(r"\s+", " ", text)
    excerpt_pos = max([compact.find(code), compact.find(name) if name else -1])
    excerpt = compact[:220] if excerpt_pos < 0 else compact[max(0, excerpt_pos - 80): excerpt_pos + 220]
    fingerprint = hashlib.sha256(f"{code}|{path}".encode("utf-8")).hexdigest()[:16]
    return {
        "指纹": fingerprint,
        "股票代码": code,
        "股票名称": name,
        "股票角色": stock.get("来源类型", ""),
        "来源文件": str(path.relative_to(ROOT)),
        "来源类型": source_type(path),
        "标题": title,
        "正向词": positive,
        "风险词": risk,
        "题材词": themes,
        "重要度评分": score,
        "摘要": excerpt[:260],
    }


def build_payload(date: str, lookback_days: int) -> dict[str, Any]:
    holdings = collect_holdings()
    plans = collect_plan_stocks(date)
    pool = {**plans, **holdings}
    files = candidate_sources(date, lookback_days)
    hits: dict[str, dict[str, Any]] = {}
    for path in files:
        for stock in pool.values():
            for snippet in snippets_for_stock(path, stock):
                hit = score_hit(stock, path, snippet)
                if hit:
                    old = hits.get(hit["指纹"])
                    if not old or hit["重要度评分"] > old["重要度评分"]:
                        hits[hit["指纹"]] = hit
    rows = sorted(hits.values(), key=lambda x: x.get("重要度评分", 0), reverse=True)
    return {
        "日期": date,
        "生成时间": now_text(),
        "持仓票": list(holdings.values()),
        "明日计划票": list(plans.values()),
        "扫描文件数": len(files),
        "线索数": len(rows),
        "高优先线索": [x for x in rows if x.get("重要度评分", 0) >= 32],
        "全部线索": rows,
        "使用边界": "本报告用于晚间买卖决策提醒，不构成自动交易指令；最终看竞价、承接、板块和仓位纪律。",
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['日期']} 22:30 持仓票与明日计划票新闻线索",
        "",
        f"- 生成时间：{payload['生成时间']}",
        f"- 持仓票：{', '.join([x.get('股票名称') or x.get('股票代码') for x in payload['持仓票']]) or '无'}",
        f"- 明日计划票：{', '.join([x.get('股票名称') or x.get('股票代码') for x in payload['明日计划票'][:20]]) or '无'}",
        f"- 扫描文件数：{payload['扫描文件数']}",
        f"- 高优先线索：{len(payload['高优先线索'])}",
        "",
        "## 需要你决策的线索",
        "",
    ]
    important = []
    seen_codes: set[str] = set()
    for row in payload["高优先线索"]:
        code = str(row.get("股票代码") or "")
        if code in seen_codes:
            continue
        important.append(row)
        seen_codes.add(code)
        if len(important) >= 12:
            break
    if not important:
        lines.append("- 暂无高优先线索。")
    for i, row in enumerate(important, 1):
        direction = "风险" if row.get("风险词") else "正向/催化"
        lines += [
            f"### {i}. {row.get('股票名称') or row.get('股票代码')} {direction}线索",
            "",
            f"- 角色：{row.get('股票角色')}",
            f"- 来源：{row.get('来源类型')} / `{row.get('来源文件')}`",
            f"- 标题：{row.get('标题')}",
            f"- 命中：正向={','.join(row.get('正向词', [])) or '-'}；风险={','.join(row.get('风险词', [])) or '-'}；题材={','.join(row.get('题材词', [])) or '-'}",
            f"- 摘要：{row.get('摘要')}",
            "- 需要你判断：明天是加权、观察、降权，还是直接回避？",
            "",
        ]
    lines += [
        "## 全部线索简表",
        "",
        "| 分数 | 股票 | 角色 | 来源 | 标题 |",
        "|---:|---|---|---|---|",
    ]
    for row in payload["全部线索"][:40]:
        lines.append(f"| {row.get('重要度评分','')} | {row.get('股票名称') or row.get('股票代码')} | {row.get('股票角色','')} | {row.get('来源类型','')} | {row.get('标题','')[:80]} |")
    return "\n".join(lines).rstrip() + "\n"


def maybe_send_pending() -> None:
    sender = ROOT / ".system" / "scripts" / "send-feishu-pending-notifications.py"
    if sender.exists():
        subprocess.run(["python3", str(sender)], cwd=str(ROOT), text=True, capture_output=True, timeout=60)


def main() -> int:
    parser = argparse.ArgumentParser(description="持仓票/明日计划票晚间新闻线索雷达")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--lookback-days", type=int, default=2)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()

    payload = build_payload(args.date, args.lookback_days)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.write:
        out_dir = RAW / "11-Codex分析产物" / "晚间个股线索" / args.date
        write_json(out_dir / "evening-stock-news-radar.json", payload)
        md = render_md(payload)
        (out_dir / "evening-stock-news-radar.md").write_text(md, encoding="utf-8")
        (ROOT / "wiki" / "07-作战室" / f"{args.date}-22点30持仓与计划票线索.md").write_text(md, encoding="utf-8")
        if args.notify:
            PENDING.mkdir(parents=True, exist_ok=True)
            notify_path = PENDING / f"{args.date}-2230-持仓与计划票线索.md"
            sent_path = SENT / notify_path.name
            if not sent_path.exists():
                notify_path.write_text(md, encoding="utf-8")
                maybe_send_pending()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
