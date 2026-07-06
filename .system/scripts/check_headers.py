#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import openpyxl


def inspect_file(path: Path, label: str | None = None) -> None:
    path = path.expanduser().resolve()
    workbook = openpyxl.load_workbook(path, data_only=True)
    sheet = workbook.active
    display = label or path.name

    print(f"\n=== {display} headers ===")
    for index, cell in enumerate(sheet[1]):
        print(f"  [{index}] {cell.value}")

    if sheet.max_row >= 2:
        print("  --- first data row ---")
        for index, cell in enumerate(sheet[2]):
            print(f"  [{index}] {cell.value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="检查本机 .xlsx 表头和第一行数据。")
    parser.add_argument("files", nargs="+", help="要检查的 .xlsx 文件")
    parser.add_argument("--label", help="单文件时使用的显示标签")
    args = parser.parse_args()

    for file_arg in args.files:
        inspect_file(Path(file_arg), args.label if len(args.files) == 1 else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
