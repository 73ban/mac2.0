#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path("/Users/qixinchaye/wiki/73神话")
TZ = dt.timezone(dt.timedelta(hours=8))


def now_cn() -> dt.datetime:
    return dt.datetime.now(TZ)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def iter_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return [p for p in path.rglob("*") if p.is_file()]


def file_time(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, TZ).isoformat(timespec="seconds")


def source_status(name: str, path: Path, *, now: dt.datetime, required: bool = True) -> dict[str, Any]:
    files = iter_files(path)
    ts = now.timestamp()
    last_6h = [p for p in files if ts - p.stat().st_mtime <= 6 * 3600]
    last_24h = [p for p in files if ts - p.stat().st_mtime <= 24 * 3600]
    latest = max(files, key=lambda p: p.stat().st_mtime, default=None)
    ok = bool(last_24h) if required else True
    status = "ok" if ok else "缺当日/近24小时写入"
    if not path.exists():
        status = "目录缺失" if required else "目录缺失-非硬问题"
    return {
        "源": name,
        "路径": rel(path),
        "目录存在": path.exists(),
        "文件数": len(files),
        "近6小时": len(last_6h),
        "近24小时": len(last_24h),
        "最新文件": rel(latest) if latest else "",
        "最新时间": file_time(latest) if latest else "",
        "状态": status,
    }


def longxia_not_due_status(task_name: str, date: str, now: dt.datetime) -> str:
    config = read_json(ROOT / ".system/longxia-task-schedule.json")
    delay = int(config.get("syncDelayMinutes") or 10)
    for task in config.get("tasks") or []:
        if task.get("name") != task_name:
            continue
        hour, minute = [int(x) for x in str(task.get("time")).split(":", 1)]
        check_at = dt.datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=TZ, hour=hour, minute=minute) + dt.timedelta(minutes=delay)
        if now < check_at:
            return f"未到龙虾验收时间{check_at.strftime('%H:%M')}"
        return ""
    return ""


def scheduled_source_status(name: str, task_name: str, path: Path, *, date: str, now: dt.datetime, required: bool = True) -> dict[str, Any]:
    row = source_status(name, path, now=now, required=required)
    not_due = longxia_not_due_status(task_name, date, now)
    if row["状态"] != "ok" and not_due:
        row["状态"] = not_due
    return row


def latest_error_file(path: Path) -> dict[str, str]:
    files = sorted(path.glob("*error*.md"), key=lambda p: p.stat().st_mtime, reverse=True) if path.exists() else []
    if not files:
        return {}
    text = files[0].read_text(encoding="utf-8", errors="replace").strip()
    return {"路径": rel(files[0]), "修改时间": file_time(files[0]), "摘要": text[:300]}


def launchctl_status(labels: list[str]) -> list[dict[str, str]]:
    try:
        out = subprocess.run(["launchctl", "list"], check=False, capture_output=True, text=True).stdout
    except Exception as exc:
        return [{"任务": "launchctl", "状态": f"读取失败：{exc}"}]
    rows = []
    for label in labels:
        hit = ""
        for line in out.splitlines():
            if label in line:
                hit = line.strip()
                break
        rows.append({"任务": label, "状态": hit or "未加载"})
    return rows


def hotlist_counts(date: str) -> dict[str, Any]:
    tgb = read_json(ROOT / f"raw/04-市场数据/热榜/{date}/淘股吧热榜100-latest.json")
    ths = read_json(ROOT / f"raw/04-市场数据/同花顺热榜/{date}/ths-hot-top100.json")
    merged = read_json(ROOT / f"raw/04-市场数据/三榜热度合并/{date}/三榜热度合并.json")
    return {
        "淘股吧": {
            "股票热榜": len(tgb.get("股票热榜") or []),
            "热门讨论": len(tgb.get("热门讨论100") or []),
            "话题榜": len(tgb.get("话题榜") or []),
            "实盘赛热门买入": len(tgb.get("实盘赛热门买入") or []),
            "社交热帖": len(tgb.get("实盘赛社交热帖") or []),
            "热门个股详情TopN": len(tgb.get("热门个股详情TopN") or []),
        },
        "同花顺": {"Top100": len(ths.get("rows") or ths.get("data") or [])},
        "三榜合并": {
            "合并股票": len(merged.get("股票") or []),
            "三榜共振": sum(
                1
                for row in (merged.get("股票") or [])
                if row.get("同花顺排名") and row.get("通达信排名") and row.get("淘股吧排名")
            ),
        },
    }


