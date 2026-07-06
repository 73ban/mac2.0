#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ATTRIBUTIONS = ROOT / "data/facts/trade_mode_attributions.jsonl"
DPLUS = ROOT / "data/facts/trade_mode_dplus_results.jsonl"
REPORT_ROOT = ROOT / "raw/11-Codex分析产物/交易模式原地回填"

START = "<!-- codex-trade-mode-backfill:start -->"
END = "<!-- codex-trade-mode-backfill:end -->"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def replace_block(text: str, block: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if pattern.search(text):
        return pattern.sub(block, text)
    if not text.endswith("\n"):
        text += "\n"
    return text + "\n" + block + "\n"


def clean_cell(value: Any, limit: int = 90) -> str:
    text = str(value or "").replace("\n", " ").replace("|", "\\|").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def pct(value: Any) -> str:
    if value is None:
        return "待数据"
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return str(value)


def dplus_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        rid = str(row.get("result_id") or "")
        key = rid.replace("trade-mode-dplus:", "", 1)
        if key:
            out[key] = row
    return out


def render_block(items: list[dict[str, Any]], dplus_by_id: dict[str, dict[str, Any]], generated_at: str) -> str:
    lines = [
        START,
        "## Codex逐笔模式归因回填",
        "",
        f"- 生成时间：{generated_at}",
        "- 说明：本块是对上方真实成交记录的二次归因，不改动原始成交表；用于后续按模式统计胜率、复盘错误和训练作战室。",
        "- 口径：主模式/辅助模式来自同日复盘、题材、热榜、盘口语义和D+验证的综合推定；`待人工归因`表示证据不足。",
        "",
        "| 时间 | 股票 | 操作 | 价格 | 主模式 | 辅助模式 | 置信度 | D+1 | D+3 | D+5 | 归因依据 |",
        "|---|---|---|---:|---|---|---|---:|---:|---:|---|",
    ]
    for row in sorted(items, key=lambda x: (str(x.get("date") or ""), int(x.get("trade_index") or 0))):
        did = dplus_by_id.get(str(row.get("attribution_id") or ""), {})
        nodes = did.get("nodes") or {}
        evidence = "；".join(clean_cell(x, 28) for x in (row.get("evidence") or [])[:3]) or "待补充"
        secondary = "、".join(clean_cell(x, 20) for x in (row.get("secondary_modes") or [])[:4]) or "-"
        lines.append(
            f"| {clean_cell(row.get('time'))} | {clean_cell(row.get('name'), 36)} {clean_cell(row.get('code'), 12)} | "
            f"{clean_cell(row.get('action'), 28)} | {clean_cell(row.get('price'), 18)} | {clean_cell(row.get('primary_mode'), 24)} | "
            f"{secondary} | {clean_cell(row.get('confidence'), 12)} | "
            f"{pct(((nodes.get('D+1') or {}).get('close_return_pct')))} | "
            f"{pct(((nodes.get('D+3') or {}).get('close_return_pct')))} | "
            f"{pct(((nodes.get('D+5') or {}).get('close_return_pct')))} | {evidence} |"
        )
    lines += [
        "",
        "### 回填后的复盘用途",
        "",
        "- 大赚/大亏日按主模式聚合，检查哪类买点贡献收益或制造回撤。",
        "- 同一股票多笔买入按同一模式聚合，但保留逐笔价格，避免均价掩盖错误买点。",
        "- 以后如果修正模式，不删除本块历史判断，只由脚本用最新归一化口径刷新。",
        END,
    ]
    return "\n".join(lines)


def main() -> int:
    attributions = read_jsonl(ATTRIBUTIONS)
    dplus_by_id = dplus_map(read_jsonl(DPLUS))
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped: list[str] = []
    for row in attributions:
        source = str(row.get("source") or "")
        if not source.startswith("wiki/"):
            skipped.append(source)
            continue
        path = ROOT / source
        if not path.exists() or path.suffix.lower() != ".md":
            skipped.append(source)
            continue
        by_source[source].append(row)

    updated: list[str] = []
    for source, items in sorted(by_source.items()):
        path = ROOT / source
        text = path.read_text(encoding="utf-8", errors="ignore")
        block = render_block(items, dplus_by_id, generated_at)
        new_text = replace_block(text, block)
        if new_text != text:
            write_text(path, new_text)
            updated.append(source)

    report_dir = REPORT_ROOT / datetime.now().strftime("%Y-%m-%d")
    report = {
        "schema": "73wiki-trade-mode-inplace-backfill-v1",
        "generatedAt": generated_at,
        "attribution_rows": len(attributions),
        "source_files": len(by_source),
        "updated_files": len(updated),
        "skipped_sources": sorted(set(x for x in skipped if x)),
        "updated": updated,
    }
    write_text(report_dir / "trade-mode-inplace-backfill.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = [
        f"# {datetime.now().strftime('%Y-%m-%d')} 交易模式原地回填报告",
        "",
        f"- 生成时间：{generated_at}",
        f"- 逐笔归因：{len(attributions)}",
        f"- 命中文件：{len(by_source)}",
        f"- 已更新文件：{len(updated)}",
        "",
        "## 已更新文件",
        "",
    ]
    for source in updated:
        lines.append(f"- `{source}`")
    if not updated:
        lines.append("- 无")
    write_text(report_dir / "trade-mode-inplace-backfill.md", "\n".join(lines) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
