#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DPLUS = ROOT / "data/facts/trade_mode_dplus_results.jsonl"
RAW = ROOT / "raw"
OUT = RAW / "11-Codex分析产物/交易模式环境拆分"
WIKI = ROOT / "wiki/09-统计与进化/交易模式D+环境拆分.md"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            v = json.loads(line)
        except Exception:
            continue
        if isinstance(v, dict):
            rows.append(v)
    return rows


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def node_ret(row: dict[str, Any], node: str = "D+1") -> float | None:
    v = ((row.get("nodes") or {}).get(node) or {}).get("close_return_pct")
    try:
        return float(v)
    except Exception:
        return None


def hot_context(date: str, code: str) -> dict[str, Any]:
    data = read_json(RAW / "04-市场数据/三榜热度合并" / date / "三榜热度合并.json", {})
    for row in data.get("股票") or []:
        if str(row.get("代码") or "").endswith(code):
            sources = row.get("来源榜单") or []
            source_count = len({str(x).split("#")[0] for x in sources})
            rank = int(row.get("综合排名") or 999)
            return {
                "hot_bucket": "三榜前排" if source_count >= 3 and rank <= 20 else "双榜/前排" if source_count >= 2 or rank <= 20 else "单榜/后排",
                "rank": rank,
                "source_count": source_count,
                "themes": row.get("概念标签") or [],
                "limit_tag": row.get("连板标记") or "",
            }
    return {"hot_bucket": "无三榜记录", "rank": 999, "source_count": 0, "themes": [], "limit_tag": ""}


def role_bucket(row: dict[str, Any], ctx: dict[str, Any]) -> str:
    tag = str(ctx.get("limit_tag") or "")
    name = str(row.get("name") or "")
    mode = str(row.get("primary_mode") or "")
    if "连板" in tag or "板" in tag:
        return "连板/涨停票"
    if mode in {"趋势主升", "容量票强弱锚"}:
        return "趋势/容量票"
    if mode in {"主线核心低吸", "冰点恐慌修复"}:
        return "分歧承接票"
    if mode in {"高低切补涨", "首板新题材试错"}:
        return "低位补涨/试错"
    return "未分层"


def summarize(rows: list[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[key_fn(row)].append(row)
    out = []
    for key, items in buckets.items():
        returns = [node_ret(x) for x in items]
        returns = [x for x in returns if x is not None]
        out.append({
            "bucket": key,
            "samples": len(items),
            "available": len(returns),
            "hit_rate": round(sum(1 for x in returns if x >= 0) / len(returns) * 100, 2) if returns else None,
            "fail_rate": round(sum(1 for x in returns if x <= -5) / len(returns) * 100, 2) if returns else None,
            "avg_d1": round(sum(returns) / len(returns), 2) if returns else None,
        })
    return sorted(out, key=lambda x: (x["bucket"]))


def fmt(v: Any) -> str:
    if v is None:
        return "待数据"
    return str(v)


def table(rows: list[dict[str, Any]], title: str) -> list[str]:
    lines = [f"## {title}", "", "| 分组 | 样本 | 可算 | D+1命中 | D+1失败 | D+1均值 |", "|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append(f"| {row['bucket']} | {row['samples']} | {row['available']} | {fmt(row['hit_rate'])} | {fmt(row['fail_rate'])} | {fmt(row['avg_d1'])} |")
    return lines + [""]


def main() -> int:
    rows = read_jsonl(DPLUS)
    enriched = []
    for row in rows:
        ctx = hot_context(str(row.get("date") or ""), str(row.get("code") or ""))
        item = dict(row)
        item["hot_context"] = ctx
        item["role_bucket"] = role_bucket(row, ctx)
        enriched.append(item)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    by_mode = summarize(enriched, lambda x: str(x.get("primary_mode") or "待人工归因"))
    by_hot = summarize(enriched, lambda x: str((x.get("hot_context") or {}).get("hot_bucket") or "未知"))
    by_role = summarize(enriched, lambda x: str(x.get("role_bucket") or "未知"))
    by_mode_hot = summarize(enriched, lambda x: f"{x.get('primary_mode') or '待人工归因'} × {(x.get('hot_context') or {}).get('hot_bucket') or '未知'}")
    payload = {
        "schema": "73wiki-trade-mode-environment-split-v1",
        "generatedAt": generated_at,
        "rows": len(enriched),
        "byMode": by_mode,
        "byHot": by_hot,
        "byRole": by_role,
        "byModeHot": by_mode_hot,
    }
    today = datetime.now().strftime("%Y-%m-%d")
    write(OUT / today / "trade-mode-environment-split.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# 交易模式D+环境拆分",
        "",
        f"- 生成时间：{generated_at}",
        f"- 样本数：{len(enriched)}",
        "- 当前口径：先按三榜热度、股票角色、模式做粗分层；后续继续接入情绪周期、连板天梯、成交量。",
        "",
    ]
    for part in (
        table(by_mode, "按模式"),
        table(by_hot, "按三榜热度"),
        table(by_role, "按股票角色"),
        table(by_mode_hot, "按模式×热榜"),
    ):
        lines.extend(part)
    md = "\n".join(lines)
    write(OUT / today / "trade-mode-environment-split.md", md)
    write(WIKI, md)
    print(json.dumps({"ok": True, "rows": len(enriched), "output": str(WIKI.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
