#!/usr/bin/env python3
"""
Fetch public Taoguba pages through self-hosted Firecrawl and store RAW markdown.

This script is intentionally low-frequency/manual. It does not promote
extracted ideas into WIKI rules; Codex analysis and D+ validation happen later.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "raw"
FIRECRAWL_SERVICE_DIR = Path("/Users/qixinchaye/services/firecrawl")
DEFAULT_API_URL = "http://127.0.0.1:3002"


def today_cn() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    raw = parsed.path.strip("/").replace("/", "-") or "home"
    raw = re.sub(r"[^0-9A-Za-z._-]+", "-", raw)
    return raw[:80] or "page"


def extract_markdown(payload: dict) -> str:
    markdown = payload.get("markdown") or ""
    if isinstance(markdown, str):
        return markdown
    return ""


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


def scrape_with_local_api(url: str, api_url: str) -> dict:
    endpoint = f"{api_url.rstrip('/')}/v1/scrape"
    body = json.dumps({"url": url, "formats": ["markdown", "links"]}).encode("utf-8")
    request = Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("success"):
        raise RuntimeError(f"Firecrawl scrape failed: {json.dumps(payload, ensure_ascii=False)[:1000]}")
    return payload


def run_firecrawl(url: str, output_json: Path, api_url: str, auto_start: bool) -> dict:
    ensure_firecrawl(api_url, auto_start=auto_start)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    payload = scrape_with_local_api(url, api_url)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def write_page(url: str, date: str, api_url: str, auto_start: bool) -> Path:
    slug = slug_from_url(url)
    out_dir = RAW_ROOT / "09-短线知识" / "淘股吧" / date / slug
    raw_json = out_dir / "firecrawl_raw.json"
    raw_md = out_dir / "原文.md"
    meta_md = out_dir / "抓取记录.md"

    payload = run_firecrawl(url, raw_json, api_url=api_url, auto_start=auto_start)
    data = payload.get("data") or {}
    markdown = extract_markdown(data)
    metadata = data.get("metadata") or {}

    raw_md.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    meta_md.write_text(
        "\n".join(
            [
                f"# 淘股吧Firecrawl抓取记录",
                "",
                f"- URL：{url}",
                f"- 日期：{date}",
                f"- API：{api_url}",
                f"- 自部署：是",
                f"- 状态码：{metadata.get('statusCode', '')}",
                f"- 标题：{metadata.get('title', '')}",
                f"- 原始JSON：`firecrawl_raw.json`",
                f"- 原文Markdown：`原文.md`",
                "",
                "## 注意",
                "",
                "本文件只代表公开网页抓取成功，不代表观点已被验证；后续必须结合当日市场环境和 D+验证再决定是否沉淀进 WIKI。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=today_cn())
    parser.add_argument("--url", action="append", required=True, help="Public Taoguba URL. Can be repeated.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Self-hosted Firecrawl API URL.")
    parser.add_argument("--no-auto-start", action="store_true", help="Do not auto-start the local Docker service.")
    args = parser.parse_args()

    outputs = []
    for url in args.url:
        outputs.append(write_page(url, args.date, args.api_url, auto_start=not args.no_auto_start))

    print(json.dumps({"ok": True, "outputs": [str(p) for p in outputs]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
