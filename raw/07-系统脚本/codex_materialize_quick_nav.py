#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Materialize tradingBrain.quickNav into JSON and a WIKI entry page."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "73wiki.config.json"
OUT_JSON = ROOT / ".system/quick-nav.json"
OUT_MD = ROOT / "wiki/00-总纲/今日导航.md"


def load_nav() -> list[dict[str, Any]]:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    nav = ((data.get("tradingBrain") or {}).get("quickNav") or [])
    return nav if isinstance(nav, list) else []


def render(nav: list[dict[str, Any]]) -> str:
    lines = [
        "# 今日导航",
        "",
        f"更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| 入口 | 路径 | 状态 |",
        "|---|---|---|",
    ]
    for item in nav:
        path = str(item.get("path") or "")
        exists = (ROOT / path).exists()
        lines.append(f"| {item.get('title', '')} | `{path}` | {'OK' if exists else '待确认'} |")
    lines.extend(["", "## 说明", "", "- 本页由 `73wiki.config.json` 的 `tradingBrain.quickNav` 生成。", "- 如果前端左侧导航支持配置读取，直接读取 `.system/quick-nav.json`。"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 quickNav 导航产物")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    nav = load_nav()
    payload = {"schema": "73wiki-quick-nav-v1", "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "items": nav}
    if args.write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.write_text(render(nav), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
