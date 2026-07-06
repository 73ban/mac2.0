#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path("/Users/qixinchaye/wiki/73神话")
TZ = dt.timezone(dt.timedelta(hours=8))


def today() -> str:
    return dt.datetime.now(TZ).date().isoformat()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


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


def clean_cell(value: str) -> str:
    return value.replace("|", "/").replace("\n", " ").strip()


def parse_mapping_sections(path: Path) -> list[dict[str, Any]]:
    text = read_text(path)
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                sections.append(current)
            current = {"name": line[3:].strip(), "rows": [], "doc_count": 0}
            continue
        if current is None:
            continue
        m = re.match(r"资料数：(\d+)", line.strip())
        if m:
            current["doc_count"] = int(m.group(1))
            continue
        if line.startswith("| ") and not line.startswith("| ---") and not line.startswith("|---"):
            parts = [p.strip() for p in line.strip("|").split("|")]
            if parts and parts[0] not in {"日期", "来源"}:
                current["rows"].append(parts)
    if current:
        sections.append(current)
    return sections


def existing_stock_profile(stock: str) -> str:
    root = ROOT / "wiki/03-L3个股档案"
    if not root.exists():
        return ""
    ignore_dirs = {"RAW增量个股卡", "作战室个股雷达卡", "公告事件档案", "总结", "持股态度卡"}
    for path in root.rglob("*.md"):
        if any(part in ignore_dirs for part in path.parts):
            continue
        name = path.stem
        if name.startswith("RAW") or "资料映射" in name or "高价值个股资料池" in name:
            continue
        if stock in name:
            return rel(path)
    return ""


def has_theme_overview(theme: str) -> str:
    root = ROOT / "wiki/02-L2方向题材"
    if not root.exists():
        return ""
    for path in root.glob("*.md"):
        if "RAW" in path.name:
            continue
        if theme in path.stem:
            return rel(path)
    return ""


def hotlist_names(date: str) -> set[str]:
    out: set[str] = set()
    merged = read_json(ROOT / f"raw/04-市场数据/三榜热度合并/{date}/三榜热度合并.json")
    for row in merged.get("股票") or []:
        for key in ("代码", "名称", "stock", "name", "code"):
            value = str(row.get(key) or "").strip()
            if value:
                out.add(value)
    tgb = read_json(ROOT / f"raw/04-市场数据/热榜/{date}/淘股吧热榜100-latest.json")
    for group in ("股票热榜", "淘股吧6维补充"):
        for row in tgb.get(group) or []:
            for key in ("代码", "名称", "stockCode", "stockName", "code", "name"):
                value = str(row.get(key) or "").strip()
                if value:
                    out.add(value)
    return out


def latest_reason(stock: str, rows: list[list[str]]) -> str:
    for row in rows:
        if len(row) >= 3:
            return row[2][:80]
    return ""


def valid_stock_key(value: str) -> bool:
    value = value.strip()
    if re.fullmatch(r"\d{6}", value):
        return True
    if re.fullmatch(r"\d+", value):
        return False
    if len(value) < 2:
        return False
    if any(ch in value for ch in "/\\:："):
        return False
    if re.search(r"[\u4e00-\u9fff]", value):
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{1,20}", value):
        return True
    return False