def build(date: str) -> dict[str, Any]:
    now = now_cn()
    cloud = read_json(ROOT / ".system/cloud-data-connectors-health.json")
    werss = read_json(ROOT / ".system/werss-health.json")
    data_health = read_json(ROOT / ".system/data-interface-health.json")
    is_trade_day = bool(data_health.get("是否交易日"))

    sources = [
        source_status("WeRSS/公众号RAW", ROOT / "raw/05-研报新闻/公众号", now=now),
        source_status("财联社CS财经", ROOT / "raw/05-研报新闻/财联社/CS财经", now=now),
        scheduled_source_status("公告RAW", "每日公告+候选池", ROOT / "raw/05-研报新闻/公告" / date, date=date, now=now, required=is_trade_day),
        source_status("同花顺热榜Top100", ROOT / f"raw/04-市场数据/同花顺热榜/{date}", now=now),
        source_status("淘股吧热榜/话题/实盘热帖", ROOT / f"raw/04-市场数据/热榜/{date}", now=now),
        source_status("三榜热度合并", ROOT / f"raw/04-市场数据/三榜热度合并/{date}", now=now),
        source_status("淘股吧实盘赛样本", ROOT / f"raw/09-短线知识/淘股吧实盘赛/{date}", now=now),
        source_status("截图OCR", ROOT / f"raw/08-截图/飞书图片/{date[:4]}/{date[5:7]}/{date[8:10]}", now=now, required=False),
        scheduled_source_status("通达信热榜", "通达信热榜TOP100", ROOT / f"raw/04-市场数据/通达信热榜/{date}", date=date, now=now, required=is_trade_day),
        source_status("tdxrs竞价快照", ROOT / f"raw/04-市场数据/tdxrs竞价快照/{date}", now=now, required=is_trade_day),
        source_status("东方财富全市场快照", ROOT / f"raw/04-市场数据/东方财富/{date}", now=now, required=False),
    ]

    optional = cloud.get("optionalResults") or {}
    optional_failures = [
        {"任务": name, "错误": item.get("error") or item.get("stderr") or item.get("stdout") or "未给出错误"}
        for name, item in optional.items()
        if item.get("ok") is False
    ]
    hard_issues = []
    for row in sources:
        if row["状态"] not in ("ok", "目录缺失-非硬问题") and not str(row["状态"]).startswith("未到龙虾验收时间"):
            hard_issues.append(f"{row['源']}：{row['状态']}")
    cloud_required_results = cloud.get("results") or {}
    cloud_required_failures = [
        name
        for name, item in cloud_required_results.items()
        if item.get("ok") is False and not item.get("skipped")
    ]
    if cloud and not cloud.get("ok") and cloud_required_failures:
        hard_issues.append("云数据连接器主链失败：" + "、".join(cloud_required_failures))

    conclusions = []
    if not hard_issues:
        if is_trade_day:
            conclusions.append("核心RAW写入链路当前可用；交易日专属通达信/公告等任务按龙虾定时表+10分钟验收，未到点不按硬故障处理。")
        else:
            conclusions.append("核心RAW写入链路当前可用；今天是非交易日，交易日专属通达信/tdxrs/公告缺当日文件不按硬故障处理。")
    else:
        conclusions.append("存在需要处理的RAW硬问题：" + "；".join(hard_issues))
    if optional_failures:
        conclusions.append("云数据连接器为 yellow，原因是可选项失败，不是WeRSS/财联社主链失败。")
    if werss.get("source_mode") == "local-direct":
        conclusions.append("公众号链路当前走 local-direct；旧远端WeRSS API已停用，本地URL种子和本地缓存仍在写RAW。")

    return {
        "schema": "73wiki-raw-ingest-health-dashboard-v1",
        "日期": date,
        "生成时间": now.isoformat(timespec="seconds"),
        "是否交易日": is_trade_day,
        "结论": conclusions,
        "硬问题": hard_issues,
        "源状态": sources,
        "热榜计数": hotlist_counts(date),
        "健康文件": {
            "cloud-data-connectors": {
                "ok": cloud.get("ok"),
                "statusColor": cloud.get("statusColor"),
                "startedAt": cloud.get("startedAt"),
                "finishedAt": cloud.get("finishedAt"),
            },
            "werss": {
                "checked_at": werss.get("checked_at"),
                "source_mode": werss.get("source_mode"),
                "legacy_werss_api": werss.get("legacy_werss_api"),
                "seed_count": ((werss.get("url_seed_capture") or {}).get("seed_count")),
                "seen_count": ((werss.get("url_seed_capture") or {}).get("seen_count")),
                "last_run": ((werss.get("url_seed_capture") or {}).get("last_run")),
                "wx_daemon_status": ((werss.get("wx_cli_cache") or {}).get("daemon_status") or {}).get("stdout"),
            },
            "data-interface": {
                "生成时间": data_health.get("生成时间"),
                "登记表版本": data_health.get("登记表版本"),
            },
        },
        "可选失败": optional_failures,
        "东方财富错误": latest_error_file(ROOT / f"raw/04-市场数据/东方财富/{date}"),
        "LaunchAgent": launchctl_status([
            "com.73wiki.cloud-data-connectors",
            "com.73wiki.local-werss",
            "com.73wiki.data-interface-health",
            "com.73wiki.taoguba-hotlist",
            "com.73wiki.taoguba-contest-pipeline",
            "com.73wiki.paddleocr-raw08",
            "com.73wiki.eastmoney-market-snapshot",
            "com.73wiki.daily-master-dashboard",
        ]),
    }


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in row) + " |")
    return "\n".join(out)


