#!/usr/bin/env python3
"""Build monthly top/bottom board ranking summary from daily RAW."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BOARD_DIR = ROOT / "raw/04-市场数据/板块强度"
OUT_DIR = ROOT / "wiki/09-统计与进化"


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("%", "").replace("+", "").strip())
    except Exception:
        return None


def row_name(row: dict[str, Any]) -> str:
    name = str(row.get("板块名称") or row.get("名称") or row.get("name") or "").strip()
    return "" if name in {"—", "-", "无"} else name


def row_code(row: dict[str, Any]) -> str:
    return str(row.get("板块代码") or row.get("代码") or row.get("code") or "").strip()


def normalize_row(row: dict[str, Any], rank: int, side: str) -> dict[str, Any]:
    return {
        "排名": row.get("排名") or row.get("板块排名") or rank,
        "板块代码": row_code(row),
        "板块名称": row_name(row),
        "涨跌幅": number(row.get("涨跌幅")),
        "方向": side,
    }


def extract_from_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    quality = str(payload.get("quality") or payload.get("质量等级") or payload.get("元信息", {}).get("数据缺口") or "")

    top = payload.get("涨幅Top10") or payload.get("涨幅前十") or []
    bottom = payload.get("跌幅Top10") or payload.get("跌幅前十") or []

    if not top and payload.get("板块列表"):
        rows = [row for row in payload["板块列表"] if row_name(row)]
        rows.sort(key=lambda row: (number(row.get("涨跌幅")) is None, -(number(row.get("涨跌幅")) or -9999)))
        top = rows[:10]
        bottom = sorted(rows, key=lambda row: (number(row.get("涨跌幅")) is None, number(row.get("涨跌幅")) or 9999))[:10]
        quality = quality or "全量板块列表转换"

    if not top and payload.get("主线板块"):
        top = payload["主线板块"][:10]
        quality = quality or "复盘重建主线板块，非通达信完整涨跌榜"

    norm_top = [normalize_row(row, i, "涨幅前10") for i, row in enumerate(top[:10], start=1) if row_name(row)]
    norm_bottom = [normalize_row(row, i, "跌幅前10") for i, row in enumerate(bottom[:10], start=1) if row_name(row)]
    return norm_top, norm_bottom, quality


def pick_daily_file(day_dir: Path) -> Path | None:
    preferred = [
        day_dir / "tdx-board-strength.json",
        day_dir / "通达信板块强度.json",
    ]
    for path in preferred:
        if path.exists():
            return path
    files = sorted(path for path in day_dir.glob("*.json") if "sync-conflict" not in path.name)
    return files[0] if files else None


def render_month(month: str, daily: list[dict[str, Any]], agg: dict[str, dict[str, Any]]) -> str:
    lines = [
        f"# {month} 板块涨跌前10月度统计",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 作用",
        "",
        "- 每日复盘必须看最近1个月板块前10/后10，判断主线延续、退潮、反抽和资金切换。",
        "- 涨幅前10统计用于寻找持续主线和新主线。",
        "- 跌幅前10统计用于识别退潮扩散、风险板块和前主线杀跌。",
        "",
        "## 每日涨幅前10",
        "",
        "| 日期 | 排名 | 板块代码 | 板块 | 涨跌幅 | 数据质量 |",
        "|---|---:|---|---|---:|---|",
    ]
    for item in daily:
        for row in item["涨幅前10"]:
            val = "" if row["涨跌幅"] is None else f"{row['涨跌幅']:.2f}%"
            lines.append(f"| {item['日期']} | {row['排名']} | {row['板块代码']} | {row['板块名称']} | {val} | {item['数据质量']} |")
    lines.extend(["", "## 每日跌幅前10", "", "| 日期 | 排名 | 板块代码 | 板块 | 涨跌幅 | 数据质量 |", "|---|---:|---|---|---:|---|"])
    for item in daily:
        for row in item["跌幅前10"]:
            val = "" if row["涨跌幅"] is None else f"{row['涨跌幅']:.2f}%"
            lines.append(f"| {item['日期']} | {row['排名']} | {row['板块代码']} | {row['板块名称']} | {val} | {item['数据质量']} |")

    leaders = sorted(agg.values(), key=lambda x: (-x["涨幅前10次数"], -x["涨幅累计分"], x["板块名称"]))
    laggards = sorted(agg.values(), key=lambda x: (-x["跌幅前10次数"], x["跌幅累计分"], x["板块名称"]))

    lines.extend(["", "## 月内强势板块出现次数", "", "| 排名 | 板块 | 代码 | 涨幅前10次数 | 平均涨跌幅 |", "|---:|---|---|---:|---:|"])
    for i, row in enumerate([x for x in leaders if x["涨幅前10次数"] > 0][:20], start=1):
        avg = row["涨幅累计分"] / row["涨幅前10次数"] if row["涨幅前10次数"] else 0
        lines.append(f"| {i} | {row['板块名称']} | {row['板块代码']} | {row['涨幅前10次数']} | {avg:.2f}% |")

    lines.extend(["", "## 月内弱势板块出现次数", "", "| 排名 | 板块 | 代码 | 跌幅前10次数 | 平均涨跌幅 |", "|---:|---|---|---:|---:|"])
    for i, row in enumerate([x for x in laggards if x["跌幅前10次数"] > 0][:20], start=1):
        avg = row["跌幅累计分"] / row["跌幅前10次数"] if row["跌幅前10次数"] else 0
        lines.append(f"| {i} | {row['板块名称']} | {row['板块代码']} | {row['跌幅前10次数']} | {avg:.2f}% |")

    lines.extend(["", "## 复盘口径", ""])
    lines.append("- 当某板块连续进入涨幅前10，且涨停全景、热榜、成交额榜同步确认，才按主线候选处理。")
    lines.append("- 当某板块连续进入跌幅前10，尤其从前期主线切入跌幅榜，按退潮风险处理。")
    lines.append("- 单日涨幅前10只代表当日异动，不能直接定主线；月度出现次数用于过滤一日游。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default=datetime.now().strftime("%Y-%m"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    daily = []
    agg: dict[str, dict[str, Any]] = defaultdict(lambda: {"板块名称": "", "板块代码": "", "涨幅前10次数": 0, "跌幅前10次数": 0, "涨幅累计分": 0.0, "跌幅累计分": 0.0})
    for day_dir in sorted(BOARD_DIR.glob(f"{args.month}-*")):
        if not day_dir.is_dir() or not re.match(r"\d{4}-\d{2}-\d{2}$", day_dir.name):
            continue
        source = pick_daily_file(day_dir)
        if not source:
            continue
        payload = read_json(source)
        top, bottom, quality = extract_from_payload(payload)
        item = {"日期": day_dir.name, "来源文件": str(source.relative_to(ROOT)), "数据质量": quality or "raw", "涨幅前10": top, "跌幅前10": bottom}
        daily.append(item)
        for row in top:
            key = row["板块代码"] or row["板块名称"]
            agg[key]["板块名称"] = row["板块名称"]
            agg[key]["板块代码"] = row["板块代码"]
            agg[key]["涨幅前10次数"] += 1
            agg[key]["涨幅累计分"] += row["涨跌幅"] or 0
        for row in bottom:
            key = row["板块代码"] or row["板块名称"]
            agg[key]["板块名称"] = row["板块名称"]
            agg[key]["板块代码"] = row["板块代码"]
            agg[key]["跌幅前10次数"] += 1
            agg[key]["跌幅累计分"] += row["涨跌幅"] or 0

    payload = {
        "数据格式": "73wiki-monthly-board-top-bottom-v1",
        "月份": args.month,
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "交易日统计": daily,
        "板块汇总": sorted(agg.values(), key=lambda row: row["板块名称"]),
    }
    if args.write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / f"{args.month}-板块涨跌前10月度统计.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (OUT_DIR / f"{args.month}-板块涨跌前10月度统计.md").write_text(render_month(args.month, daily, agg), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
