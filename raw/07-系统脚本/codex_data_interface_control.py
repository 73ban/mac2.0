#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""73神话数据接口总控。

它负责读取统一登记表，检查本机自动任务、RAW输出和龙虾/老虎事实层交付状态。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from codex_trading_calendar import calendar_note, is_trade_day, trading_day_info


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / ".system/data-interface-registry.json"
HEALTH_JSON = ROOT / ".system/data-interface-health.json"
REPORT_DIR = ROOT / "wiki/09-统计与进化"
SYNCTHING_CONFIG = Path.home() / "Library/Application Support/Syncthing/config.xml"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def expects_trade_day(interface: dict[str, Any]) -> bool:
    text = " ".join(str(interface.get(key, "")) for key in ("频率", "分类", "接口名"))
    markers = ["交易日", "收盘后", "盘中", "竞价", "龙虎榜", "15:06", "09:25", "22:00"]
    if "周日" in text:
        return False
    if "用户提供后" in text or "飞书触发" in text:
        return False
    return any(marker in text for marker in markers)


def waits_for_user(interface: dict[str, Any]) -> bool:
    text = " ".join(str(interface.get(key, "")) for key in ("频率", "分类", "接口名"))
    return "用户提供后" in text or "飞书触发" in text


def optional_weekend_job(interface: dict[str, Any], date: str) -> bool:
    text = " ".join(str(interface.get(key, "")) for key in ("频率", "分类", "接口名"))
    if "周日" not in text:
        return False
    try:
        return datetime.strptime(date, "%Y-%m-%d").weekday() == 6
    except ValueError:
        return False


def fallback_error_exists(interface: dict[str, Any], date: str) -> bool:
    name = str(interface.get("接口名", ""))
    if "东方财富全市场快照" in name:
        return (ROOT / f"raw/04-市场数据/东方财富/{date}/market-snapshot-error.md").exists()
    return False


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def expand_path(text: str, date: str) -> Path:
    value = text.replace("{日期}", date).replace("~", str(Path.home()))
    return ROOT / value if not value.startswith("/") else Path(value)


def path_exists(pattern: str, date: str) -> dict[str, Any]:
    path = expand_path(pattern, date)
    if "*" in str(path):
        matches = list(path.parent.glob(path.name))
        return {
            "路径": pattern,
            "存在": bool(matches),
            "数量": len(matches),
            "样例": [rel(x) for x in matches[:5]],
        }
    return {
        "路径": pattern,
        "存在": path.exists(),
        "大小": path.stat().st_size if path.exists() and path.is_file() else None,
    }


