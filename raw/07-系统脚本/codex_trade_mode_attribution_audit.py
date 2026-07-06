#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [
    ROOT / "wiki/06-持仓与资金管理",
    ROOT / "wiki/09-统计与进化",
    ROOT / "raw/02-每日复盘",
    ROOT / "raw/01-交割单",
]
OUT_RAW = ROOT / f"raw/11-Codex分析产物/交易模式归因审计/{date.today().isoformat()}"
OUT_WIKI = ROOT / f"wiki/09-统计与进化/{date.today().isoformat()}-交易模式归因缺口审计.md"

BUY_RE = re.compile(r"(买入|融资买入|担保品买入|加仓|建仓)")
NEGATIVE_BUY_RE = re.compile(r"(无买入|没有买入|全部卖出，无买入|买入笔数|买入金额|当日合计.*无买入)")
TRADE_FILE_RE = re.compile(r"(交割单|交易记录|复盘|持仓|买卖)")
MODE_MARKERS = [
    "主模式",
    "辅助模式",
    "模式来源",
    "Codex推定",
    "mode_standard_name",
    "交易模式",
    "买入模式",
]


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"PK\x03\x04"):
        return ""
    return data.decode("utf-8", errors="ignore")


def iter_candidates():
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            rel = path.relative_to(ROOT).as_posix()
            if ".stversions" in path.parts or "sync-conflict" in path.name:
                continue
            if TRADE_FILE_RE.search(path.name) or TRADE_FILE_RE.search(rel):
                yield path


def audit_file(path: Path) -> dict | None:
    text = read_text(path)
    if not text.strip():
        return None
    buy_lines = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if not BUY_RE.search(line):
            continue
        if NEGATIVE_BUY_RE.search(line):
            continue
        buy_lines.append((idx, line))
    buy_count = len(buy_lines)
    if buy_count == 0:
        return None
    has_mode = any(marker in text for marker in MODE_MARKERS)
    samples = []
    for idx, line in buy_lines[:5]:
        samples.append({"line": idx, "text": line[:180]})
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "buy_count": buy_count,
        "has_mode_attribution": has_mode,
        "status": "ok" if has_mode else "missing_mode_attribution",
        "samples": samples,
    }


def render_md(items: list[dict]) -> str:
    missing = [item for item in items if not item["has_mode_attribution"]]
    ok = [item for item in items if item["has_mode_attribution"]]
    lines = [
        f"# {date.today().isoformat()} 交易模式归因缺口审计",
        "",
        "## 结论",
        "",
        f"- 有买入记录的复盘/交割单文件：{len(items)}",
        f"- 已出现模式归因字段：{len(ok)}",
        f"- 缺模式归因字段：{len(missing)}",
        "",
        "说明：这是文件级审计。后续还要升级为逐笔交易级归因。",
        "",
        "## 缺口文件",
        "",
        "| 文件 | 买入词命中 | 样例 | 后续动作 |",
        "|---|---:|---|---|",
    ]
    for item in missing[:120]:
        sample = item["samples"][0]["text"].replace("|", "\\|") if item["samples"] else ""
        lines.append(f"| `{item['file']}` | {item['buy_count']} | {sample} | 补主模式/辅助模式/模式来源/置信度 |")
    if not missing:
        lines.append("| 无 | 0 | 无 | 无 |")

    lines += [
        "",
        "## 下一步",
        "",
        "1. 优先补最近 30 个交易日和大亏/大赚日。",
        "2. 每笔买入补：主模式、辅助模式、模式来源、置信度、推定依据。",
        "3. 补完后再按模式、市场状态、情绪周期做胜率拆分。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_RAW.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(iter_candidates()):
        item = audit_file(path)
        if item:
            items.append(item)
    payload = {
        "schema": "73wiki-trade-mode-attribution-audit-v1",
        "date": date.today().isoformat(),
        "total_trade_files": len(items),
        "missing_mode_attribution": sum(1 for item in items if not item["has_mode_attribution"]),
        "items": items,
    }
    (OUT_RAW / "trade-mode-attribution-audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = render_md(items)
    (OUT_RAW / "trade-mode-attribution-audit.md").write_text(md, encoding="utf-8")
    OUT_WIKI.write_text(md, encoding="utf-8")
    print(json.dumps({"ok": True, "total_trade_files": payload["total_trade_files"], "missing": payload["missing_mode_attribution"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
