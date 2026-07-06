#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验收本机或用户导入的 09:25 竞价弱转强 RAW。"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "raw" / "04-市场数据" / "竞价弱转强"
REPORT_DIR = ROOT / "wiki" / "09-统计与进化"

REQUIRED_FIELDS = [
    "股票代码",
    "股票名称",
    "昨日弱的原因",
    "今日转强证据",
    "竞价涨幅",
    "竞价金额",
    "竞价量占昨日成交额比例",
    "是否强于板块",
    "是否强于同身位",
    "隔夜催化",
    "个股地位",
    "操作分级",
    "买点",
    "止损",
    "骗炮风险",
]

ENGLISH_BAD_KEYS = [
    "weak",
    "strong",
    "limitUpCount",
    "code",
    "name",
    "reason",
    "score",
    "rank",
    "buy",
    "sell",
]


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def iter_rows(obj: Any):
    if isinstance(obj, list):
        for item in obj:
            yield from iter_rows(item)
    elif isinstance(obj, dict):
        if any(key in obj for key in ("股票代码", "股票名称", "操作分级")):
            yield obj
        for key in ("数据", "记录", "候选", "竞价弱转强", "items", "rows", "data"):
            value = obj.get(key)
            if isinstance(value, (list, dict)):
                yield from iter_rows(value)


def nonempty(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text not in {"-", "—", "无", "暂无", "null", "None"}


def validate_row(row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    code = str(row.get("股票代码", "")).strip()
    name = str(row.get("股票名称", "")).strip()
    label = f"{name or '未命名'} {code or '无代码'}"
    for field in REQUIRED_FIELDS:
        if not nonempty(row.get(field)):
            issues.append(f"{label} 缺字段：{field}")
    if code and not re.fullmatch(r"\d{6}", code):
        issues.append(f"{label} 股票代码格式错误")
    grade = str(row.get("操作分级", "")).strip()
    if grade and not any(x in grade for x in ("A", "B", "C", "D", "可参与", "观察", "回避", "骗炮")):
        issues.append(f"{label} 操作分级不是 A/B/C/D 口径")
    weak_reason = str(row.get("昨日弱的原因", "")).strip()
    if weak_reason and len(weak_reason) < 8:
        issues.append(f"{label} 昨日弱的原因过短，疑似套话")
    evidence = str(row.get("今日转强证据", "")).strip()
    if evidence and len(evidence) < 12:
        issues.append(f"{label} 今日转强证据过短，疑似套话")
    if "A" in grade and ("不买" in str(row.get("买点", "")) or not nonempty(row.get("买点"))):
        issues.append(f"{label} A级候选没有可执行买点")
    return issues


def render_report(date: str, payload: dict[str, Any]) -> str:
    lines = [
        f"# {date} 竞价弱转强验收",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- JSON 文件：`{payload['json_path']}`",
        f"- MD 文件：`{payload['md_path']}`",
        f"- 验收结果：{payload['grade']}",
        f"- 候选数量：{payload['row_count']}",
        f"- 问题数量：{len(payload['issues'])}",
        "",
        "## 问题清单",
        "",
    ]
    if payload["issues"]:
        lines.extend([f"- {issue}" for issue in payload["issues"]])
    else:
        lines.append("- 未发现硬性缺口。")
    lines += [
        "",
        "## 候选简表",
        "",
        "| 股票 | 分级 | 昨日弱因 | 今日转强证据 | 风险 |",
        "|---|---|---|---|---|",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row.get('股票名称','')} {row.get('股票代码','')} | {row.get('操作分级','')} | {str(row.get('昨日弱的原因',''))[:40]} | {str(row.get('今日转强证据',''))[:50]} | {str(row.get('骗炮风险',''))[:40]} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="竞价弱转强RAW验收")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    base = RAW_DIR / args.date
    json_path = base / "0925-竞价弱转强.json"
    md_path = base / "0925-竞价弱转强.md"
    issues: list[str] = []
    if not json_path.exists():
        issues.append(f"缺少 JSON：{json_path.relative_to(ROOT)}")
    if not md_path.exists():
        issues.append(f"缺少 MD：{md_path.relative_to(ROOT)}")

    rows: list[dict[str, Any]] = []
    if json_path.exists():
        raw = read_json(json_path, {})
        rows = list(iter_rows(raw))
        if not rows:
            issues.append("JSON 未识别到任何候选票记录")
        text = json.dumps(raw, ensure_ascii=False)
        for bad in ENGLISH_BAD_KEYS:
            if bad in text:
                issues.append(f"发现不建议使用的英文字段或词：{bad}")
    for row in rows:
        issues.extend(validate_row(row))

    grade = "PASS" if not issues else ("MISSING" if not json_path.exists() or not md_path.exists() else "FAIL")
    payload = {
        "date": args.date,
        "json_path": str(json_path.relative_to(ROOT)),
        "md_path": str(md_path.relative_to(ROOT)),
        "grade": grade,
        "row_count": len(rows),
        "issues": issues,
        "rows": rows,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.write:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (REPORT_DIR / f"{args.date}-竞价弱转强验收.md").write_text(render_report(args.date, payload), encoding="utf-8")
    return 0 if grade == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
