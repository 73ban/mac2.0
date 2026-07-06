#!/usr/bin/env python3
"""Run the daily closed loop for 73神话.

This script is an orchestrator. It does not replace the specialized scripts;
it runs them in the order required for the daily review loop:

RAW -> Codex derivatives -> WIKI publish -> D+/war-room validation ->
AI context -> Mac local archive package -> Syncthing scan -> report.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "raw/07-系统脚本"
REPORT_DIR = ROOT / "wiki/09-统计与进化"
CODEX_OUT = ROOT / "raw/11-Codex分析产物"
LOCAL_ARCHIVE = CODEX_OUT / "Mac本机闭环归档"
SYNCTHING_CONFIG = Path.home() / "Library/Application Support/Syncthing/config.xml"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def run_cmd(label: str, cmd: list[str], allow_fail: bool = False) -> dict[str, Any]:
    started = now_text()
    result = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    ok = result.returncode == 0
    if not ok and not allow_fail:
        status = "fail"
    else:
        status = "ok" if ok else "warn"
    return {
        "label": label,
        "status": status,
        "returncode": result.returncode,
        "startedAt": started,
        "finishedAt": now_text(),
        "cmd": " ".join(cmd),
        "stdoutTail": result.stdout[-4000:],
        "stderrTail": result.stderr[-4000:],
    }


def run_script(label: str, script: str, args: list[str] | None = None, allow_fail: bool = False) -> dict[str, Any]:
    return run_cmd(label, [sys.executable, str(SCRIPTS / script), *(args or [])], allow_fail=allow_fail)


def copy_if_exists(src: Path, dst_root: Path) -> str | None:
    if not src.exists() or not src.is_file():
        return None
    if ".stfolder" in src.parts or ".stversions" in src.parts:
        return None
    if "每日复盘" in src.parts and "市场数据补全-" in src.name:
        return None
    dst = dst_root / rel(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return rel(src)


def build_local_archive_package(date: str) -> dict[str, Any]:
    out = LOCAL_ARCHIVE / date
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    roots = [
        ROOT / "raw/01-交割单" / date,
        ROOT / "raw/11-Codex分析产物" / date,
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            item = copy_if_exists(path, out)
            if item:
                copied.append(item)

    for pattern_root, pattern in [
        (ROOT / "raw/02-每日复盘", f"{date}*"),
        (ROOT / "raw/04-市场数据", f"**/*{date}*"),
        (ROOT / "raw/10-飞书交易沟通", "**/*"),
    ]:
        if not pattern_root.exists():
            continue
        for path in pattern_root.glob(pattern):
            item = copy_if_exists(path, out)
            if item:
                copied.append(item)

    for script in [
        "codex_extract_market_raw_derivatives.py",
        "codex_daily_workflow.py",
        "codex_ingest_feishu_message.py",
        "codex_raw_watch.py",
        "codex_publish_daily_raw_to_wiki.py",
        "codex_run_daily_closed_loop.py",
    ]:
        item = copy_if_exists(SCRIPTS / script, out)
        if item:
            copied.append(item)

    for path in [
        ROOT / f"wiki/09-统计与进化/{date}-复盘.md",
        ROOT / f"wiki/06-持仓与资金管理/{date}-交割单.md",
        ROOT / f"wiki/09-统计与进化/{date}-数据提取补齐报告.md",
        ROOT / f"wiki/09-统计与进化/{date}-每日闭环运行报告.md",
    ]:
        item = copy_if_exists(path, out)
        if item:
            copied.append(item)

    manifest = out / "Mac本机闭环归档清单.md"
    unique = sorted(set(copied))
    manifest.write_text(
        "\n".join(
            [
                f"# {date} Mac 本机闭环归档清单",
                "",
                f"- 生成时间：{now_text()}",
                "- 用途：归档 Mac 本机当日闭环涉及的交割单、复盘、市场数据、飞书沟通、分析产物和关键脚本。",
                "- 规则：当前 73wiki 不再向 Windows/云服务器/外部事实层回传；本目录只作为本机审计和回溯入口。",
                "- 复制口径：如需人工备份，把本目录作为 Mac 本机归档复制，不作为另一台机器的任务入口。",
                "",
                "## 已复制文件",
                *[f"- {x}" for x in unique],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"path": rel(out), "files": len(unique) + 1, "copied": unique[:20]}


def syncthing_api_key() -> str:
    if not SYNCTHING_CONFIG.exists():
        return ""
    root = ET.parse(SYNCTHING_CONFIG).getroot()
    return root.findtext("gui/apikey") or ""


def syncthing_request(path: str, method: str = "GET", data: Any | None = None) -> Any:
    key = syncthing_api_key()
    if not key:
        raise RuntimeError("Syncthing API key not found")
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:8384{path}",
        data=body,
        method=method,
        headers={"X-API-Key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else None


def syncthing_scan_and_status() -> dict[str, Any]:
    status: dict[str, Any] = {"ok": False, "folders": {}}
    try:
        for folder in ["mac-wiki", "mac-templates", "raw-09", "raw-10", "raw-11"]:
            try:
                syncthing_request(f"/rest/db/scan?folder={folder}", method="POST")
            except Exception as error:
                status["folders"][folder] = {"scanError": str(error)}
        connections = syncthing_request("/rest/system/connections")
        connected = connections.get("connections", {}) if isinstance(connections, dict) else {}
        status["connectedDeviceCount"] = sum(1 for state in connected.values() if isinstance(state, dict) and state.get("connected"))
        for folder in ["raw-09", "raw-10", "raw-11"]:
            try:
                completion = syncthing_request(f"/rest/db/status?folder={urllib.parse.quote(folder)}")
                status["folders"][folder] = {
                    **status["folders"].get(folder, {}),
                    "state": completion.get("state"),
                    "errors": completion.get("errors"),
                }
            except Exception as error:
                status["folders"][folder] = {**status["folders"].get(folder, {}), "completionError": str(error)}
        status["ok"] = True
    except Exception as error:
        status["error"] = str(error)
    return status


def required_file_status(date: str) -> list[dict[str, Any]]:
    paths = [
        ROOT / f"raw/01-交割单/{date}/交割单.md",
        ROOT / f"raw/02-每日复盘/{date}-复盘.md",
        ROOT / f"raw/04-市场数据/每日涨停全景/{date}/tdx-daily-limit.json",
        ROOT / f"raw/04-市场数据/首板涨停催化/{date}/tdx-first-board-catalyst.json",
        ROOT / f"raw/04-市场数据/通达信涨停原因/{date}/tdx-limit-reason-6dim.json",
        ROOT / f"raw/04-市场数据/通达信热榜/{date}/tdx-hot-top100.md",
        ROOT / f"raw/04-市场数据/通达信成交额排名/{date}/tdx-成交额Top100.md",
        ROOT / f"wiki/09-统计与进化/{date}-复盘.md",
        ROOT / f"wiki/06-持仓与资金管理/{date}-交割单.md",
        ROOT / f"wiki/07-作战室/{date}-AI上下文包.md",
        ROOT / f"wiki/07-作战室/{date}-作战室候选票评分表.md",
        ROOT / f"wiki/09-统计与进化/{date}-作战室候选验证回看.md",
    ]
    out: list[dict[str, Any]] = []
    for path in paths:
        out.append({"path": rel(path), "exists": path.exists(), "size": path.stat().st_size if path.exists() else 0})
    return out


def review_quality_status(date: str) -> list[dict[str, Any]]:
    path = ROOT / f"raw/02-每日复盘/{date}-复盘.md"
    text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
    checks = [
        ("交割单与持仓", ["今日实际交易", "持仓与资金"]),
        ("用户口述买卖理由", ["用户买入理由", "用户口述原文"]),
        ("指数与市场广度", ["指数", "涨停跌停", "市场广度"]),
        ("涨停全景与首板连板", ["涨停全景", "首板", "连板天梯"]),
        ("板块强度与主线", ["板块涨幅", "板块跌幅", "主线"]),
        ("热榜与成交额", ["通达信热榜", "同花顺热榜", "成交额"]),
        ("龙虎榜重点票", ["龙虎榜", "席位"]),
        ("持仓公告新闻核验", ["公告", "问询", "催化核验"]),
        ("D+验证表", ["D+验证", "成功标准", "失败标准"]),
    ]
    results: list[dict[str, Any]] = []
    for label, keywords in checks:
        hits = [keyword for keyword in keywords if keyword in text]
        results.append({"label": label, "ok": len(hits) >= min(2, len(keywords)), "hits": hits})
    return results


def render_report(
    date: str,
    steps: list[dict[str, Any]],
    files: list[dict[str, Any]],
    review_checks: list[dict[str, Any]],
    package: dict[str, Any],
    sync: dict[str, Any],
) -> str:
    ok_steps = sum(1 for item in steps if item["status"] == "ok")
    warn_steps = sum(1 for item in steps if item["status"] == "warn")
    fail_steps = sum(1 for item in steps if item["status"] == "fail")
    missing = [item for item in files if not item["exists"]]
    review_missing = [item for item in review_checks if not item["ok"]]
    lines = [
        f"# {date} 每日闭环运行报告",
        "",
        f"- 生成时间：{now_text()}",
        f"- 步骤：OK {ok_steps} / WARN {warn_steps} / FAIL {fail_steps}",
        f"- 必要文件缺失：{len(missing)}",
        f"- 复盘质量缺项：{len(review_missing)}",
        f"- Mac本机闭环归档：`{package.get('path', '')}`，文件数 {package.get('files', 0)}",
        "",
        "## 步骤结果",
        "",
        "| 步骤 | 状态 | 返回码 |",
        "|---|---|---:|",
    ]
    for item in steps:
        lines.append(f"| {item['label']} | {item['status']} | {item['returncode']} |")
    lines.extend(["", "## 必要文件", "", "| 文件 | 状态 | 大小 |", "|---|---|---:|"])
    for item in files:
        lines.append(f"| `{item['path']}` | {'OK' if item['exists'] else '缺失'} | {item['size']} |")
    lines.extend(["", "## 复盘质量验收", "", "| 模块 | 状态 | 命中关键词 |", "|---|---|---|"])
    for item in review_checks:
        lines.append(f"| {item['label']} | {'OK' if item['ok'] else '缺失'} | {', '.join(item['hits'])} |")
    lines.extend(["", "## Syncthing 本机状态", ""])
    lines.append(f"- 已连接设备数：{sync.get('connectedDeviceCount', '')}")
    for folder, state in sync.get("folders", {}).items():
        lines.append(
            f"- {folder}：state={state.get('state')} errors={state.get('errors')}"
        )
    if missing or review_missing:
        lines.extend(["", "## 仍需处理", ""])
        for item in missing:
            lines.append(f"- 缺失：`{item['path']}`")
        for item in review_missing:
            lines.append(f"- 复盘缺项：{item['label']}")
    else:
        lines.extend(["", "## 结论", "", "- Mac 端闭环必要文件齐全。"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run daily closed loop.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--skip-network", action="store_true")
    args = parser.parse_args()

    date = args.date
    month = date[:7]
    steps: list[dict[str, Any]] = []

    steps.append(run_script("市场 RAW 衍生产物补齐", "codex_extract_market_raw_derivatives.py", ["--date", date]))
    steps.append(run_script("盘后主流程", "codex_daily_workflow.py", ["--date", date, "--phase", "postmarket"], allow_fail=True))
    steps.append(run_script("发布交割单与复盘到 WIKI", "codex_publish_daily_raw_to_wiki.py", ["--date", date, "--allow-before-postmarket"]))
    steps.append(run_script("复盘强制发布检查", "codex_review_publish_guard.py", ["--date", date, "--write"], allow_fail=True))
    steps.append(run_script("作战室 D+0 验证", "codex_warroom_validation_pipeline.py", ["--date", date, "--session", "postclose"]))
    steps.append(run_script("作战室 D+自动回填", "codex_warroom_dplus_autofill.py", ["--today", date], allow_fail=True))
    steps.append(run_script("公告事件入库", "codex_register_announcement_events.py", ["--date", date, "--write"], allow_fail=True))
    steps.append(run_script("生成 D+验证任务", "codex_generate_dplus_tasks.py", ["--date", date, "--force"], allow_fail=True))
    steps.append(run_script("D+验证自动回填", "codex_dplus_validation_autofill.py", ["--today", date], allow_fail=True))
    steps.append(run_script("公告事件D+自动回填", "codex_announcement_dplus_autofill.py", ["--today", date], allow_fail=True))
    steps.append(run_script("公告事件月度统计", "codex_announcement_monthly_stats.py", ["--month", month, "--write"], allow_fail=True))
    steps.append(run_script("实时催化雷达", "codex_realtime_catalyst_radar.py", ["--date", date, "--lookback-hours", "18"]))
    steps.append(run_script("月度 RAW 覆盖审计", "codex_audit_raw_coverage.py", ["--month", month, "--as-of", date]))
    steps.append(run_script("月度交易统计", "codex_build_monthly_trade_stats.py", ["--month", month, "--as-of", date]))
    steps.append(run_script("错误账本", "codex_build_error_ledger.py", ["--month", month], allow_fail=True))
    steps.append(run_script("刷新 AI 上下文", "codex_update_ai_context.py", ["--date", date]))

    files = required_file_status(date)
    review_checks = review_quality_status(date)
    package = build_local_archive_package(date)
    sync = {"ok": False, "skipped": True} if args.skip_network else syncthing_scan_and_status()

    report = render_report(date, steps, files, review_checks, package, sync)
    report_path = REPORT_DIR / f"{date}-每日闭环运行报告.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    payload = {
        "ok": not any(step["status"] == "fail" for step in steps),
        "date": date,
        "report": rel(report_path),
        "steps": [{"label": x["label"], "status": x["status"], "returncode": x["returncode"]} for x in steps],
        "missingRequiredFiles": [x for x in files if not x["exists"]],
        "missingReviewQuality": [x for x in review_checks if not x["ok"]],
        "macLocalArchivePackage": package,
        "syncthing": sync,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
