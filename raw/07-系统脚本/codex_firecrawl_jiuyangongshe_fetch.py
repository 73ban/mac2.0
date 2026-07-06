#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch public Jiuyangongshe pages through self-hosted Firecrawl.

The goal is RAW preservation. Signal extraction, stock/theme card updates and
D+ validation happen in later pipeline stages.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "raw"
FIRECRAWL_SERVICE_DIR = Path("/Users/qixinchaye/services/firecrawl")
DEFAULT_API_URL = "http://127.0.0.1:3002"
SITE = "https://www.jiuyangongshe.com"
SEARCH_SEED = "fa3409439e2b45c79176c5eebf75a4f8"

DEFAULT_URLS = [
    f"{SITE}/",
    f"{SITE}/square_action/2_96",
    f"{SITE}/product",
]


def safe_name(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]", "-", str(value or "").strip())
    value = re.sub(r"\s+", "", value)
    return value[:30] or "未命名"


def today_cn() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    raw = parsed.netloc.replace(".", "-") + "-" + (parsed.path.strip("/").replace("/", "-") or "home")
    if parsed.query:
        raw += "-" + hashlib.sha1(parsed.query.encode("utf-8")).hexdigest()[:8]
    raw = re.sub(r"[^0-9A-Za-z._-]+", "-", raw)
    return raw[:100] or "page"


def api_alive(api_url: str) -> bool:
    try:
        with urlopen(f"{api_url.rstrip('/')}/", timeout=3) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def ensure_firecrawl(api_url: str, auto_start: bool) -> None:
    if api_alive(api_url):
        return
    if not auto_start:
        raise RuntimeError(f"Firecrawl local API is not reachable: {api_url}")
    if not FIRECRAWL_SERVICE_DIR.exists():
        raise RuntimeError(f"Firecrawl service directory not found: {FIRECRAWL_SERVICE_DIR}")
    subprocess.run(["docker", "compose", "up", "-d"], check=True, cwd=str(FIRECRAWL_SERVICE_DIR))
    deadline = time.time() + 90
    while time.time() < deadline:
        if api_alive(api_url):
            return
        time.sleep(2)
    raise RuntimeError(f"Firecrawl local API did not become ready: {api_url}")


def scrape(url: str, api_url: str) -> dict:
    endpoint = f"{api_url.rstrip('/')}/v1/scrape"
    body = json.dumps({"url": url, "formats": ["markdown", "links"]}).encode("utf-8")
    req = Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("success"):
        raise RuntimeError(f"Firecrawl scrape failed: {json.dumps(payload, ensure_ascii=False)[:1000]}")
    return payload


def extract_article_links(payload: dict) -> list[str]:
    data = payload.get("data") or {}
    links = data.get("links") or []
    found: list[str] = []
    for value in links:
        url = value.get("url") if isinstance(value, dict) else value
        url = str(url or "").strip()
        if not url:
            continue
        if url.startswith("/"):
            url = SITE + url
        if re.search(r"https://www\.jiuyangongshe\.com/a/[0-9a-zA-Z_-]+", url) and url not in found:
            found.append(url)
    return found


def current_warroom_targets(date: str) -> list[dict]:
    path = RAW_ROOT / "11-Codex分析产物" / "动态作战室" / date / "dynamic-warroom-top5.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    targets: list[dict] = []
    seen: set[str] = set()
    for row in [*(payload.get("holdingsAnalysis") or []), *(payload.get("top5") or [])]:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        key = code or name
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            {
                "code": code,
                "name": name,
                "isHolding": bool(row.get("isHolding")),
                "rank": row.get("rank"),
                "themes": row.get("themes") or [],
                "searchUrl": f"{SITE}/search/{SEARCH_SEED}?k={quote(name)}&type=2",
            }
        )
    return targets