def expected_outputs(interface: dict[str, Any], date: str) -> list[dict[str, Any]]:
    if str(interface.get("接口名", "")) == "截图OCR自动识别":
        ocr_md = sorted((ROOT / "raw/08-截图").rglob("*.ocr.md"))
        ocr_json = sorted((ROOT / "raw/08-截图").rglob("*.ocr.json"))
        index = ROOT / "data/facts/screenshot_ocr_index.jsonl"
        return [
            {"路径": "raw/08-截图/**/*.ocr.md", "存在": bool(ocr_md), "数量": len(ocr_md), "样例": [rel(path) for path in ocr_md[-5:]]},
            {"路径": "raw/08-截图/**/*.ocr.json", "存在": bool(ocr_json), "数量": len(ocr_json), "样例": [rel(path) for path in ocr_json[-5:]]},
            {"路径": "data/facts/screenshot_ocr_index.jsonl", "存在": index.exists(), "大小": index.stat().st_size if index.exists() else None},
        ]

    if str(interface.get("接口名", "")) == "淘股吧热榜100":
        today = datetime.now().strftime("%Y-%m-%d")
        now_hm = int(datetime.now().strftime("%H%M"))
        base = f"raw/04-市场数据/热榜/{date}"
        if date == today and now_hm < 1800:
            return [{"路径": f"{base}/淘股吧热榜100-1800.json/md", "存在": None, "说明": "未到18:00执行时间"}]
        checks = [
            path_exists(f"{base}/淘股吧热榜100-latest.json", date),
            path_exists(f"{base}/淘股吧热榜100-latest.md", date),
        ]
        if date != today or now_hm >= 2200:
            checks.extend(
                [
                    path_exists(f"{base}/淘股吧热榜100-2200.json", date),
                    path_exists(f"{base}/淘股吧热榜100-2200.md", date),
                ]
            )
        return checks

    if str(interface.get("接口名", "")) == "淘股吧实盘赛样本":
        base = ROOT / f"raw/09-短线知识/淘股吧实盘赛/{date}"
        files = sorted([path for path in base.rglob("*") if path.is_file()]) if base.exists() else []
        structured = base / "结构化样本.json"
        source_index = base / "source_index.json"
        return [
            {"路径": f"raw/09-短线知识/淘股吧实盘赛/{date}/", "存在": base.exists(), "数量": len(files), "样例": [rel(path) for path in files[-5:]]},
            {"路径": f"raw/09-短线知识/淘股吧实盘赛/{date}/结构化样本.json", "存在": structured.exists(), "大小": structured.stat().st_size if structured.exists() else None},
            {"路径": f"raw/09-短线知识/淘股吧实盘赛/{date}/source_index.json", "存在": source_index.exists(), "大小": source_index.stat().st_size if source_index.exists() else None},
        ]

    out_dir = interface.get("输出目录", "")
    outputs = interface.get("输出文件", [])
    checks: list[dict[str, Any]] = []
    if not out_dir:
        return checks
    for item in outputs:
        if not isinstance(item, str):
            continue
        if any(token in item for token in ["按栏目", "按公众号", "按URL", "WeRSS内部", "原始xls", "飞书原文"]):
            checks.append({"路径": f"{out_dir}/{item}", "存在": None, "说明": "动态文件，人工看目录"})
            continue
        candidate = f"{out_dir.rstrip('/')}/{item}"
        if "json/md" in candidate:
            checks.append(path_exists(candidate.replace("json/md", "json"), date))
            checks.append(path_exists(candidate.replace("json/md", "md"), date))
        elif ".json" in candidate or ".md" in candidate:
            checks.append(path_exists(candidate, date))
        else:
            checks.append({"路径": candidate, "存在": None, "说明": "动态文件或目录"})
    return checks


def review_publish_checks(date: str, trade_day: bool) -> dict[str, Any]:
    specs = [
        ("交割单RAW", [ROOT / f"raw/01-交割单/{date}/交割单.md", ROOT / f"raw/01-交割单/{date}", ROOT / f"raw/01-交割单/{date}-交割单.md"]),
        ("口述复盘RAW", [ROOT / f"raw/02-每日复盘/{date}-飞书复盘RAW.md", ROOT / f"raw/10-飞书交易沟通/{date[:4]}/{date[5:7]}/{date[8:10]}"]),
        ("每日复盘RAW", [ROOT / f"raw/02-每日复盘/{date}-复盘.md"]),
        ("正式WIKI复盘", [ROOT / f"wiki/09-统计与进化/{date}-复盘.md"]),
        ("正式WIKI交割单", [ROOT / f"wiki/06-持仓与资金管理/{date}-交割单.md"]),
    ]
    checks = []
    for label, paths in specs:
        exists = any(path.is_file() or (path.is_dir() and any(item.is_file() for item in path.iterdir())) for path in paths)
        checks.append({"路径": f"{label}: " + " | ".join(rel(path) for path in paths), "存在": exists})
    missing = [item for item in checks if not item["存在"]]
    if not trade_day:
        status = "非交易日不要求"
    elif missing:
        status = "缺文件"
    else:
        status = "ok"
    return {
        "接口名": "复盘强制发布检查",
        "分类": "发布检查",
        "责任方": "Mac/Codex+用户",
        "状态": "运行中",
        "频率": "交易日盘后强制",
        "输出检查": checks,
        "验收状态": status,
    }


def launchctl_state(label: str) -> dict[str, Any]:
    result = subprocess.run(
        ["launchctl", "print", f"gui/{Path.home().owner() if False else ''}"],
        text=True,
        capture_output=True,
    )
    return {"标签": label, "状态": "未检查", "说明": "使用 --launchctl 由人工检查具体LaunchAgent"}


