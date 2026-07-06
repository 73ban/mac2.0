#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

import openpyxl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_ROOT = PROJECT_ROOT / "wiki" / "sources"


def fmt(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def infer_date(path: Path) -> str:
    match = re.search(r"(20\d{2})[-_年.]?(\d{2})[-_月.]?(\d{2})", path.stem)
    if not match:
        raise ValueError(f"无法从文件名识别日期：{path.name}")
    year, month, day = match.groups()
    return f"{year}-{month}-{day}"


def infer_type(path: Path) -> str:
    name = path.name
    if "持仓" in name:
        return "持仓"
    if "委托" in name or "成交" in name:
        return "委托"
    raise ValueError(f"无法从文件名识别类型，请用 --type 指定：{path.name}")


def row_values(row: Iterable[object]) -> list[object]:
    return list(row)


def render_order(rows: list[list[object]], date: str) -> list[str]:
    lines = [
        f"# {date} 委托明细",
        "",
        "| 时间 | 买卖 | 代码 | 名称 | 委托价 | 委托量 | 成交价 | 成交量 | 状态 |",
        "|------|------|------|------|--------|--------|--------|--------|------|",
    ]
    for row in rows[1:]:
        if not row or row[0] is None:
            continue
        padded = row + [""] * 10
        lines.append(
            f"| {fmt(padded[0])} | {fmt(padded[3])} | {fmt(padded[1])} | {fmt(padded[2])} | "
            f"{fmt(padded[5])} | {fmt(padded[6])} | {fmt(padded[8])} | {fmt(padded[9])} | {fmt(padded[4])} |"
        )
    return lines


def render_position(rows: list[list[object]], date: str) -> list[str]:
    lines = [
        f"# {date} 持仓明细",
        "",
        "| 代码 | 名称 | 持仓量 | 可用 | 成本 | 现价 | 市值 | 浮盈 | 盈亏% |",
        "|------|------|--------|------|------|------|------|------|-------|",
    ]
    for row in rows[1:]:
        if not row or row[0] is None:
            continue
        padded = row + [""] * 11
        lines.append(
            f"| {fmt(padded[0])} | {fmt(padded[1])} | {fmt(padded[2])} | {fmt(padded[3])} | "
            f"{fmt(padded[6])} | {fmt(padded[7])} | {fmt(padded[8])} | {fmt(padded[9])} | {fmt(padded[10])} |"
        )
    return lines


def convert_file(path: Path, out_root: Path, file_type: str | None, date: str | None) -> Path:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError(f"当前脚本只直接支持 .xlsx，请先把 .xls 另存为 .xlsx：{path}")

    actual_type = file_type or infer_type(path)
    actual_date = date or infer_date(path)

    workbook = openpyxl.load_workbook(path, data_only=True)
    sheet = workbook.active
    rows = [row_values(row) for row in sheet.iter_rows(values_only=True)]
    if actual_type == "委托":
        lines = render_order(rows, actual_date)
    elif actual_type == "持仓":
        lines = render_position(rows, actual_date)
    else:
        raise ValueError(f"不支持的类型：{actual_type}")

    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / f"{actual_date}-{actual_type}明细.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="把本机交割单/持仓 .xlsx 转成 Markdown。")
    parser.add_argument("files", nargs="+", help="要转换的 .xlsx 文件，例如 ~/Downloads/20260629 当日委托.xlsx")
    parser.add_argument("--type", choices=["委托", "持仓"], help="文件类型；不传则从文件名推断")
    parser.add_argument("--date", help="交易日期 YYYY-MM-DD；不传则从文件名推断")
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT), help="输出目录，默认写入 wiki/sources")
    args = parser.parse_args()

    out_root = Path(args.out_root).expanduser()
    for file_arg in args.files:
        out_path = convert_file(Path(file_arg), out_root, args.type, args.date)
        print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