def write_page(url: str, date: str, api_url: str, auto_start: bool, category: str) -> tuple[Path, dict]:
    ensure_firecrawl(api_url, auto_start=auto_start)
    out_dir = RAW_ROOT / "05-研报新闻" / "韭研公社网页" / date / category / slug_from_url(url)
    raw_json = out_dir / "firecrawl_raw.json"
    raw_md = out_dir / "原文.md"
    meta_md = out_dir / "抓取记录.md"
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = scrape(url, api_url=api_url)
    raw_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    data = payload.get("data") or {}
    markdown = data.get("markdown") if isinstance(data.get("markdown"), str) else ""
    metadata = data.get("metadata") or {}
    title = str(metadata.get("title") or "").strip()
    article_links = extract_article_links(payload)

    if title and not markdown.lstrip().startswith("# "):
        markdown = f"# {title}\n\n{markdown}"
    raw_md.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    meta_md.write_text(
        "\n".join(
            [
                "# 韭研公社网页Firecrawl抓取记录",
                "",
                f"- URL：{url}",
                f"- 日期：{date}",
                f"- 类别：{category}",
                f"- API：{api_url}",
                f"- 状态码：{metadata.get('statusCode', '')}",
                f"- 标题：{title}",
                f"- 发现文章链接：{len(article_links)}",
                f"- 原始JSON：`firecrawl_raw.json`",
                f"- 原文Markdown：`原文.md`",
                "",
                "## 注意",
                "",
                "本文件只代表公开网页抓取成功，不代表观点已被验证；后续必须结合热榜、涨停原因、互动易、竞价和 D+验证再决定是否沉淀进 WIKI。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return out_dir, {"url": url, "output": str(out_dir), "articleLinks": article_links}


def write_focus_summary(date: str, rows: list[dict]) -> None:
    out_dir = RAW_ROOT / "05-研报新闻" / "韭研公社网页" / date / "_focus-warroom"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "focus-warroom.json").write_text(json.dumps({"date": date, "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# {date} 韭研公社作战室专项抓取",
        "",
        "用途：围绕当前持仓票和动态作战室Top5抓韭研公社网页逻辑，用于补个股卡、题材卡、每日重要信息Top10和D+验证。",
        "",
        "| 代码 | 名称 | 持仓 | 作战室排名 | 搜索结果 | 详情抓取 | 搜索页 |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('code') or ''} | {row.get('name') or ''} | {'是' if row.get('isHolding') else '否'} | {row.get('rank') or ''} | {row.get('articleLinkCount') or 0} | {len(row.get('articleOutputs') or [])} | `{row.get('searchOutput') or ''}` |"
        )
    (out_dir / "focus-warroom.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="韭研公社网页 Firecrawl RAW 抓取")
    parser.add_argument("--date", default=today_cn())
    parser.add_argument("--url", action="append", help="Public Jiuyangongshe URL. Can be repeated.")
    parser.add_argument("--default-frontpages", action="store_true", help="Fetch homepage/square/product frontpages.")
    parser.add_argument("--discover-articles", type=int, default=0, help="Fetch N article links discovered from frontpages.")
    parser.add_argument("--focus-current-warroom", action="store_true", help="Fetch Jiuyangongshe search pages for current holdings and dynamic warroom Top5.")
    parser.add_argument("--focus-articles-per-stock", type=int, default=3, help="Article detail pages to fetch for each warroom stock.")
    parser.add_argument("--category", default="manual")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--no-auto-start", action="store_true")
    args = parser.parse_args()

    urls = list(args.url or [])
    if args.default_frontpages:
        urls.extend(DEFAULT_URLS)
    if not urls and not args.focus_current_warroom:
        raise SystemExit("No URL specified. Use --url or --default-frontpages.")

    outputs = []
    discovered: list[str] = []
    for url in urls:
        out_dir, item = write_page(url, args.date, args.api_url, not args.no_auto_start, args.category)
        outputs.append(str(out_dir))
        for link in item["articleLinks"]:
            if link not in discovered:
                discovered.append(link)

    article_outputs = []
    if args.discover_articles:
        for url in discovered[: args.discover_articles]:
            out_dir, _ = write_page(url, args.date, args.api_url, not args.no_auto_start, "article")
            article_outputs.append(str(out_dir))

    focus_rows = []
    if args.focus_current_warroom:
        for target in current_warroom_targets(args.date):
            category = f"focus-stock-{target.get('code') or 'nocode'}-{safe_name(target.get('name') or '')}"
            out_dir, item = write_page(target["searchUrl"], args.date, args.api_url, not args.no_auto_start, category)
            links = item.get("articleLinks") or []
            outputs_for_target = []
            for url in links[: args.focus_articles_per_stock]:
                article_dir, _ = write_page(url, args.date, args.api_url, not args.no_auto_start, category)
                outputs_for_target.append(str(article_dir))
            focus_rows.append(
                {
                    **target,
                    "searchOutput": str(out_dir),
                    "articleLinkCount": len(links),
                    "articleOutputs": outputs_for_target,
                }
            )
        write_focus_summary(args.date, focus_rows)

    print(
        json.dumps(
            {
                "ok": True,
                "date": args.date,
                "frontpageOutputs": outputs,
                "discoveredArticles": len(discovered),
                "articleOutputs": article_outputs,
                "focusRows": focus_rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