def build(date: str) -> dict[str, Any]:
    stock_sections = parse_mapping_sections(ROOT / f"wiki/03-L3个股档案/RAW个股资料映射-{date}.md")
    theme_sections = parse_mapping_sections(ROOT / f"wiki/02-L2方向题材/RAW题材资料映射-{date}.md")
    method_sections = parse_mapping_sections(ROOT / f"wiki/04-L4交易模式与执行/游资公众号心得待提炼池-{date}.md")
    hot_names = hotlist_names(date)

    create_stock = []
    append_stock = []
    warroom_review = []
    for sec in stock_sections:
        stock = sec["name"]
        if not valid_stock_key(stock):
            continue
        docs = int(sec.get("doc_count") or len(sec.get("rows") or []))
        if docs < 2:
            continue
        profile = existing_stock_profile(stock)
        in_hot = stock in hot_names
        item = {
            "个股": stock,
            "资料数": docs,
            "已有档案": profile,
            "当日热榜": in_hot,
            "代表资料": latest_reason(stock, sec.get("rows") or []),
        }
        if not profile and (docs >= 3 or in_hot):
            create_stock.append({**item, "建议动作": "新建L3个股概览卡"})
        elif profile and (docs >= 3 or in_hot):
            append_stock.append({**item, "建议动作": "追加到既有L3个股档案"})
        if docs >= 5 or in_hot:
            warroom_review.append({**item, "建议动作": "进入作战室复核池，不直接给买入权限"})

    create_theme = []
    append_theme = []
    for sec in theme_sections:
        theme = sec["name"]
        docs = int(sec.get("doc_count") or len(sec.get("rows") or []))
        if docs < 3:
            continue
        overview = has_theme_overview(theme)
        item = {
            "题材": theme,
            "资料数": docs,
            "已有概览": overview,
            "代表资料": latest_reason(theme, sec.get("rows") or []),
        }
        if not overview and docs >= 5:
            create_theme.append({**item, "建议动作": "新建L2题材概览卡"})
        elif overview:
            append_theme.append({**item, "建议动作": "追加到既有L2题材页"})

    mode_extract = []
    for sec in method_sections:
        method = sec["name"]
        docs = int(sec.get("doc_count") or len(sec.get("rows") or []))
        if docs >= 3:
            mode_extract.append({
                "模式": method,
                "资料数": docs,
                "建议动作": "进入L4模式提炼候选；必须D+验证后才能转正式模式",
                "代表资料": latest_reason(method, sec.get("rows") or []),
            })

    dplus_queue = []
    for item in warroom_review[:80]:
        if item["当日热榜"] or item["资料数"] >= 8:
            dplus_queue.append({
                "标的": item["个股"],
                "触发": "热榜/资料密度",
                "验证节点": ["D+1", "D+3", "D+5"],
                "验证内容": "是否延续热度、是否板块共振、是否出现亏钱效应或承接衰减",
            })

    return {
        "schema": "73wiki-raw-to-wiki-action-planner-v1",
        "日期": date,
        "生成时间": dt.datetime.now(TZ).isoformat(timespec="seconds"),
        "输入": {
            "个股映射": f"wiki/03-L3个股档案/RAW个股资料映射-{date}.md",
            "题材映射": f"wiki/02-L2方向题材/RAW题材资料映射-{date}.md",
            "模式待提炼池": f"wiki/04-L4交易模式与执行/游资公众号心得待提炼池-{date}.md",
            "三榜合并": f"raw/04-市场数据/三榜热度合并/{date}/三榜热度合并.json",
        },
        "动作清单": {
            "新建个股概览卡": create_stock[:100],
            "追加个股档案": append_stock[:100],
            "作战室复核池": warroom_review[:120],
            "新建题材概览卡": create_theme[:80],
            "追加题材页": append_theme[:80],
            "L4模式提炼候选": mode_extract[:80],
            "D+验证建议": dplus_queue[:80],
        },
        "规则": [
            "RAW先入索引，不直接污染正式Wiki。",
            "同一标的资料数>=3或当日热榜出现，触发个股卡新建/追加。",
            "资料数>=5或热榜共振，进入作战室复核池，但不自动给买入权限。",
            "题材资料数>=5且无正式概览，触发新建L2题材概览卡。",
            "模式资料数>=3，只能进入L4模式提炼候选；必须经过D+验证和用户交易反馈后才能升正式模式。",
        ],
    }


def md_table(headers: list[str], rows: list[dict[str, Any]], keys: list[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    if not rows:
        lines.append("| " + " | ".join(["无"] + [""] * (len(headers) - 1)) + " |")
        return "\n".join(lines)
    for row in rows:
        lines.append("| " + " | ".join(clean_cell(str(row.get(key, ""))) for key in keys) + " |")
    return "\n".join(lines)


def write_md(path: Path, data: dict[str, Any]) -> None:
    actions = data["动作清单"]
    lines = [
        f"# {data['日期']} RAW到Wiki主动处理决策台",
        "",
        f"- 生成时间：{data['生成时间']}",
        "",
        "## 处理原则",
        "",
    ]
    lines.extend(f"- {rule}" for rule in data["规则"])
    lines += ["", "## 新建个股概览卡", ""]
    lines.append(md_table(["个股", "资料数", "当日热榜", "代表资料"], actions["新建个股概览卡"], ["个股", "资料数", "当日热榜", "代表资料"]))
    lines += ["", "## 追加个股档案", ""]
    lines.append(md_table(["个股", "资料数", "已有档案", "当日热榜", "代表资料"], actions["追加个股档案"], ["个股", "资料数", "已有档案", "当日热榜", "代表资料"]))
    lines += ["", "## 作战室复核池", ""]
    lines.append(md_table(["个股", "资料数", "当日热榜", "建议动作"], actions["作战室复核池"], ["个股", "资料数", "当日热榜", "建议动作"]))
    lines += ["", "## 新建题材概览卡", ""]
    lines.append(md_table(["题材", "资料数", "代表资料"], actions["新建题材概览卡"], ["题材", "资料数", "代表资料"]))
    lines += ["", "## 追加题材页", ""]
    lines.append(md_table(["题材", "资料数", "已有概览", "代表资料"], actions["追加题材页"], ["题材", "资料数", "已有概览", "代表资料"]))
    lines += ["", "## L4模式提炼候选", ""]
    lines.append(md_table(["模式", "资料数", "建议动作"], actions["L4模式提炼候选"], ["模式", "资料数", "建议动作"]))
    lines += ["", "## D+验证建议", ""]
    lines.append(md_table(["标的", "触发", "验证节点", "验证内容"], actions["D+验证建议"], ["标的", "触发", "验证节点", "验证内容"]))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=today())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    data = build(args.date)
    if args.write:
        out_dir = ROOT / "wiki/09-统计与进化"
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f"{args.date}-RAW到Wiki主动处理决策台.json"
        md_path = out_dir / f"{args.date}-RAW到Wiki主动处理决策台.md"
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        write_md(md_path, data)
        (ROOT / ".system/raw-to-wiki-action-planner.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(str(md_path))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