def inspect_launch_agent(plist: str) -> dict[str, Any]:
    path = Path(plist.replace("~", str(Path.home())))
    label = ""
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="ignore")
        import re
        m = re.search(r"<key>Label</key>\s*<string>([^<]+)</string>", text)
        label = m.group(1) if m else ""
    status = {"配置文件": plist, "存在": path.exists(), "标签": label, "运行状态": "未知"}
    if label:
        uid = subprocess.run(["id", "-u"], text=True, capture_output=True).stdout.strip()
        result = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            text=True,
            capture_output=True,
        )
        status["运行状态"] = "已加载" if result.returncode == 0 else "未加载"
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("state ="):
                    status["当前状态"] = line.split("=", 1)[1].strip()
                elif line.startswith("runs ="):
                    status["运行次数"] = line.split("=", 1)[1].strip()
                elif line.startswith("last exit code ="):
                    status["上次退出"] = line.split("=", 1)[1].strip()
    return status


def syncthing_status() -> dict[str, Any]:
    if not SYNCTHING_CONFIG.exists():
        return {"ok": False, "状态": "未安装或配置不存在", "配置文件": str(SYNCTHING_CONFIG)}
    try:
        root = ET.parse(SYNCTHING_CONFIG).getroot()
        api_key = root.findtext("gui/apikey") or ""
        if not api_key:
            return {"ok": False, "状态": "缺少API Key", "配置文件": str(SYNCTHING_CONFIG)}

        def request(path: str) -> Any:
            req = urllib.request.Request(
                f"http://127.0.0.1:8384{path}",
                headers={"X-API-Key": api_key},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode("utf-8") or "{}")

        connections = request("/rest/system/connections")
        folders = request("/rest/config/folders")
        device_states = connections.get("connections", {}) if isinstance(connections, dict) else {}
        connected = [
            {"设备": device, "地址": state.get("address", "")}
            for device, state in device_states.items()
            if state.get("connected")
        ]
        folder_rows = []
        if isinstance(folders, list):
            for folder in folders:
                folder_rows.append(
                    {
                        "id": folder.get("id"),
                        "路径": folder.get("path"),
                        "类型": folder.get("type"),
                        "暂停": folder.get("paused", False),
                    }
                )
        return {
            "ok": True,
            "状态": "运行中",
            "已连接设备数": len(connected),
            "已连接设备": connected,
            "共享目录数": len(folder_rows),
            "共享目录": folder_rows,
        }
    except Exception as error:
        return {"ok": False, "状态": "连接失败", "错误": str(error)}


def build_status(date: str) -> dict[str, Any]:
    registry = load_registry()
    trade_info = trading_day_info(date)
    trade_day = bool(trade_info["isTradeDay"])
    tasks = []
    for task in registry.get("自动任务", []):
        item = dict(task)
        plist = str(task.get("配置文件", ""))
        if plist.endswith(".plist"):
            item["LaunchAgent状态"] = inspect_launch_agent(plist)
        tasks.append(item)

    interfaces = []
    for interface in registry.get("接口", []):
        checks = expected_outputs(interface, date)
        required = [x for x in checks if x.get("存在") is not None]
        ok_count = sum(1 for x in required if x.get("存在"))
        status = "待人工看目录"
        if required and waits_for_user(interface):
            status = "等待用户提供"
        elif required and fallback_error_exists(interface, date):
            status = "备用接口错误-不阻塞"
        elif required and optional_weekend_job(interface, date):
            status = "周日任务待补齐"
        elif required and (not trade_day and expects_trade_day(interface)):
            status = "非交易日不要求"
        elif checks and any("未到" in str(x.get("说明", "")) for x in checks):
            status = "未到执行时间"
        elif required:
            status = "ok" if ok_count == len(required) else "缺文件"
        interfaces.append(
            {
                "接口名": interface.get("接口名"),
                "分类": interface.get("分类"),
                "责任方": interface.get("责任方"),
                "状态": interface.get("状态"),
                "频率": interface.get("频率"),
                "输出检查": checks,
                "验收状态": status,
            }
        )
    interfaces.append(review_publish_checks(date, trade_day))

    return {
        "生成时间": now_text(),
        "检查日期": date,
        "是否交易日": trade_day,
        "交易日信息": trade_info,
        "交易日判断口径": calendar_note(date),
        "登记表版本": registry.get("版本"),
        "自动任务": tasks,
        "接口状态": interfaces,
        "Syncthing状态": syncthing_status(),
    }


