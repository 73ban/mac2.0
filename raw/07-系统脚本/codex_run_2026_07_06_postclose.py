#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-command post-close runner for 2026-07-06 P0 closure."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "raw/07-系统脚本"
REPORT = ROOT / "wiki/09-统计与进化/2026-07-06-P0收盘闭环执行报告.md"


def market_closed() -> bool:
    now = datetime.now()
    return now.hour > 15 or (now.hour == 15 and now.minute >= 5)


def run(label: str, args: list[str]) -> dict[str, Any]:
    result = subprocess.run([sys.executable, *args], cwd=str(ROOT), text=True, capture_output=True)
    return {"label": label, "returncode": result.returncode, "stdoutTail": result.stdout[-2000:], "stderrTail": result.stderr[-2000:]}


def main() -> int:
    if not market_closed():
        reason = "未到15:05，不执行2026-07-06收盘闭环"
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            "\n".join(
                [
                    "# 2026-07-06 P0收盘闭环执行报告",
                    "",
                    f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "- 总体：WAITING",
                    f"- 原因：{reason}",
                    "- 到点后执行：`python3 raw/07-系统脚本/codex_run_2026_07_06_postclose.py`",
                    "",
                    "| 步骤 | 状态 |",
                    "|---|---|",
                    "| 公告D+回填 | 待15:05后执行 |",
                    "| 作战室D+回填 | 待15:05后执行 |",
                    "| 每日闭环 | 待15:05后执行 |",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(json.dumps({"ok": False, "reason": reason, "report": str(REPORT.relative_to(ROOT))}, ensure_ascii=False, indent=2))
        return 0
    steps = [
        run("公告D+回填", [str(SCRIPTS / "codex_announcement_dplus_autofill.py"), "--today", "2026-07-06"]),
        run("作战室D+回填", [str(SCRIPTS / "codex_warroom_dplus_autofill.py"), "--today", "2026-07-06"]),
        run("每日闭环", [str(SCRIPTS / "codex_run_daily_closed_loop.py"), "--date", "2026-07-06"]),
    ]
    ok = all(step["returncode"] == 0 for step in steps)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        "\n".join(
            [
                "# 2026-07-06 P0收盘闭环执行报告",
                "",
                f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"- 总体：{'PASS' if ok else 'FAIL'}",
                "",
                "| 步骤 | 返回码 |",
                "|---|---:|",
                *[f"| {step['label']} | {step['returncode']} |" for step in steps],
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({"ok": ok, "report": str(REPORT.relative_to(ROOT)), "steps": steps}, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
