#!/usr/bin/env python3
"""Convert TDX concept board CSV into standard board-strength RAW."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_MARKET = ROOT / "raw/04-市场数据"


def number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace("%", "").strip())
    except Exception:
        return None


def date_from_name(path: Path) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if not match:
        raise ValueError(f"Cannot infer trade date from {path}")
    return match.group(1)


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = []
        for row in csv.DictReader(handle):
            code = str(row.get("代码") or row.get("code") or "").strip()
            name = str(row.get("名称") or row.get("name") or "").strip()
            if not code or not name:
                continue
            rows.append(
                {
                    "板块代码": code,
                    "板块名称": name,
                    "来源": "通达信",
                    "现价": number(row.get("现价") or row.get("price")),
                    "涨跌幅": number(row.get("涨跌幅(%)") or row.get("changePercent")),
                    "市场": str(row.get("market") or "").strip(),
                    "涨停家数": None,
                    "上涨家数": None,
                    "下跌家数": None,
                    "成交额": "",
                    "领涨股": [],
                    "板块催化摘要": "",
                    "数据缺口": "CSV 只有板块代码、板块名称、现价、涨跌幅；涨停家数、上涨家数、下跌家数、领涨股、板块催化摘要需要 Mac 本机脚本补采或用户导入 RAW。",
                }
            )
    rows.sort(key=lambda item: (item["涨跌幅"] is None, -(item["涨跌幅"] or -9999), item["板块代码"]))
    for index, row in enumerate(rows, start=1):
        row["板块排名"] = index
    return rows


def render_markdown(trade_date: str, payload: dict[str, Any]) -> str:
    rows = payload["板块列表"]
    top_rows = rows[:50]
    bottom_rows = rows[-30:]
    up_rows = [row for row in rows if (row.get("涨跌幅") or 0) > 0]
    down_rows = [row for row in rows if (row.get("涨跌幅") or 0) < 0]

    def table(items: list[dict[str, Any]]) -> list[str]:
        out = ["| 排名 | 板块代码 | 板块 | 涨跌幅% | 现价 | 涨停数 | 领涨股 | 催化摘要 |", "|---:|---|---|---:|---:|---:|---|---|"]
        for row in items:
            leaders = "、".join(f"{item.get('名称','')}({item.get('代码','')})" for item in row.get("领涨股", [])[:3])
            out.append(
                f"| {row.get('板块排名','')} | {row.get('板块代码','')} | {row.get('板块名称','')} | "
                f"{row.get('涨跌幅') if row.get('涨跌幅') is not None else ''} | "
                f"{row.get('现价') if row.get('现价') is not None else ''} | "
                f"{row.get('涨停家数') if row.get('涨停家数') is not None else ''} | "
                f"{leaders} | {row.get('板块催化摘要','')} |"
            )
        return out

    lines = [
        f"# {trade_date} 通达信概念板块强度全量排名",
        "",
        f"生成时间：{payload['生成时间']}",
        "",
        "## 元信息",
        "",
        "```yaml",
        f"来源: {payload['来源']}",
        f"源CSV: {payload['源CSV']}",
        f"板块总数: {payload['元信息']['板块总数']}",
        f"排名范围: {payload['元信息']['排名范围']}",
        f"是否样本: {'是' if payload['元信息']['是否样本'] else '否'}",
        f"上涨板块数: {payload['元信息']['上涨板块数']}",
        f"下跌板块数: {payload['元信息']['下跌板块数']}",
        f"中位涨跌幅: {payload['元信息']['中位涨跌幅']}",
        f"数据缺口: {payload['元信息']['数据缺口']}",
        "```",
        "",
        "## 板块涨幅 Top50",
        "",
        *table(top_rows),
        "",
        "## 下跌板块 Bottom30",
        "",
        *table(bottom_rows),
        "",
        "## 全量排名",
        "",
        *table(rows),
        "",
        "## 口径说明",
        "",
        f"- 本文件由通达信概念板块 CSV 转换，当前可读板块 {len(rows)} 个。",
        "- D+板块对比已具备基础字段：板块代码、板块名称、涨跌幅。",
        "- 涨停家数、领涨股、催化摘要暂缺，需要 Mac 本机脚本补采或用户导入 RAW。",
        f"- 上涨板块 {len(up_rows)} 个，下跌板块 {len(down_rows)} 个。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="")
    parser.add_argument("--csv", default="")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else None
    if csv_path is None:
        trade_date = args.date or datetime.now().strftime("%Y-%m-%d")
        csv_path = RAW_MARKET / f"通达信概念板块全列表-{trade_date}.csv"
    if not csv_path.is_absolute():
        csv_path = ROOT / csv_path
    trade_date = args.date or date_from_name(csv_path)
    rows = read_csv(csv_path)
    changes = [row["涨跌幅"] for row in rows if row["涨跌幅"] is not None]
    sorted_changes = sorted(changes)
    median = None
    if sorted_changes:
        mid = len(sorted_changes) // 2
        median = sorted_changes[mid] if len(sorted_changes) % 2 else round((sorted_changes[mid - 1] + sorted_changes[mid]) / 2, 2)
    out_dir = RAW_MARKET / "板块强度" / trade_date
    payload = {
        "数据格式": "73wiki-通达信板块强度-v1",
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "日期": trade_date,
        "来源": "通达信概念板块全列表CSV",
        "源CSV": str(csv_path.relative_to(ROOT)),
        "元信息": {
            "板块总数": len(rows),
            "排名范围": "全量",
            "是否样本": False,
            "上涨板块数": sum(1 for value in changes if value > 0),
            "平盘板块数": sum(1 for value in changes if value == 0),
            "下跌板块数": sum(1 for value in changes if value < 0),
            "中位涨跌幅": median,
            "数据缺口": "CSV 缺少涨停家数、上涨家数、下跌家数、领涨股、板块催化摘要；请通过 Mac 本机脚本补采或用户导入 RAW。",
        },
        "板块列表": rows,
        "输出文件": {
            "JSON": f"raw/04-市场数据/板块强度/{trade_date}/通达信板块强度.json",
            "Markdown": f"raw/04-市场数据/板块强度/{trade_date}/通达信板块强度.md",
        },
    }
    if args.write:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "通达信板块强度.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out_dir / "通达信板块强度.md").write_text(render_markdown(trade_date, payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