def render_md(status: dict[str, Any]) -> str:
    interfaces = status["接口状态"]
    mac_auto = [x for x in interfaces if "Mac" in str(x.get("责任方", ""))]
    fact_layer = [x for x in interfaces if "龙虾" in str(x.get("责任方", "")) or "老虎" in str(x.get("责任方", ""))]
    ok_items = [x for x in interfaces if x.get("验收状态") == "ok"]
    missing_items = [x for x in interfaces if x.get("验收状态") == "缺文件"]
    non_blocking = [x for x in interfaces if x.get("验收状态") in {"非交易日不要求", "等待用户提供", "备用接口错误-不阻塞", "周日任务待补齐", "未到执行时间"}]
    lines = [
        f"# {status['检查日期']} 数据接口运行总控报告",
        "",
        f"- 生成时间：{status['生成时间']}",
        f"- 登记表版本：{status['登记表版本']}",
        f"- 是否交易日：{status.get('是否交易日')}",
        f"- 交易日判断口径：{status.get('交易日判断口径')}",
        "",
        "## 数据源总控看板",
        "",
        "| 分组 | 数量 | 说明 |",
        "|---|---:|---|",
        f"| Mac自动 | {len(mac_auto)} | 本机 LaunchAgent/Codex 脚本负责 |",
        f"| 龙虾/老虎事实层 | {len(fact_layer)} | 按既定分工写 RAW，Mac 本机验收和分析 |",
        f"| 今日已到 | {len(ok_items)} | 固定输出检查通过 |",
        f"| 今日缺失 | {len(missing_items)} | 需要补 RAW 或排查任务 |",
        f"| 不阻塞 | {len(non_blocking)} | 非交易日、用户触发、备用错误或动态目录 |",
        "",
        "## 自动任务",
        "",
        "| 任务 | 状态 | 频率 | 执行入口 | LaunchAgent |",
        "|---|---|---|---|---|",
    ]
    for task in status["自动任务"]:
        la = task.get("LaunchAgent状态") or {}
        lines.append(
            f"| {task.get('任务名','')} | {task.get('状态','')} | {task.get('频率','')} | `{task.get('执行入口','')}` | {la.get('运行状态','')} {la.get('当前状态','')} |"
        )

    lines += [
        "",
        "## 接口状态",
        "",
        "| 接口 | 分类 | 责任方 | 当前状态 | 验收 | 频率 |",
        "|---|---|---|---|---|---|",
    ]
    for item in status["接口状态"]:
        lines.append(
            f"| {item.get('接口名','')} | {item.get('分类','')} | {item.get('责任方','')} | {item.get('状态','')} | {item.get('验收状态','')} | {item.get('频率','')} |"
        )

    sync = status.get("Syncthing状态") or {}
    lines += [
        "",
        "## Syncthing 状态",
        "",
        f"- 状态：{sync.get('状态')}",
        f"- 已连接设备数：{sync.get('已连接设备数', '')}",
        f"- 共享目录数：{sync.get('共享目录数', '')}",
    ]
    if sync.get("错误"):
        lines.append(f"- 错误：{sync.get('错误')}")
    for folder in sync.get("共享目录", [])[:20]:
        lines.append(f"- {folder.get('id')}：{folder.get('类型')}，paused={folder.get('暂停')}，`{folder.get('路径')}`")

    lines += ["", "## 缺文件明细", ""]
    missing = 0
    for item in status["接口状态"]:
        if item.get("验收状态") in {"非交易日不要求", "等待用户提供", "备用接口错误-不阻塞", "周日任务待补齐", "未到执行时间"}:
            continue
        for check in item.get("输出检查", []):
            if check.get("存在") is False:
                missing += 1
                lines.append(f"- {item['接口名']}：`{check.get('路径')}`")
    if missing == 0:
        lines.append("- 未发现明确缺失的固定文件。动态目录仍按接口规则人工抽查。")

    lines += [
        "",
        "## 使用规则",
        "",
        "- Mac自动接口缺文件，先看对应 LaunchAgent 和 `.system/logs/`。",
        "- 龙虾/老虎事实层接口缺文件，按分工补 RAW；Mac 只验收、归档和分析，不在分析层伪造。",
        "- RAW 到齐后，再跑盘后闭环和 WIKI 发布。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="73神话数据接口总控")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    status = build_status(args.date)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if args.write:
        HEALTH_JSON.parent.mkdir(parents=True, exist_ok=True)
        HEALTH_JSON.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report = REPORT_DIR / f"{args.date}-数据接口运行总控报告.md"
        report.write_text(render_md(status), encoding="utf-8")
        print(f"written {rel(HEALTH_JSON)}")
        print(f"written {rel(report)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
