#!/usr/bin/env python3
"""Unified daily workflow runner for 73神话.

Usage:
  python3 raw/07-系统脚本/codex_daily_workflow.py --date 2026-06-29 --phase premarket
  python3 raw/07-系统脚本/codex_daily_workflow.py --date 2026-06-29 --phase postmarket
  python3 raw/07-系统脚本/codex_daily_workflow.py --date 2026-06-29 --phase context

Phases:
  premarket   Prepare war-room, D+ task, AI context.
  context     Only refresh .system/current-ai-context.json and config pointers.
  postmarket  Prepare post-market review/stat/training skeletons.
  full        Run premarket then postmarket. Use only when both inputs exist.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "raw/07-系统脚本"


def run_step(label: str, script: str, date: str, force: bool = False) -> None:
    cmd = [sys.executable, str(SCRIPTS / script), "--date", date]
    if force:
        cmd.append("--force")
    print(f"\n== {label} ==")
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def run_step_write(label: str, script: str, date: str) -> None:
    cmd = [sys.executable, str(SCRIPTS / script), "--date", date, "--write"]
    print(f"\n== {label} ==")
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def run_month_step(label: str, script: str, month: str, as_of: str | None = None) -> None:
    cmd = [sys.executable, str(SCRIPTS / script), "--month", month]
    if as_of:
        cmd.extend(["--as-of", as_of])
    print(f"\n== {label} ==")
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def run_month_write(label: str, script: str, month: str) -> None:
    cmd = [sys.executable, str(SCRIPTS / script), "--month", month, "--write"]
    print(f"\n== {label} ==")
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def run_snapshot(label: str, date: str, session: str) -> None:
    cmd = [sys.executable, str(SCRIPTS / "codex_snapshot_warroom_versions.py"), "--date", date, "--session", session]
    print(f"\n== {label} ==")
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def run_postmarket(date: str, force: bool = False) -> None:
    month = date[:7]
    run_snapshot("warroom postclose snapshot", date, "postclose")
    run_step("postmarket", "codex_prepare_postmarket.py", date, force)
    run_step("market raw derivatives", "codex_extract_market_raw_derivatives.py", date, False)
    run_step_write("board four dragons", "codex_generate_board_dragons.py", date)
    run_step_write("dragon role ranking", "codex_generate_dragon_role_ranking.py", date)
    run_step_write("market structure analysis", "codex_generate_market_structure_analysis.py", date)
    run_step_write("message catalyst score", "codex_score_message_catalysts.py", date)
    run_month_write("monthly board top/bottom", "codex_build_monthly_board_top_bottom.py", month)
    run_month_step("raw coverage", "codex_audit_raw_coverage.py", month, date)
    run_month_step("monthly trade stats", "codex_build_monthly_trade_stats.py", month, date)
    run_month_step("error ledger", "codex_build_error_ledger.py", month)
    run_step("context", "codex_update_ai_context.py", date, False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument(
        "--phase",
        required=True,
        choices=["premarket", "context", "postmarket", "full"],
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.phase == "premarket":
        run_step("premarket", "codex_prepare_trading_day.py", args.date, args.force)
        run_snapshot("warroom preopen snapshot", args.date, "preopen")
    elif args.phase == "context":
        run_step("context", "codex_update_ai_context.py", args.date, False)
    elif args.phase == "postmarket":
        run_postmarket(args.date, args.force)
    elif args.phase == "full":
        run_step("premarket", "codex_prepare_trading_day.py", args.date, args.force)
        run_snapshot("warroom preopen snapshot", args.date, "preopen")
        run_postmarket(args.date, args.force)

    print(f"\ndone phase={args.phase} date={args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
