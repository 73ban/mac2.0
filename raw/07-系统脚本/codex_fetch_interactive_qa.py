#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取重点池股票的互动问答 RAW。

沪市使用上证 e 互动公开问答页；深市先登记为待 Playwright/接口补抓。
这个脚本只写 RAW 和缺口，不生成交易结论。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
SYSTEM = ROOT / ".system"
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|43\d{4}|83\d{4}|87\d{4}|92\d{4})(?!\d)")


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


def latest_files(patterns: list[str], limit: int = 8) -> list[Path]:
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


def clean(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_name_near_code(text: str, code: str) -> str:
    for pattern in [
        rf"([\u4e00-\u9fa5A-Za-z0-9＊*STst]+)[（(]?\s*{code}\s*[)）]?",
        rf"{code}\s*[/|\s-]*\s*([\u4e00-\u9fa5A-Za-z0-9＊*STst]{{2,12}})",
    ]:
        m = re.search(pattern, text)
        if m:
            name = re.sub(r"^(代码|股票|名称)$", "", m.group(1)).strip()
            if 1 < len(name) <= 12:
                return name
    return ""


def collect_priority_stocks(date: str, max_stocks: int) -> list[dict[str, str]]:
    next_date = next_trade_date(date)
    sources: list[Path] = []
    sources.extend(latest_dated_files(["raw/01-交割单/*/交割单.md"], limit=1))
    for pattern in [
        f"raw/03-每日计划/{date}*.md",
        f"raw/03-每日计划/{next_date}*.md",
        f"wiki/07-作战室/{date}-作战室候选票评分表.md",
        f"wiki/07-作战室/{next_date}-作战室候选票评分表.md",
        f"wiki/07-作战室/{date}-作战室输入候选.md",
        f"wiki/07-作战室/{next_date}-作战室输入候选.md",
        f"raw/04-市场数据/同花顺热榜/{date}/*.json",
        f"raw/04-市场数据/每日涨停全景/{date}/*.json",
        f"raw/04-市场数据/通达信连板天梯/{date}/*.json",
    ]:
        sources.extend([x for x in ROOT.glob(pattern) if x.is_file()])
    by_code: dict[str, dict[str, str]] = {}
    for path in sources:
        text = read_text(path)
        if "/交割单/" in str(path):
            parts = re.split(r"##\s*终态持仓|##\s*当前持仓表", text)
            text = parts[-1] if len(parts) > 1 else text
            text = text.split("## 按个股")[0].split("## 备注")[0]
        for code in CODE_RE.findall(text):
            name = extract_name_near_code(text, code)
            if name in {"明日计划", "风险线索", "正向线索", "高优先线索"}:
                name = ""
            if code not in by_code:
                by_code[code] = {
                    "股票代码": code,
                    "股票名称": name,
                    "来源": str(path.relative_to(ROOT)),
                }
            elif not by_code[code].get("股票名称") and name:
                by_code[code]["股票名称"] = name
    ordered = list(by_code.values())
    # 持仓和作战室优先，热榜/涨停排后。
    def rank(item: dict[str, str]) -> tuple[int, str]:
        src = item.get("来源", "")
        if "交割单" in src or "当前持仓" in src:
            return (0, item["股票代码"])
        if "作战室" in src or "每日计划" in src or "竞价" in src:
            return (1, item["股票代码"])
        return (2, item["股票代码"])

    ordered.sort(key=rank)
    return ordered[:max_stocks]


def http_get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def parse_sse_items(raw_html: str, code: str, name: str) -> list[dict[str, Any]]:
    blocks = re.split(r'<div class="m_feed_item"', raw_html)
    rows = []
    for block in blocks[1:]:
        item_id = ""
        m_id = re.search(r'id="item-(\d+)"', block)
        if m_id:
            item_id = m_id.group(1)
        texts = re.findall(r'<div class="m_feed_txt"[^>]*>([\s\S]*?)</div>', block)
        if not texts:
            continue
        question = clean(texts[0])
        answer = clean(texts[1]) if len(texts) > 1 else ""
        times = re.findall(r"<span>(\d{4}年\d{2}月\d{2}日\s+\d{2}:\d{2})</span>", block)
        if code not in question and (name and name not in question) and code not in answer and (name and name not in answer):
            continue
        rows.append(
            {
                "平台": "上证e互动",
                "股票代码": code,
                "股票名称": name,
                "问答ID": item_id,
                "问题时间": times[0] if times else "",
                "回复时间": times[-1] if len(times) > 1 else "",
                "投资者问题": question,
                "公司回复原文": answer,
                "原始链接": f"https://sns.sseinfo.com/qadetail.do?questionId={item_id}" if item_id else "https://sns.sseinfo.com/qa.do",
            }
        )
    return rows


def fetch_sse(code: str, name: str, pages: int) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    keyword = name or code
    for page in range(1, pages + 1):
        query = urllib.parse.urlencode({"type": "1", "page": str(page), "keyword": keyword})
        url = f"https://sns.sseinfo.com/getNewDataFullText.do?{query}"
        try:
            raw = http_get(url)
            rows.extend(parse_sse_items(raw, code, name))
        except Exception as exc:
            errors.append(f"{code} {name} page={page}: {exc}")
            break
    return rows, errors


def fetch_sz_playwright(code: str, name: str, limit: int = 20) -> tuple[list[dict[str, Any]], list[str]]:
    helper = ROOT / "raw" / "07-系统脚本" / "codex_fetch_szse_interactive_qa.mjs"
    if not helper.exists():
        return [], [f"{code} {name}: 缺少深交所互动易 Playwright helper"]
    try:
        result = subprocess.run(
            ["node", str(helper), code, name or code, str(limit)],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=45,
        )
        payload = json.loads(result.stdout or "{}")
        rows = payload.get("rows") if isinstance(payload, dict) else []
        if isinstance(rows, list) and rows:
            return rows, []
        reason = payload.get("error") if isinstance(payload, dict) else result.stderr.strip()
        return [], [f"{code} {name}: 深交所互动易未抓到问答 {reason or ''}".strip()]
    except Exception as exc:
        return [], [f"{code} {name}: 深交所互动易 Playwright 抓取失败 {exc}"]


def fetch_sz_batch(stocks: list[dict[str, str]], limit: int = 20) -> dict[str, tuple[list[dict[str, Any]], list[str]]]:
    helper = ROOT / "raw" / "07-系统脚本" / "codex_fetch_szse_interactive_qa.mjs"
    if not stocks:
        return {}
    if not helper.exists():
        return {s["股票代码"]: ([], [f"{s['股票代码']} {s.get('股票名称','')}: 缺少深交所互动易 Playwright helper"]) for s in stocks}
    try:
        input_payload = json.dumps([{**s, "limit": limit} for s in stocks], ensure_ascii=False)
        result = subprocess.run(
            ["node", str(helper), "--batch"],
            input=input_payload,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=max(90, len(stocks) * 18),
        )
        payload = json.loads(result.stdout or "{}")
        out: dict[str, tuple[list[dict[str, Any]], list[str]]] = {}
        for item in payload.get("results", []):
            code = str(item.get("code") or "")
            name = str(item.get("name") or "")
            rows = item.get("rows") if isinstance(item, dict) else []
            if isinstance(rows, list) and rows:
                out[code] = (rows, [])
            else:
                out[code] = ([], [f"{code} {name}: 深交所互动易未抓到问答 {item.get('error','')}".strip()])
        for stock in stocks:
            code = stock["股票代码"]
            out.setdefault(code, ([], [f"{code} {stock.get('股票名称','')}: 深交所互动易批量抓取无返回"]))
        return out
    except Exception as exc:
        return {s["股票代码"]: ([], [f"{s['股票代码']} {s.get('股票名称','')}: 深交所互动易批量抓取失败 {exc}"]) for s in stocks}


def classify_market(code: str) -> str:
    if code.startswith(("60", "68")):
        return "沪市"
    if code.startswith(("00", "30")):
        return "深市"
    return "其他"


IMPORTANT_WORDS = [
    "量产", "供货", "订单", "中标", "客户", "产能", "涨价", "断供", "出口", "海外",
    "认证", "通过验证", "并购", "重组", "收购", "定增", "机器人", "半导体", "算力",
    "光刻", "存储", "CPO", "PCB", "AI", "液冷", "固态电池", "稀土", "贵金属",
]
RISK_WORDS = ["减持", "亏损", "问询", "监管", "澄清", "终止", "诉讼", "立案", "退市", "风险"]


def score_row(row: dict[str, Any]) -> dict[str, Any]:
    text = f"{row.get('投资者问题','')} {row.get('公司回复原文','')}"
    hits = [word for word in IMPORTANT_WORDS if word.lower() in text.lower()]
    risks = [word for word in RISK_WORDS if word in text]
    score = len(hits) * 8 + len(risks) * 10
    if row.get("公司回复原文"):
        score += 8
    row["命中关键词"] = hits
    row["风险关键词"] = risks
    row["重要度评分"] = score
    row["是否需要人工决策"] = score >= 24
    return row


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['日期']} 互动问答RAW",
        "",
        f"- 生成时间：{payload['生成时间']}",
        f"- 重点股票数：{payload['重点股票数']}",
        f"- 问答条数：{payload['问答条数']}",
        f"- 缺口数：{len(payload['抓取缺口'])}",
        "",
        "## 高优先线索",
        "",
        "| 分数 | 平台 | 代码 | 名称 | 问题时间 | 关键词 | 问题 | 回复摘要 |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    for row in payload["高优先线索"][:60]:
        q = str(row.get("投资者问题", ""))[:80]
        a = str(row.get("公司回复原文", ""))[:100]
        lines.append(
            f"| {row.get('重要度评分','')} | {row.get('平台','')} | {row.get('股票代码','')} | {row.get('股票名称','')} | {row.get('问题时间','')} | {'、'.join(row.get('命中关键词', []) + row.get('风险关键词', []))} | {q} | {a} |"
        )
    lines += ["", "## 抓取缺口", ""]
    if payload["抓取缺口"]:
        lines.extend([f"- {x}" for x in payload["抓取缺口"][:80]])
    else:
        lines.append("- 无")
    lines += ["", "## 全部问答", ""]
    for row in payload["全部问答"][:120]:
        lines.append(f"### {row.get('股票代码','')} {row.get('股票名称','')} {row.get('平台','')} {row.get('问题时间','')}")
        lines.append("")
        lines.append(f"- 问：{row.get('投资者问题','')}")
        lines.append(f"- 答：{row.get('公司回复原文','')}")
        lines.append(f"- 链接：{row.get('原始链接','')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取互动易/e互动重点池问答")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--max-stocks", type=int, default=30)
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    stocks = collect_priority_stocks(args.date, args.max_stocks)
    all_rows: list[dict[str, Any]] = []
    gaps: list[str] = []
    sz_results = fetch_sz_batch([s for s in stocks if classify_market(s["股票代码"]) == "深市"], limit=20)
    for stock in stocks:
        code = stock["股票代码"]
        name = stock.get("股票名称", "")
        market = classify_market(code)
        if market == "沪市":
            rows, errors = fetch_sse(code, name, args.pages)
        elif market == "深市":
            rows, errors = sz_results.get(code, ([], [f"{code} {name}: 深交所互动易批量抓取缺结果"]))
        else:
            rows, errors = [], [f"{code} {name}: 非沪深主板/创业板/科创板，暂不抓互动问答"]
        for row in rows:
            row["重点池来源"] = stock.get("来源", "")
            all_rows.append(score_row(row))
        gaps.extend(errors)

    all_rows.sort(key=lambda x: x.get("重要度评分", 0), reverse=True)
    payload = {
        "日期": args.date,
        "生成时间": now_text(),
        "重点股票数": len(stocks),
        "重点股票": stocks,
        "问答条数": len(all_rows),
        "高优先线索": [x for x in all_rows if x.get("重要度评分", 0) >= 24],
        "全部问答": all_rows,
        "抓取缺口": gaps,
        "说明": "沪市为上证e互动公开问答；深市互动易当前登记缺口，后续接 Playwright/加签接口。",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.write:
        out_dir = RAW / "05-研报新闻" / "互动问答" / args.date
        write_json(out_dir / "interactive-qa.json", payload)
        (out_dir / "interactive-qa.md").write_text(render_md(payload), encoding="utf-8")
        write_json(SYSTEM / "interactive-qa-state.json", {"最近运行": now_text(), "日期": args.date, "问答条数": len(all_rows), "缺口数": len(gaps)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
