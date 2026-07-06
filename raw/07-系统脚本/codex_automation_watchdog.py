#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Watch scheduled data/learning jobs and alert when automation stalls."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SYSTEM = ROOT / ".system"
WIKI_STATS = ROOT / "wiki" / "09-统计与进化"
PENDING = SYSTEM / "feishu-notify-pending"
STATE = SYSTEM / "automation-watchdog-state.json"


@dataclass
class CheckResult:
    name: str
    level: str
    status: str
    detail: str
    latest_path: str = ""
    latest_time: str = ""


def now() -> datetime:
    return datetime.now()


def now_text() -> str:
    return now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def run_cmd(args: list[str], timeout: int = 30) -> dict[str, Any]:
    try:
        proc = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=timeout)
        return {"ok": proc.returncode == 0, "status": proc.returncode, "stdout": proc.stdout[-3000:], "stderr": proc.stderr[-3000:]}
    except Exception as exc:
        return {"ok": False, "status": None, "stdout": "", "stderr": str(exc)}


def latest_file(root: Path, suffixes: set[str] | None = None) -> Path | None:
    if not root.exists():
        return None
    best: Path | None = None
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        if best is None or path.stat().st_mtime > best.stat().st_mtime:
            best = path
    return best


def freshness_check(name: str, root: Path, max_age_minutes: int, *, required: bool = True, suffixes: set[str] | None = None) -> CheckResult:
    latest = latest_file(root, suffixes=suffixes)
    if latest is None:
        level = "critical" if required else "warning"
        return CheckResult(name, level, "missing", f"目录无可用产物：{rel(root)}")
    mtime = datetime.fromtimestamp(latest.stat().st_mtime)
    age = now() - mtime
    if age <= timedelta(minutes=max_age_minutes):
        return CheckResult(name, "ok", "ok", f"最新产物 {int(age.total_seconds() // 60)} 分钟前更新", rel(latest), mtime.strftime("%Y-%m-%d %H:%M:%S"))
    level = "critical" if required else "warning"
    return CheckResult(name, level, "stale", f"最新产物已 {int(age.total_seconds() // 60)} 分钟未更新，阈值 {max_age_minutes} 分钟", rel(latest), mtime.strftime("%Y-%m-%d %H:%M:%S"))


def exact_file_freshness_check(name: str, path: Path, max_age_minutes: int, *, required: bool = True) -> CheckResult:
    if not path.exists():
        level = "critical" if required else "warning"
        return CheckResult(name, level, "missing", f"固定产物不存在：{rel(path)}")
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    age = now() - mtime
    if age <= timedelta(minutes=max_age_minutes):
        return CheckResult(name, "ok", "ok", f"固定产物 {int(age.total_seconds() // 60)} 分钟前更新", rel(path), mtime.strftime("%Y-%m-%d %H:%M:%S"))
    level = "critical" if required else "warning"
    return CheckResult(name, level, "stale", f"固定产物已 {int(age.total_seconds() // 60)} 分钟未更新，阈值 {max_age_minutes} 分钟", rel(path), mtime.strftime("%Y-%m-%d %H:%M:%S"))


