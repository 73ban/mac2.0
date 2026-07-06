#!/usr/bin/env python3
"""Build an error-candidate JSONL and error-cost ledger draft from wiki tables.

Usage:
  python3 raw/07-系统脚本/codex_build_error_ledger.py --month 2026-06
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def strip_md(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    return text.strip()


def parse_table(path: Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    rows: list[dict] = []
    in_table = False
    for line in text.splitlines():
        if line.startswith("| 日期 | 标的/行为 | 错误类型 |"):
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("|---"):
            continue
        if not line.startswith("|"):
            if rows:
                break
            continue
        parts = [strip_md(x) for x in line.strip().strip("|").split("|")]
        if len(parts) < 6:
            continue
        date, subject, error_type, evidence, impact, action = parts[:6]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            continue
        key = f"{date}|{subject}|{error_type}"
        rows.append(
            {
                "schema": "73wiki-error-candidate-v1",
                "id": "errcand_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12],
                "month": date[:7],
                "date": date,
                "subject": subject,
                "errorType": error_type,
                "evidence": evidence,
                "impact": impact,
                "action": action,
                "status": "candidate",
                "source": path.relative_to(ROOT).as_posix(),
            }
        )
    return rows


def infer_cost_hint(item: dict) -> str:
    text = " ".join(str(item.get(k, "")) for k in ["subject", "impact", "evidence"])
    money = re.search(r"(?:约\s*)?([+\-]\s*\d[\d,]*(?:\.\d+)?)", text)
    if "少赚" in text:
        return "少赚，需按当日分时估算机会成本"
    if "多亏" in text:
        return "多亏，需按应卖点和实际卖点估算"
    if money:
        return money.group(1).replace(" ", "")
    return "待补"


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + ("\n" if rows else ""), encoding="utf-8")


def write_ledger(path: Path, month: str, rows: list[dict]) -> None:
    type_counts: dict[str, int] = {}
    for row in rows:
        for part in re.split(r"\s*/\s*", row["errorType"]):
            type_counts[part] = type_counts.get(part, 0) + 1

    ledger_rows = []
    for row in rows:
        ledger_rows.append(
            "| {date} | {subject} | {etype} | 待补 | 待补 | {cost} | 待补 | 待补 | {impact} | {action} |".format(
                date=row["date"],
                subject=row["subject"],
                etype=row["errorType"],
                cost=infer_cost_hint(row),
                impact=row["impact"],
                action=row["action"],
            )
        )

    type_rows = [
        f"| {etype} | {count} | 待补 | 待补 | {'是' if count >= 2 else '待观察'} | {'升级正式错误页' if count >= 2 else '继续观察'} |"
        for etype, count in sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    md = "\n".join(
        [
            f"# {month} 错误成本账本草案",
            "",
            f"更新时间：{datetime.now().strftime('%Y-%m-%d')}",
            "",
            "## 定位",
            "",
            "本页由 `raw/07-系统脚本/codex_build_error_ledger.py` 从错误候选页生成。当前先固定错误事实、类型和处理动作；金额字段需要后续按成交明细和分时补齐。",
            "",
            f"来源：[[{month}下旬错误候选汇总]]",
            "",
            "## 单笔错误记录",
            "",
            "| 日期 | 股票/行为 | 错误类型 | 对应模式 | 仓位 | 实际亏损/机会成本 | 如果按规则执行 | 错误成本 | 原因 | 改进动作 |",
            "|---|---|---|---|---:|---:|---:|---:|---|---|",
            *ledger_rows,
            "",
            "## 错误类型统计",
            "",
            "| 错误类型 | 次数 | 总成本 | 最大单笔 | 是否重复 | 下周动作 |",
            "|---|---:|---:|---:|---|---|",
            *type_rows,
            "",
            "## 下一步",
            "",
            "1. 先补成交级错误成本。",
            "2. 重复错误优先升级正式错误页，不再只停留在候选汇总。",
            "3. 每周统计错误成本占总亏损比例，作为模式降级依据。",
        ]
    )
    path.write_text(md + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", required=True)
    args = parser.parse_args()

    source = ROOT / "wiki/05-错误库" / f"{args.month}下旬错误候选汇总.md"
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            "\n".join(
                [
                    f"# {args.month}下旬错误候选汇总",
                    "",
                    "## 错误候选表",
                    "",
                    "| 日期 | 标的/行为 | 错误类型 | 证据 | 影响 | 处理动作 |",
                    "|---|---|---|---|---|---|",
                    "",
                    "## 说明",
                    "",
                    "- 本文件由错误账本流程自动建立。",
                    "- 当日复盘确认的错误候选写入上表，再由脚本生成错误成本账本草案。",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    rows = parse_table(source)
    write_jsonl(ROOT / f"data/trading/{args.month}-error-candidates.jsonl", rows)
    write_ledger(ROOT / "wiki/09-统计与进化" / f"{args.month}-错误成本账本草案.md", args.month, rows)
    print(json.dumps({"source": str(source), "candidates": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