def write_md(path: Path, data: dict[str, Any]) -> None:
    lines = [
        f"# {data['日期']} RAW写入链路体检",
        "",
        f"- 生成时间：{data['生成时间']}",
        f"- 是否交易日：{'是' if data['是否交易日'] else '否'}",
        "",
        "## 结论",
        "",
    ]
    lines.extend(f"- {item}" for item in data["结论"])
    lines += ["", "## 源状态", ""]
    lines.append(md_table(
        ["源", "状态", "近6小时", "近24小时", "文件数", "最新时间", "最新文件"],
        [[r["源"], r["状态"], r["近6小时"], r["近24小时"], r["文件数"], r["最新时间"], r["最新文件"]] for r in data["源状态"]],
    ))
    lines += ["", "## 热榜计数", "", "```json", json.dumps(data["热榜计数"], ensure_ascii=False, indent=2), "```"]
    lines += ["", "## 健康文件", "", "```json", json.dumps(data["健康文件"], ensure_ascii=False, indent=2), "```"]
    lines += ["", "## 可选失败", ""]
    if data["可选失败"]:
        lines.append(md_table(["任务", "错误"], [[x["任务"], x["错误"]] for x in data["可选失败"]]))
    else:
        lines.append("- 无。")
    if data["东方财富错误"]:
        lines += ["", "## 东方财富备用接口错误", "", "```text", data["东方财富错误"]["摘要"], "```"]
    lines += ["", "## LaunchAgent", ""]
    lines.append(md_table(["任务", "状态"], [[x["任务"], x["状态"]] for x in data["LaunchAgent"]]))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=now_cn().date().isoformat())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    data = build(args.date)
    if args.write:
        wiki_dir = ROOT / "wiki/09-统计与进化"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        json_path = wiki_dir / f"{args.date}-RAW写入链路体检.json"
        md_path = wiki_dir / f"{args.date}-RAW写入链路体检.md"
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        write_md(md_path, data)
        system_path = ROOT / ".system/raw-ingest-health-dashboard.json"
        system_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(str(md_path))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