def launchctl_checks() -> list[CheckResult]:
    labels = {
        "云数据连接器15分钟总线": "com.73wiki.cloud-data-connectors",
        "数据接口健康报告": "com.73wiki.data-interface-health",
        "PaddleOCR截图识别": "com.73wiki.paddleocr-raw08",
        "淘股吧热榜": "com.73wiki.taoguba-hotlist",
        "淘股吧实盘赛": "com.73wiki.taoguba-contest-pipeline",
        "韭研公社网页": "com.73wiki.jiuyangongshe-web-fetch",
        "短线模式词典扫描": "com.73wiki.shortline-mode-dictionary",
        "动态作战室Top5": "com.73wiki.dynamic-warroom-top5",
        "WeRSS本地服务": "com.73wiki.local-werss",
        "飞书桥": "com.qixinchaye.feishu-codex-bridge",
    }
    results: list[CheckResult] = []
    uid = run_cmd(["id", "-u"], timeout=5).get("stdout", "").strip() or "501"
    for name, label in labels.items():
        proc = subprocess.run(["launchctl", "print", f"gui/{uid}/{label}"], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if proc.returncode != 0:
            results.append(CheckResult(name, "critical", "not_loaded", f"{label} 未加载"))
            continue
        state = ""
        last_exit = ""
        for line in proc.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("state ="):
                state = stripped.split("=", 1)[1].strip()
            if stripped.startswith("last exit code ="):
                last_exit = stripped.split("=", 1)[1].strip()
        detail = f"{label} 已加载"
        if state:
            detail += f"；state={state}"
        if last_exit:
            detail += f"；last_exit={last_exit}"
        results.append(CheckResult(name, "ok", "loaded", detail))
    return results


def run_sub_healthchecks() -> list[CheckResult]:
    results: list[CheckResult] = []
    ocr = run_cmd(["/usr/bin/python3", "raw/07-系统脚本/codex_ocr_healthcheck.py", "--write"], timeout=60)
    if not ocr["ok"]:
        results.append(CheckResult("OCR健康检查", "critical", "failed", (ocr.get("stderr") or ocr.get("stdout") or "")[:500]))
    werss = run_cmd(["/usr/bin/python3", "raw/07-系统脚本/codex_werss_healthcheck.py", "--output", ".system/werss-health.json"], timeout=60)
    if not werss["ok"]:
        results.append(CheckResult("WeRSS健康检查", "warning", "failed", (werss.get("stderr") or werss.get("stdout") or "")[:500]))
    return results


def ocr_result() -> CheckResult:
    data = read_json(SYSTEM / "ocr-health.json", {})
    if not data:
        return CheckResult("PaddleOCR模型/侧车", "critical", "missing_health", ".system/ocr-health.json 不存在或不可读")
    paddle = data.get("paddleocr") or {}
    sidecars = data.get("raw08Sidecars") or {}
    if not data.get("ok") or not paddle.get("ok"):
        return CheckResult("PaddleOCR模型/侧车", "critical", "failed", str(data)[:500])
    missing = int(sidecars.get("missingSidecarCount") or 0)
    if missing:
        return CheckResult("PaddleOCR模型/侧车", "critical", "missing_sidecars", f"有 {missing} 张图片缺 OCR sidecar")
    return CheckResult("PaddleOCR模型/侧车", "ok", "ok", paddle.get("status") or "PaddleOCR可用")


def cloud_health_result() -> CheckResult:
    data = read_json(SYSTEM / "cloud-data-connectors-health.json", {})
    if not data:
        return CheckResult("云数据连接器健康文件", "warning", "missing", "cloud-data-connectors-health.json 不存在")
    if data.get("ok"):
        return CheckResult("云数据连接器健康文件", "ok", "ok", f"statusColor={data.get('statusColor')} finishedAt={data.get('finishedAt')}")
    status_color = str(data.get("statusColor") or "").lower()
    module_ok = ((data.get("summary") or {}).get("moduleOk") or {})
    hard_failed = [name for name in ("csCailian", "thsHotlist", "rawQueueIngest", "catalystRadar") if module_ok.get(name) is False]
    if status_color in {"yellow", "degraded"} and not hard_failed:
        alerts = data.get("alerts") or []
        detail = "；".join(str(item.get("message") or item) for item in alerts[:3]) or "局部降级"
        return CheckResult("云数据连接器健康文件", "warning", "degraded", f"statusColor={data.get('statusColor')} {detail}")
    return CheckResult("云数据连接器健康文件", "critical", "failed", f"statusColor={data.get('statusColor')} hardFailed={','.join(hard_failed) or '-'} error={data.get('error')}")


def werss_probe_result() -> CheckResult:
    data = read_json(SYSTEM / "werss-health.json", {})
    if not data:
        return CheckResult("WeRSS/微信本地探针", "warning", "missing", ".system/werss-health.json 不存在")
    latest = data.get("latest_raw_files") or []
    if latest:
        return CheckResult("WeRSS/微信本地探针", "ok", "raw_writing", f"公众号RAW仍在更新；最新 {latest[0].get('mtime')} {latest[0].get('path')}")
    wx = ((data.get("wx_cli_cache") or {}).get("biz_articles_probe") or {})
    if wx.get("ok") is False:
        return CheckResult("WeRSS/微信本地探针", "warning", "probe_failed", "wx-daemon备用探针失败，但需结合公众号RAW新鲜度判断")
    return CheckResult("WeRSS/微信本地探针", "warning", "unknown", "无 latest_raw_files")


def time_based_checks(date: str) -> list[CheckResult]:
    hhmm = int(now().strftime("%H%M"))
    checks = [
        freshness_check("WeRSS/公众号RAW写入", ROOT / "raw/05-研报新闻/公众号", 360, suffixes={".md"}),
        freshness_check("财联社CS财经", ROOT / "raw/05-研报新闻/财联社/CS财经", 180, suffixes={".md"}),
        freshness_check("同花顺热榜Top100", ROOT / f"raw/04-市场数据/同花顺热榜/{date}", 180, suffixes={".json", ".md"}),
        freshness_check("三榜热度合并", ROOT / f"raw/04-市场数据/三榜热度合并/{date}", 240, suffixes={".json", ".md"}),
        freshness_check("RAW到Wiki/重要信息产物", ROOT / f"raw/11-Codex分析产物/每日重要信息Top10/{date}", 180, required=False, suffixes={".json", ".md"}),
        exact_file_freshness_check("动态作战室Top5主文件", ROOT / f"raw/11-Codex分析产物/动态作战室/{date}/dynamic-warroom-top5.json", 5, required=False),
        exact_file_freshness_check("盘中一分钟看盘主文件", ROOT / f"raw/11-Codex分析产物/盘中一分钟看盘/{date}/intraday-minute-watch.json", 5, required=False),
        exact_file_freshness_check("盘中一分钟提醒验证", ROOT / f"raw/11-Codex分析产物/盘中一分钟提醒验证/{date}/intraday-alert-validation.json", 10, required=False),
        exact_file_freshness_check("飞书Codex任务收件箱", ROOT / f"raw/10-飞书交易沟通/任务指令/{date}/codex-task-inbox.json", 10, required=False),
        freshness_check("短线模式词典扫描产物", ROOT / f"raw/11-Codex分析产物/短线模式词典/{date}", 90, required=False, suffixes={".json", ".md"}),
        freshness_check("交易模式页面质量检查", ROOT / f"raw/11-Codex分析产物/交易模式质量检查/{date}", 90, required=False, suffixes={".json", ".md"}),
        freshness_check("交易模式归因缺口审计", ROOT / f"raw/11-Codex分析产物/交易模式归因审计/{date}", 90, required=False, suffixes={".json", ".md"}),
        freshness_check("逐笔交易模式归因", ROOT / f"raw/11-Codex分析产物/交易模式逐笔归因/{date}", 90, required=False, suffixes={".json", ".md"}),
        freshness_check("交易模式D+验证", ROOT / f"raw/11-Codex分析产物/交易模式D+验证/{date}", 90, required=False, suffixes={".json", ".md"}),
        freshness_check("大赚大亏日模式归因", ROOT / f"raw/11-Codex分析产物/交易模式大赚大亏日归因/{date}", 90, required=False, suffixes={".json", ".md"}),
        freshness_check("Codex长期运行驾驶舱", ROOT / f"raw/11-Codex分析产物/Codex长期运行驾驶舱/{date}", 90, required=False, suffixes={".json", ".md"}),
    ]
    if hhmm >= 1830:
        checks.append(freshness_check("淘股吧热榜100", ROOT / f"raw/04-市场数据/热榜/{date}", 180, suffixes={".json", ".md"}))
    else:
        checks.append(CheckResult("淘股吧热榜100", "ok", "not_due", "18:00/22:00任务未到首次执行窗口"))
    return checks


def build(date: str) -> dict[str, Any]:
    checks: list[CheckResult] = []
    checks.extend(run_sub_healthchecks())
    checks.extend(launchctl_checks())
    checks.append(ocr_result())
    checks.append(cloud_health_result())
    checks.append(werss_probe_result())
    checks.extend(time_based_checks(date))
    critical = [x for x in checks if x.level == "critical"]
    warning = [x for x in checks if x.level == "warning"]
    return {
        "schema": "73wiki-automation-watchdog-v1",
        "date": date,
        "generatedAt": now_text(),
        "status": "critical" if critical else "warning" if warning else "ok",
        "criticalCount": len(critical),
        "warningCount": len(warning),
        "checks": [x.__dict__ for x in checks],
    }


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 自动化任务Watchdog",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        f"- 总状态：{payload['status']}",
        f"- 硬故障：{payload['criticalCount']}；软告警：{payload['warningCount']}",
        "",
        "| 级别 | 检查项 | 状态 | 说明 | 最新时间 | 最新产物 |",
        "|---|---|---|---|---|---|",
    ]
    for row in payload["checks"]:
        lines.append(
            f"| {row['level']} | {row['name']} | {row['status']} | {str(row['detail']).replace('|', '/')} | {row.get('latest_time','')} | `{row.get('latest_path','')}` |"
        )
    lines.extend(
        [
            "",
            "## 处理原则",
            "",
            "- critical：主链可能罢工，写飞书待处理，并优先修复。",
            "- warning：备用探针或非核心链路异常，写报告，不阻塞主流程。",
            "- ok：只记录，不打扰。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_notify(payload: dict[str, Any]) -> str:
    bad = [x for x in payload["checks"] if x["level"] in {"critical", "warning"}]
    lines = [
        "【自动化任务Watchdog告警】",
        f"时间：{payload['generatedAt']}",
        f"总状态：{payload['status']}；硬故障 {payload['criticalCount']}；软告警 {payload['warningCount']}",
        "性质：系统告警，不是交易判断。无需回复；我会按 critical 优先级处理。",
        "",
    ]
    for idx, row in enumerate(bad[:12], start=1):
        lines.append(f"{idx}. [{row['level']}] {row['name']}：{row['status']}。{row['detail']}")
        if row.get("latest_path"):
            lines.append(f"   最新产物：{row.get('latest_time')} {row.get('latest_path')}")
    lines.append("")
    lines.append("处理：我会优先处理 critical；warning 用于观察和后续修配置。")
    return "\n".join(lines)


def issue_signature(payload: dict[str, Any]) -> str:
    bad = [f"{x['level']}|{x['name']}|{x['status']}" for x in payload["checks"] if x["level"] in {"critical", "warning"}]
    return "\n".join(sorted(bad))


def write_pending_if_needed(payload: dict[str, Any]) -> dict[str, Any]:
    if payload["status"] == "ok":
        return {"created": False, "reason": "ok"}
    if payload.get("criticalCount", 0) == 0:
        return {"created": False, "reason": "warnings_report_only"}
    state = read_json(STATE, {"lastSignature": "", "lastNotifiedAt": ""})
    sig = issue_signature(payload)
    if sig == state.get("lastSignature"):
        return {"created": False, "reason": "same_signature"}
    PENDING.mkdir(parents=True, exist_ok=True)
    name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-自动化任务Watchdog告警.md"
    path = PENDING / name
    path.write_text(render_notify(payload), encoding="utf-8")
    write_json(STATE, {"lastSignature": sig, "lastNotifiedAt": payload["generatedAt"]})
    return {"created": True, "file": rel(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Automation watchdog for scheduled data jobs.")
    parser.add_argument("--date", default=now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()
    payload = build(args.date)
    notify = {"created": False, "reason": "not_requested"}
    if args.write:
        write_json(SYSTEM / "automation-watchdog.json", payload)
        WIKI_STATS.mkdir(parents=True, exist_ok=True)
        (WIKI_STATS / f"{args.date}-自动化任务Watchdog.md").write_text(render_md(payload), encoding="utf-8")
        if args.notify:
            notify = write_pending_if_needed(payload)
    print(json.dumps({"ok": True, "date": args.date, "status": payload["status"], "critical": payload["criticalCount"], "warning": payload["warningCount"], "notify": notify}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
