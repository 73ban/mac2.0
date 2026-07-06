#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path("/Users/qixinchaye/wiki/73神话")
TZ = dt.timezone(dt.timedelta(hours=8))


def today_cn() -> str:
    return dt.datetime.now(TZ).date().isoformat()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"_bad_line": line[:200]})
    return rows


def file_status(rel: str) -> dict:
    path = ROOT / rel
    return {
        "路径": rel,
        "存在": path.exists(),
        "大小": path.stat().st_size if path.exists() else 0,
        "修改时间": dt.datetime.fromtimestamp(path.stat().st_mtime, TZ).isoformat(timespec="seconds") if path.exists() else "",
    }


def extract_yaml_date(text: str) -> str:
    match = re.search(r"(?m)^\s*date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\s*$", text)
    if match:
        return match.group(1)
    match = re.search(r"(?m)^#\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", text)
    return match.group(1) if match else ""


def pinned_pages_status() -> tuple[list[dict], list[dict]]:
    context = load_json(ROOT / ".system/current-ai-context.json")
    rows = []
    for item in context.get("pinnedPages") or []:
        path = item.get("path") or ""
        status = file_status(path)
        status["标题"] = item.get("title") or ""
        status["必读"] = bool(item.get("required"))
        rows.append(status)
    missing = [row for row in rows if row["必读"] and not row["存在"]]
    return rows, missing


def validation_summary(date: str) -> dict:
    files = {
        "通用D+": ROOT / "data/facts/dplus_validation_results.jsonl",
        "作战室预测": ROOT / "data/facts/warroom_candidate_predictions.jsonl",
        "作战室D+0结果": ROOT / "data/facts/warroom_candidate_validation_results.jsonl",
        "作战室D+结果": ROOT / "data/facts/warroom_candidate_dplus_validation_results.jsonl",
        "飞书校准": ROOT / "data/facts/feishu_calibration_validation_results.jsonl",
        "公告事件": ROOT / "data/facts/announcement_event_validation_results.jsonl",
    }
    summary = {}
    for name, path in files.items():
        rows = load_jsonl(path)
        statuses = Counter(str(row.get("status") or row.get("decision") or row.get("node") or "unknown") for row in rows)
        summary[name] = {"路径": str(path.relative_to(ROOT)), "样本数": len(rows), "状态分布": dict(statuses)}

    predictions = load_jsonl(files["作战室预测"])
    results = load_jsonl(files["作战室D+结果"])
    result_keys = {
        (str(row.get("sourceDate") or row.get("date")), str(row.get("code")), str(row.get("node")))
        for row in results
        if (row.get("sourceDate") or row.get("date")) and row.get("code") and row.get("node")
    }
    due_date = dt.date.fromisoformat(date)
    debts = []
    for row in predictions:
        code = str(row.get("code") or "")
        for node, due in (row.get("validationDates") or {}).items():
            try:
                if dt.date.fromisoformat(str(due)) > due_date:
                    continue
            except ValueError:
                continue
            key = (str(row.get("date")), code, str(node))
            if key not in result_keys:
                debts.append({
                    "预测日": row.get("date"),
                    "到期日": due,
                    "节点": node,
                    "代码": code,
                    "名称": row.get("name"),
                    "角色": row.get("role"),
                    "分数": row.get("score"),
                    "权限": row.get("permission"),
                })
    summary["作战室D+到期未回填"] = {"样本数": len(debts), "明细": debts[:80]}
    return summary


def hotlist_summary(date: str) -> dict:
    result = {}
    tgb = load_json(ROOT / f"raw/04-市场数据/热榜/{date}/淘股吧热榜100-latest.json")
    if tgb:
        result["淘股吧"] = {
            "股票热榜": len(tgb.get("股票热榜") or []),
            "热门讨论": len(tgb.get("热门讨论100") or []),
            "话题榜": len(tgb.get("话题榜") or []),
            "实盘赛热门买入": len(tgb.get("实盘赛热门买入") or []),
            "详情深挖": len(tgb.get("热门个股详情TopN") or []),
        }
    ths = load_json(ROOT / f"raw/04-市场数据/同花顺热榜/{date}/ths-hot-top100.json")
    if ths:
        result["同花顺"] = {"Top100": len(ths.get("rows") or [])}
    tdx = load_json(ROOT / f"raw/04-市场数据/通达信热榜/{date}/tdx-hot-top100.json")
    if tdx:
        result["通达信"] = {"Top100": len(tdx.get("data") or [])}
    merged = load_json(ROOT / f"raw/04-市场数据/三榜热度合并/{date}/三榜热度合并.json")
    if merged:
        rows = merged.get("股票") or []
        result["三榜合并"] = {
            "合并股票": len(rows),
            "三榜共振": sum(1 for row in rows if row.get("同花顺排名") and row.get("通达信排名") and row.get("淘股吧排名")),
        }
    return result


