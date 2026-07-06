#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


ROOT = Path("/Users/qixinchaye/wiki/73神话")


def today() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_code(code: str | None) -> str:
    code = (code or "").strip()
    if len(code) == 8 and code[:2] in {"sh", "sz", "bj"}:
        return code
    if len(code) == 6 and code[0] in {"0", "2", "3"}:
        return "sz" + code
    if len(code) == 6 and code[0] in {"6", "9"}:
        return "sh" + code
    if len(code) == 6 and code[0] in {"4", "8"}:
        return "bj" + code
    return code


def ensure_stock(book: dict[str, dict], code: str, name: str) -> dict:
    code = normalize_code(code)
    item = book.setdefault(code, {
        "代码": code,
        "名称": name or "",
        "来源榜单": [],
        "同花顺排名": None,
        "通达信排名": None,
        "淘股吧排名": [],
        "同花顺热度": None,
        "通达信人气值": None,
        "淘股吧人气值": None,
        "涨跌幅": None,
        "成交额": None,
        "连板标记": "",
        "概念标签": [],
        "淘股吧关注理由": "",
        "淘股吧社区模式词": [],
        "淘股吧社区关注点": [],
        "实盘赛买入人数": None,
        "验证点": "D+1看溢价和负反馈；D+3看题材扩散；D+5看是否成为主线或退潮噪音。",
    })
    if name and not item["名称"]:
        item["名称"] = name
    return item


def add_source(item: dict, source: str, rank) -> None:
    label = f"{source}#{rank}" if rank not in (None, "") else source
    if label not in item["来源榜单"]:
        item["来源榜单"].append(label)


def add_concepts(item: dict, concepts) -> None:
    for concept in concepts or []:
        if isinstance(concept, dict):
            name = concept.get("概念名称") or concept.get("gnName")
        else:
            name = str(concept)
        if name and name not in item["概念标签"]:
            item["概念标签"].append(name)


def merge_ths(book: dict[str, dict], date: str, source_path: Path) -> None:
    data = load_json(source_path)
    for row in data.get("rows") or []:
        item = ensure_stock(book, row.get("code"), row.get("name"))
        rank = row.get("rank")
        item["同花顺排名"] = rank
        item["同花顺热度"] = row.get("hotScore")
        item["涨跌幅"] = item["涨跌幅"] if item["涨跌幅"] is not None else row.get("changePercent")
        add_concepts(item, row.get("conceptTags"))
        add_source(item, "同花顺热榜", rank)


def merge_tdx(book: dict[str, dict], date: str, source_path: Path) -> None:
    data = load_json(source_path)
    for row in data.get("data") or []:
        item = ensure_stock(book, row.get("代码"), row.get("名称"))
        rank = row.get("排名")
        item["通达信排名"] = rank
        item["通达信人气值"] = row.get("人气值")
        item["涨跌幅"] = item["涨跌幅"] if item["涨跌幅"] is not None else row.get("涨跌幅")
        add_source(item, "通达信热榜", rank)


def merge_tgb(book: dict[str, dict], date: str, source_path: Path) -> None:
    data = load_json(source_path)
    for row in data.get("股票热榜") or []:
        item = ensure_stock(book, row.get("代码"), row.get("名称"))
        rank_info = {"榜单": row.get("榜单"), "排名": row.get("排名")}
        if rank_info not in item["淘股吧排名"]:
            item["淘股吧排名"].append(rank_info)
        item["淘股吧人气值"] = item["淘股吧人气值"] if item["淘股吧人气值"] is not None else row.get("人气值")
        item["涨跌幅"] = item["涨跌幅"] if item["涨跌幅"] is not None else row.get("涨跌幅")
        item["成交额"] = item["成交额"] if item["成交额"] is not None else row.get("成交额")
        item["连板标记"] = item["连板标记"] or row.get("连板标记") or ""
        item["淘股吧关注理由"] = item["淘股吧关注理由"] or row.get("淘股吧关注理由") or ""
        add_concepts(item, row.get("关联概念"))
        add_source(item, f"淘股吧{row.get('榜单')}", row.get("排名"))
    for row in data.get("淘股吧6维补充") or []:
        item = ensure_stock(book, row.get("代码"), row.get("名称"))
        add_concepts(item, row.get("淘股吧题材归属"))
        item["淘股吧关注理由"] = item["淘股吧关注理由"] or row.get("淘股吧关注理由") or ""
        item["淘股吧社区模式词"] = row.get("社区模式词") or item["淘股吧社区模式词"]
        item["淘股吧社区关注点"] = row.get("社区关注点") or item["淘股吧社区关注点"]
        item["实盘赛买入人数"] = row.get("实盘赛买入人数") or item["实盘赛买入人数"]


def score_item(item: dict) -> int:
    score = 0
    if item.get("同花顺排名"):
        score += 1000 - int(item["同花顺排名"])
    if item.get("通达信排名"):
        score += 1000 - int(item["通达信排名"])
    if item.get("淘股吧排名"):
        score += 500 + max(0, 100 - min(int(x.get("排名") or 999) for x in item["淘股吧排名"]))
    if item.get("实盘赛买入人数"):
        score += min(int(item["实盘赛买入人数"]), 1000)
    return score


