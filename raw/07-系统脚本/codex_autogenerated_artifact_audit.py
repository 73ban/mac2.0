#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "wiki/09-统计与进化/后台自动产物审计.md"


def git_status() -> list[str]:
    p = subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return [x for x in p.stdout.splitlines() if x.strip()]


def group(path: str) -> str:
    if "wiki/02-L2" in path:
        return "题材卡"
    if "wiki/03-L3" in path:
        return "个股卡"
    if "wiki/07-" in path:
        return "作战室"
    if "wiki/09-" in path:
        return "统计进化"
    if "wiki/10-" in path:
        return "系统配置"
    if "data/facts" in path:
        return "事实层"
    if ".system" in path:
        return "运行状态"
    return "其他"


def main() -> int:
    rows = git_status()
    by = defaultdict(list)
    for line in rows:
        path = line[3:] if len(line) > 3 else line
        by[group(path)].append(line)
    lines = [
        "# 后台自动产物审计",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 未提交/未审计项：{len(rows)}",
        "- 原则：后台自动产物按组审计提交，避免题材卡、个股卡、作战室、系统配置混在一个提交里。",
        "",
        "| 分组 | 数量 | 建议动作 |",
        "|---|---:|---|",
    ]
    advice = {
        "题材卡": "检查是否为当天RAW增量沉淀，可单独提交",
        "个股卡": "检查是否只写入重要催化/确认/否认，再提交",
        "作战室": "保留动态变化和原因，单独提交",
        "统计进化": "确认统计口径后提交",
        "系统配置": "谨慎提交，避免运行态噪音",
        "事实层": "只提交小型事实层和验证结果",
        "运行状态": "一般不提交，除非是明确配置",
        "其他": "人工确认",
    }
    for key, items in sorted(by.items()):
        lines.append(f"| {key} | {len(items)} | {advice.get(key, '人工确认')} |")
    lines += ["", "## 明细", ""]
    for key, items in sorted(by.items()):
        lines += [f"### {key}", ""]
        for item in items[:120]:
            lines.append(f"- `{item}`")
        lines.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "items": len(rows), "output": str(OUT.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