def build_dashboard(date: str) -> dict:
    active_context = load_json(ROOT / ".system/current-ai-context.json")
    active_date = active_context.get("activeDate") or date
    current_warroom_text = read_text(ROOT / "wiki/07-作战室/当前作战室工作页.md")
    current_warroom_date = extract_yaml_date(current_warroom_text)
    pinned, missing = pinned_pages_status()
    validations = validation_summary(date)
    hotlists = hotlist_summary(date)
    required_files = [
        "wiki/00-总纲/20万小资金做大与AI超短进化总控.md",
        "wiki/10-系统配置/AI每日启动读取清单.md",
        "wiki/06-持仓与资金管理/当前持仓决策.md",
        "wiki/07-作战室/当前作战室工作页.md",
        f"wiki/07-作战室/{date}-作战总控.md",
        f"wiki/07-作战室/{date}-作战室候选票评分表.md",
        f"wiki/09-统计与进化/{date}-D+验证任务.md",
        "wiki/09-统计与进化/D+验证待回填总览.md",
        "wiki/04-L4交易模式与执行/20万小资金超短模式总控.md",
        "wiki/04-L4交易模式与执行/20万小资金模式权限矩阵.md",
        f"raw/04-市场数据/三榜热度合并/{date}/三榜热度合并.json",
    ]
    checks = [file_status(path) for path in required_files]
    hard_issues = []
    if current_warroom_date and current_warroom_date != active_date:
        hard_issues.append(f"当前作战室日期为{current_warroom_date}，当前上下文日期为{active_date}，必须同步。")
    if missing:
        hard_issues.append(f"必读页缺失{len(missing)}个。")
    if validations["作战室D+到期未回填"]["样本数"] > 0:
        hard_issues.append(f"作战室D+到期未回填{validations['作战室D+到期未回填']['样本数']}项。")
    return {
        "日期": date,
        "生成时间": dt.datetime.now(TZ).isoformat(timespec="seconds"),
        "当前上下文日期": active_date,
        "当前作战室日期": current_warroom_date,
        "硬问题": hard_issues,
        "必需文件检查": checks,
        "必读页缺失": missing,
        "验证摘要": validations,
        "热榜摘要": hotlists,
        "下一步优先级": [
            "先修当前作战室日期和持仓证据日期，防止对话读旧计划。",
            "优先回填作战室D+到期未验证项，不能让候选票停在unknown。",
            "盘前只从当前作战室、模式权限矩阵、三榜合并和D+任务生成动作。",
            "淘股吧/名人堂/三榜只进入权重和验证，不直接越权给买入结论。",
        ],
    }


def md_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell if cell is not None else "").replace("|", "/").replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def write_markdown(path: Path, data: dict) -> None:
    lines = [
        f"# {data['日期']} Codex每日总控驾驶舱",
        "",
        f"- 生成时间：{data['生成时间']}",
        f"- 当前上下文日期：{data['当前上下文日期']}",
        f"- 当前作战室日期：{data['当前作战室日期'] or '未识别'}",
        "",
        "## 硬问题",
        "",
    ]
    if data["硬问题"]:
        lines.extend([f"- {item}" for item in data["硬问题"]])
    else:
        lines.append("- 暂无硬问题。")
    lines += ["", "## 必需文件检查", ""]
    lines.append(md_table(
        ["路径", "存在", "大小", "修改时间"],
        [[row["路径"], "是" if row["存在"] else "否", row["大小"], row["修改时间"]] for row in data["必需文件检查"]],
    ))
    lines += ["", "## 验证摘要", ""]
    lines.append(md_table(
        ["验证层", "样本数", "状态分布/说明"],
        [
            [name, value.get("样本数"), json.dumps(value.get("状态分布") or {"明细": len(value.get("明细") or [])}, ensure_ascii=False)]
            for name, value in data["验证摘要"].items()
        ],
    ))
    debts = data["验证摘要"]["作战室D+到期未回填"]["明细"]
    lines += ["", "## 作战室D+到期未回填Top80", ""]
    lines.append(md_table(
        ["预测日", "到期日", "节点", "代码", "名称", "角色", "分数", "权限"],
        [[x.get("预测日"), x.get("到期日"), x.get("节点"), x.get("代码"), x.get("名称"), x.get("角色"), x.get("分数"), x.get("权限")] for x in debts],
    ))
    lines += ["", "## 热榜摘要", ""]
    lines.append(md_table(
        ["来源", "摘要"],
        [[name, json.dumps(value, ensure_ascii=False)] for name, value in data["热榜摘要"].items()],
    ))
    lines += ["", "## 下一步优先级", ""]
    lines.extend([f"- {item}" for item in data["下一步优先级"]])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(date: str) -> dict:
    data = build_dashboard(date)
    out_dir = ROOT / "wiki/09-统计与进化"
    json_path = out_dir / f"{date}-Codex每日总控驾驶舱.json"
    md_path = out_dir / f"{date}-Codex每日总控驾驶舱.md"
    system_path = ROOT / ".system/codex-daily-master-dashboard.json"
    text = json.dumps(data, ensure_ascii=False, indent=2)
    json_path.write_text(text + "\n", encoding="utf-8")
    system_path.write_text(text + "\n", encoding="utf-8")
    write_markdown(md_path, data)
    return {
        "json": str(json_path),
        "md": str(md_path),
        "system": str(system_path),
        "硬问题数": len(data["硬问题"]),
        "作战室D+到期未回填": data["验证摘要"]["作战室D+到期未回填"]["样本数"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成20万小资金与Codex自进化每日总控驾驶舱。")
    parser.add_argument("--date", default=today_cn())
    args = parser.parse_args()
    print(json.dumps(run(args.date), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
