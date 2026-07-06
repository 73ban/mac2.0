#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FACTS = ROOT / "data/facts/trade_mode_dplus_results.jsonl"
MODE_DIR = ROOT / "wiki/04-L4交易模式与执行/游资交易模式卡片库"
ERROR_PAGE = ROOT / "wiki/05-错误库/交易模式负反馈样本.md"
STATS_PAGE = ROOT / "wiki/09-统计与进化/交易模式D+统计总表.md"
REPORT_ROOT = ROOT / "raw/11-Codex分析产物/交易模式D+验证"

START = "<!-- codex-dplus-stats:start -->"
END = "<!-- codex-dplus-stats:end -->"


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


def pct_fmt(value: Any) -> str:
    if value is None:
        return "待数据"
    try:
        return f"{float(value):.2f}%"
    except Exception:
        return str(value)


def num_fmt(value: Any) -> str:
    if value is None:
        return "待数据"
    try:
        return f"{float(value):.2f}"
    except Exception:
        return str(value)


def mode_file(mode: str) -> Path:
    safe = mode.replace("/", "-").replace("\\", "-").strip() or "待人工归因"
    return MODE_DIR / f"{safe}.md"


def node_return(row: dict[str, Any], node: str, key: str = "close_return_pct") -> float | None:
    value = ((row.get("nodes") or {}).get(node) or {}).get(key)
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"samples": len(items)}
    for node in ("D+1", "D+3", "D+5"):
        returns = [node_return(row, node) for row in items]
        returns = [x for x in returns if x is not None]
        if returns:
            hit = [x for x in returns if x >= 0]
            strong = [x for x in returns if x >= 5]
            fail = [x for x in returns if x <= -5]
            out[node] = {
                "available": len(returns),
                "hit_rate": len(hit) / len(returns) * 100,
                "strong_rate": len(strong) / len(returns) * 100,
                "fail_rate": len(fail) / len(returns) * 100,
                "avg": sum(returns) / len(returns),
            }
        else:
            out[node] = {
                "available": 0,
                "hit_rate": None,
                "strong_rate": None,
                "fail_rate": None,
                "avg": None,
            }
    return out


def conclusion(stats: dict[str, Any]) -> str:
    d1 = stats["D+1"]
    samples = int(d1["available"] or 0)
    avg = d1["avg"]
    hit = d1["hit_rate"]
    fail = d1["fail_rate"]
    if samples < 3:
        return "样本不足，只保留观察。"
    if avg is not None and hit is not None and avg >= 3 and hit >= 55:
        return "当前D+1正反馈，允许继续验证，但仍需按行情分层。"
    if avg is not None and (avg <= -3 or (fail is not None and fail >= 40)):
        return "当前D+1负反馈，优先进入错误库复盘，限制无确认买点。"
    return "当前中性，需继续拆分市场环境、题材阶段和股票角色。"