def md_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell if cell is not None else "").replace("|", "/").replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def write_markdown(path: Path, payload: dict) -> None:
    rows = payload["股票"]
    lines = [
        f"# {payload['日期']} 三榜热度合并",
        "",
        f"- 生成时间：{payload['生成时间']}",
        f"- 同花顺文件：`{payload['输入文件'].get('同花顺', '')}`",
        f"- 通达信文件：`{payload['输入文件'].get('通达信', '')}`",
        f"- 淘股吧文件：`{payload['输入文件'].get('淘股吧', '')}`",
        f"- 合并股票数：{len(rows)}",
        "",
        "## 三榜合并Top100",
        "",
    ]
    lines.append(md_table(
        ["综合", "代码", "名称", "同花顺", "通达信", "淘股吧", "来源", "涨跌幅", "连板", "概念", "淘股吧关注理由", "实盘买入"],
        [
            [
                item.get("综合排名"),
                item.get("代码"),
                item.get("名称"),
                item.get("同花顺排名"),
                item.get("通达信排名"),
                "、".join([f"{x.get('榜单')}#{x.get('排名')}" for x in item.get("淘股吧排名") or []][:4]),
                "、".join(item.get("来源榜单") or []),
                item.get("涨跌幅"),
                item.get("连板标记"),
                "、".join((item.get("概念标签") or [])[:5]),
                item.get("淘股吧关注理由"),
                item.get("实盘赛买入人数"),
            ]
            for item in rows[:100]
        ],
    ))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_validation_queue(date: str, rows: list[dict]) -> None:
    queue = ROOT / "wiki/09-统计与进化/三榜热度有效性验证.md"
    if not queue.exists():
        queue.write_text(
            "# 三榜热度有效性验证\n\n"
            "| 日期 | 代码 | 名称 | 来源 | 同花顺 | 通达信 | 淘股吧 | D+1 | D+3 | D+5 | 结论 |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    text = queue.read_text(encoding="utf-8")
    additions = []
    for item in rows[:30]:
        marker = f"| {date} | {item.get('代码')} |"
        if marker in text:
            continue
        additions.append(
            f"| {date} | {item.get('代码')} | {item.get('名称')} | "
            f"{'、'.join(item.get('来源榜单') or [])} | {item.get('同花顺排名') or ''} | "
            f"{item.get('通达信排名') or ''} | "
            f"{'、'.join([str(x.get('排名')) for x in item.get('淘股吧排名') or []][:3])} |  |  |  |  |\n"
        )
    if additions:
        with queue.open("a", encoding="utf-8") as fh:
            fh.writelines(additions)


def run(date: str, tgb_slot: str | None) -> dict:
    ths_path = ROOT / "raw/04-市场数据/同花顺热榜" / date / "ths-hot-top100.json"
    tdx_path = ROOT / "raw/04-市场数据/通达信热榜" / date / "tdx-hot-top100.json"
    tgb_name = f"淘股吧热榜100-{tgb_slot}.json" if tgb_slot else "淘股吧热榜100-latest.json"
    tgb_path = ROOT / "raw/04-市场数据/热榜" / date / tgb_name
    book: dict[str, dict] = {}
    merge_ths(book, date, ths_path)
    merge_tdx(book, date, tdx_path)
    merge_tgb(book, date, tgb_path)
    rows = sorted(book.values(), key=lambda x: (-score_item(x), x.get("代码") or ""))
    for idx, item in enumerate(rows, 1):
        item["综合排名"] = idx
        item["来源数量"] = len({src.split("#")[0] for src in item.get("来源榜单") or []})
    out_dir = ROOT / "raw/04-市场数据/三榜热度合并" / date
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "日期": date,
        "生成时间": dt.datetime.now().isoformat(timespec="seconds"),
        "输入文件": {
            "同花顺": str(ths_path.relative_to(ROOT)) if ths_path.exists() else "",
            "通达信": str(tdx_path.relative_to(ROOT)) if tdx_path.exists() else "",
            "淘股吧": str(tgb_path.relative_to(ROOT)) if tgb_path.exists() else "",
        },
        "股票": rows,
    }
    json_path = out_dir / "三榜热度合并.json"
    md_path = out_dir / "三榜热度合并.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(md_path, payload)
    append_validation_queue(date, rows)
    return {
        "json": str(json_path),
        "md": str(md_path),
        "合并股票数": len(rows),
        "三榜共振数": sum(1 for item in rows if item.get("同花顺排名") and item.get("通达信排名") and item.get("淘股吧排名")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="合并同花顺、通达信、淘股吧三榜热度并建立D+验证队列。")
    parser.add_argument("--date", default=today(), help="日期，默认今天")
    parser.add_argument("--tgb-slot", help="指定淘股吧热榜时段；默认latest")
    args = parser.parse_args()
    print(json.dumps(run(args.date, args.tgb_slot), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