def render_mode_block(mode: str, items: list[dict[str, Any]], generated_at: str) -> str:
    stats = summarize(items)
    recent = sorted(items, key=lambda x: (str(x.get("date") or ""), str(x.get("code") or "")), reverse=True)[:12]
    lines = [
        START,
        "## Codex D+真实统计回填",
        "",
        f"- 生成时间：{generated_at}",
        f"- 统计口径：只统计已归因到 `{mode}` 的真实成交样本；以成交价为基准，看后续第1/3/5个交易日收盘收益。",
        f"- 当前结论：{conclusion(stats)}",
        "",
        "| 节点 | 可验证样本 | 命中率 | 强反馈率 | 失败率 | 平均收益 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for node in ("D+1", "D+3", "D+5"):
        item = stats[node]
        lines.append(
            f"| {node} | {item['available']} | {pct_fmt(item['hit_rate'])} | {pct_fmt(item['strong_rate'])} | "
            f"{pct_fmt(item['fail_rate'])} | {pct_fmt(item['avg'])} |"
        )
    lines += [
        "",
        "### 最近样本",
        "",
        "| 日期 | 股票 | 操作 | 入场价 | D+1 | D+3 | D+5 | 来源 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in recent:
        source = str(row.get("trade_source") or "")
        lines.append(
            f"| {row.get('date') or ''} | {row.get('name') or ''} {row.get('code') or ''} | {row.get('action') or ''} | "
            f"{num_fmt(row.get('entry_price'))} | {pct_fmt(node_return(row, 'D+1'))} | "
            f"{pct_fmt(node_return(row, 'D+3'))} | {pct_fmt(node_return(row, 'D+5'))} | {source} |"
        )
    lines += [
        "",
        "### 使用约束",
        "",
        "- 正反馈只说明历史样本有效，不等于明天无条件可买。",
        "- 负反馈优先检查：买点是否后排、是否高潮末端、是否题材退潮、是否没有盘口确认。",
        "- 后续修正只追加新结论，不删除旧统计和修正记录。",
        END,
    ]
    return "\n".join(lines)


def render_stats_page(rows: list[dict[str, Any]], by_mode: dict[str, list[dict[str, Any]]], generated_at: str) -> str:
    lines = [
        "# 交易模式D+统计总表",
        "",
        f"- 生成时间：{generated_at}",
        f"- 样本总数：{len(rows)}",
        "- 口径：逐笔成交归因后的真实D+1/D+3/D+5收盘收益；用于训练模式，不构成自动交易指令。",
        "",
        "| 模式 | 样本 | D+1可算 | D+1命中 | D+1失败 | D+1均值 | D+3可算 | D+3均值 | D+5可算 | D+5均值 | 结论 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for mode, items in sorted(by_mode.items(), key=lambda kv: summarize(kv[1])["samples"], reverse=True):
        stats = summarize(items)
        d1, d3, d5 = stats["D+1"], stats["D+3"], stats["D+5"]
        lines.append(
            f"| {mode} | {stats['samples']} | {d1['available']} | {pct_fmt(d1['hit_rate'])} | {pct_fmt(d1['fail_rate'])} | "
            f"{pct_fmt(d1['avg'])} | {d3['available']} | {pct_fmt(d3['avg'])} | {d5['available']} | {pct_fmt(d5['avg'])} | {conclusion(stats)} |"
        )
    return "\n".join(lines) + "\n"


def render_error_page(rows: list[dict[str, Any]], generated_at: str) -> str:
    failed = [row for row in rows if (node_return(row, "D+1") is not None and node_return(row, "D+1") <= -5)]
    failed.sort(key=lambda x: node_return(x, "D+1") or 0)
    lines = [
        "# 交易模式负反馈样本",
        "",
        f"- 生成时间：{generated_at}",
        "- 进入条件：D+1收盘收益 <= -5%。",
        "- 用途：复盘模式失效条件、买点过后、后排、退潮和消息证伪，不用于简单否定某个模式。",
        "",
        "| 日期 | 股票 | 主模式 | 操作 | 入场价 | D+1 | D+3 | D+5 | 需要复盘的问题 | 来源 |",
        "|---|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in failed[:120]:
        mode = row.get("primary_mode") or "待人工归因"
        question = "是否买在后排/高潮末端/退潮扩散/无盘口确认"
        lines.append(
            f"| {row.get('date') or ''} | {row.get('name') or ''} {row.get('code') or ''} | {mode} | {row.get('action') or ''} | "
            f"{num_fmt(row.get('entry_price'))} | {pct_fmt(node_return(row, 'D+1'))} | "
            f"{pct_fmt(node_return(row, 'D+3'))} | {pct_fmt(node_return(row, 'D+5'))} | {question} | {row.get('trade_source') or ''} |"
        )
    if not failed:
        lines.append("| - | - | - | - | - | - | - | - | 当前无D+1<-5样本 | - |")
    return "\n".join(lines) + "\n"


def main() -> int:
    rows = read_jsonl(FACTS)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_mode[str(row.get("primary_mode") or "待人工归因")].append(row)

    updated_modes = 0
    missing_modes: list[str] = []
    for mode, items in sorted(by_mode.items()):
        path = mode_file(mode)
        block = render_mode_block(mode, items, generated_at)
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="ignore")
        else:
            missing_modes.append(mode)
            text = f"# {mode}\n\n## 模式定义\n\n待补充。\n"
        new_text = replace_block(text, block)
        if new_text != text:
            write_text(path, new_text)
            updated_modes += 1

    write_text(STATS_PAGE, render_stats_page(rows, by_mode, generated_at))
    write_text(ERROR_PAGE, render_error_page(rows, generated_at))

    report_dir = REPORT_ROOT / datetime.now().strftime("%Y-%m-%d")
    report = {
        "schema": "73wiki-trade-mode-stats-to-wiki-v1",
        "generatedAt": generated_at,
        "rows": len(rows),
        "modes": len(by_mode),
        "updated_mode_pages": updated_modes,
        "created_or_missing_before": missing_modes,
        "stats_page": str(STATS_PAGE.relative_to(ROOT)),
        "error_page": str(ERROR_PAGE.relative_to(ROOT)),
    }
    write_text(report_dir / "trade-mode-stats-to-wiki.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
