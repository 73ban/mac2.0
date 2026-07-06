#!/usr/bin/env python3
"""Extract structured RAW derivatives from fact-layer market source files.

Fact-layer agents only need to provide complete source JSON. Codex owns the
derived RAW tables used for analysis, WIKI writing, D+ validation, and training.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "/").replace("\n", " ")


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except Exception:
        return None


def market(code: Any) -> str:
    text = str(code or "")
    if text.startswith("60"):
        return "沪主板"
    if text.startswith(("00", "001", "002", "003")):
        return "深主板"
    if text.startswith("30"):
        return "创业板"
    if text.startswith("68"):
        return "科创板"
    if text.startswith(("8", "9")):
        return "北交所"
    return "未知"


def limit_range(code: Any) -> str:
    text = str(code or "")
    if text.startswith(("30", "68")):
        return "20cm"
    if text.startswith(("8", "9")):
        return "30cm"
    return "10cm"


def infer_industry_logic(item: dict) -> str:
    """Infer a concise industry logic from fact fields only."""
    theme = str(item.get("涨停原因") or "")
    reason = str(item.get("原因揭秘") or "")
    text = f"{theme} {reason}"
    rules = [
        (("机器人", "人形机器人", "Optimus", "优必选"), "机器人主线：人形机器人/工业自动化催化，验证点在首板晋级、容量中军承接和板块内连板高度。"),
        (("CPO", "光模块", "数据中心交换机", "锐捷"), "AI算力链：CPO/光模块/数据中心设备方向，核心看海外算力映射、成交额中军和一字先锋强度。"),
        (("存储", "存储器", "HBM", "DRAM", "NAND"), "半导体存储链：存储器国产替代/涨价/并购映射，重点看产业链纯度和资金持续性。"),
        (("并购", "重组", "资产注入", "发行股份", "购买"), "并购重组线：事件驱动强，情绪弹性大，但主线代表性需和板块扩散、换手承接分开判断。"),
        (("摘帽", "撤销退市风险", "ST"), "摘帽修复线：偏事件修复和低价情绪，独立性强，不能直接代表主流题材强度。"),
        (("房地产", "地产", "物业"), "地产链：政策/修复预期驱动，持续性取决于板块扩散和权重地产承接。"),
        (("稀土", "钨", "锂", "黄金", "贵金属", "资源"), "资源品链：价格/供需/政策预期驱动，重点看期货或商品价格、容量票和趋势龙共振。"),
        (("电力", "电网", "储能", "风电", "光伏"), "电力设备/能源链：政策或订单驱动，重点看板块强度排名、资金龙和中军是否同步。"),
        (("医药", "创新药", "药", "医疗"), "医药线：消息和业绩催化驱动，持续性看同题材首板数量、20cm弹性和机构资金认可。"),
        (("消费", "食品", "零售", "旅游"), "消费线：轮动属性较强，需用板块涨幅排名和连板晋级率确认是否升级为主线。"),
    ]
    for keys, logic in rules:
        if any(key.lower() in text.lower() for key in keys):
            return logic
    if reason:
        return "事件驱动：以涨停原因和公告/新闻催化为主，需用次日晋级、开板次数和资金承接验证持续性。"
    if theme:
        return "题材驱动：源文件有题材标签但缺少具体事件，需要补新闻/公告来源确认催化强度。"
    return "待补事实源：缺题材归属和原因揭秘，不能生成产业逻辑。"


def infer_stock_position(item: dict) -> str:
    height = int(item.get("连板天数") or 1)
    days = cell(item.get("几天"))
    boards = cell(item.get("几板"))
    board_type = item.get("板型") or "板型未标注"
    fund = item.get("资金流向") or {}
    main_net = as_float(fund.get("主力净额万元"))
    main_ratio = as_float(fund.get("主力占比"))
    seal = as_float(item.get("封单金额"))
    first_time = str(item.get("首次涨停") or "")
    tags: list[str] = []
    if height >= 4:
        tags.append("高度龙/空间锚")
    elif height >= 3:
        tags.append("趋势龙候选")
    elif height == 2:
        tags.append("2板晋级候选")
    else:
        tags.append("首板观察")
    if first_time.startswith("09:25") or "一字" in str(board_type):
        tags.append("先锋强度高")
    if main_net is not None and main_net >= 5000:
        tags.append("资金认可")
    if main_ratio is not None and main_ratio >= 20:
        tags.append("主力占比高")
    if seal is not None and seal >= 100_000_000:
        tags.append("封单强")
    return f"{height}板，{days}天{boards}板，{board_type}；" + "，".join(tags)


def infer_next_validation(item: dict) -> str:
    height = int(item.get("连板天数") or 1)
    theme = item.get("涨停原因") or "对应题材"
    if height >= 4:
        return f"看是否继续打开空间并带动{theme}扩散；若高标断板杀跌，题材降权。"
    if height >= 2:
        return f"看是否晋级{height + 1}板、是否带动同题材首板/中军承接；不晋级且放量大阴则降权。"
    return f"看首板次日是否晋级或高开承接，验证{theme}是否从消息扩散为交易主线。"


def daily_limit_path(date: str) -> Path:
    candidates = [
        ROOT / f"raw/04-市场数据/每日涨停全景/{date}/tdx-daily-limit.json",
        ROOT / f"raw/04-市场数据/每日涨停全景/{date}/tdx-limit-up-panorama.json",
        ROOT / f"raw/04-市场数据/每日涨停全景/{date}/通达信涨停全景.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def records_from_daily_limit(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("记录", "数据", "涨停明细", "items", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def normalize_limit_record(raw: dict) -> dict:
    code = raw.get("代码") or raw.get("股票代码") or raw.get("code")
    fund = raw.get("资金流向") if isinstance(raw.get("资金流向"), dict) else {}
    return {
        "代码": str(code or ""),
        "名称": raw.get("名称") or raw.get("股票名称") or raw.get("股票名") or raw.get("name") or "",
        "市场": market(code),
        "涨停幅度": limit_range(code),
        "涨跌幅": raw.get("涨跌幅") or raw.get("涨幅"),
        "连板天数": int(raw.get("连板天数") or raw.get("高度") or raw.get("连板") or 1),
        "几天": raw.get("几天") or raw.get("天数"),
        "几板": raw.get("几板") or raw.get("板数"),
        "板型": raw.get("板型") or "",
        "首次涨停": raw.get("首次涨停") or raw.get("首次封板") or raw.get("涨停时间") or "",
        "开板次数": raw.get("开板次数"),
        "封单金额": raw.get("封单金额") or raw.get("封单"),
        "最大封单额_万": raw.get("最大封单额_万"),
        "涨停成交额_万": raw.get("涨停成交额_万") or raw.get("成交额_万"),
        "涨停原因": raw.get("涨停原因") or raw.get("短线主题") or "",
        "原因揭秘": raw.get("原因揭秘") or raw.get("上榜原因") or "",
        "资金流向": fund,
    }


def write_daily_limit_md(date: str, source_path: Path, records: list[dict]) -> Path:
    out = ROOT / f"raw/04-市场数据/每日涨停全景/{date}/tdx-daily-limit.md"
    first_count = sum(1 for item in records if item["连板天数"] <= 1)
    ladder_count = len(records) - first_count
    lines = [
        f"# {date} 每日涨停全景 RAW 全量表",
        "",
        f"- 生成时间：{now_text()}",
        f"- 数据源：`{rel(source_path)}`",
        f"- 涨停总数：{len(records)}",
        f"- 首板：{first_count}",
        f"- 连板：{ladder_count}",
        "- ST口径：依赖源文件口径；事实层应剔除ST。",
        "",
        "| 排名 | 代码 | 名称 | 市场 | 涨停幅度 | 涨跌幅 | 连板 | 几天几板 | 板型 | 首次涨停 | 开板 | 封单金额 | 涨停成交额万 | 主力净额万 | 涨停原因 | 原因揭秘 |",
        "|---:|---|---|---|---|---:|---:|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for idx, item in enumerate(records, 1):
        fund = item.get("资金流向") or {}
        lines.append(
            f"| {idx} | {cell(item['代码'])} | {cell(item['名称'])} | {cell(item['市场'])} | {cell(item['涨停幅度'])} | "
            f"{cell(item['涨跌幅'])} | {cell(item['连板天数'])} | {cell(item.get('几天'))}天{cell(item.get('几板'))}板 | "
            f"{cell(item.get('板型'))} | {cell(item.get('首次涨停'))} | {cell(item.get('开板次数'))} | "
            f"{cell(item.get('封单金额'))} | {cell(item.get('涨停成交额_万'))} | {cell(fund.get('主力净额万元'))} | "
            f"{cell(item.get('涨停原因'))} | {cell(item.get('原因揭秘'))} |"
        )
    write_text(out, "\n".join(lines))
    return out


def write_first_board(date: str, source_path: Path, records: list[dict]) -> list[Path]:
    first = [item for item in records if item["连板天数"] <= 1]
    out_dir = ROOT / f"raw/04-市场数据/首板涨停催化/{date}"
    json_path = out_dir / "tdx-first-board-catalyst.json"
    md_path = out_dir / "tdx-first-board-catalyst.md"
    write_json(
        json_path,
        {
            "生成时间": now_text(),
            "交易日期": date,
            "生成方": "Codex从每日涨停全景RAW拆分",
            "数据源": rel(source_path),
            "口径": "剔除ST后的全市场首板涨停票逐票落盘；首板=连板天数<=1",
            "首板总数": len(first),
            "质量等级": "complete_raw_split_from_daily_limit",
            "首板明细": first,
        },
    )
    lines = [
        f"# {date} 首板涨停催化 RAW",
        "",
        f"- 生成时间：{now_text()}",
        f"- 数据源：`{rel(source_path)}`",
        f"- 首板总数：{len(first)}",
        "",
        "| 排名 | 代码 | 名称 | 市场 | 涨停幅度 | 首次涨停 | 开板次数 | 板型 | 封单金额 | 涨停原因 | 原因揭秘 | 主力净额万元 |",
        "|---:|---|---|---|---|---|---:|---|---:|---|---|---:|",
    ]
    for idx, item in enumerate(first, 1):
        fund = item.get("资金流向") or {}
        lines.append(
            f"| {idx} | {cell(item['代码'])} | {cell(item['名称'])} | {cell(item['市场'])} | {cell(item['涨停幅度'])} | "
            f"{cell(item.get('首次涨停'))} | {cell(item.get('开板次数'))} | {cell(item.get('板型'))} | "
            f"{cell(item.get('封单金额'))} | {cell(item.get('涨停原因'))} | {cell(item.get('原因揭秘'))} | {cell(fund.get('主力净额万元'))} |"
        )
    write_text(md_path, "\n".join(lines))
    return [json_path, md_path]


def write_limit_reasons(date: str, source_path: Path, records: list[dict]) -> list[Path]:
    ladder = [item for item in records if item["连板天数"] > 1]
    out_dir = ROOT / f"raw/04-市场数据/通达信涨停原因/{date}"
    json_path = out_dir / "tdx-limit-reason-6dim.json"
    md_path = out_dir / "tdx-limit-reason-6dim.md"
    rows = []
    for item in ladder:
        fund = item.get("资金流向") or {}
        rows.append(
            {
                "代码": item["代码"],
                "名称": item["名称"],
                "市场": item["市场"],
                "涨停幅度": item["涨停幅度"],
                "连板天数": item["连板天数"],
                "几天": item.get("几天"),
                "几板": item.get("几板"),
                "题材归属": item.get("涨停原因") or "待补",
                "事件催化": item.get("原因揭秘") or "待补",
                "产业逻辑": infer_industry_logic(item),
                "个股地位": infer_stock_position(item),
                "盘口质量": {
                    "首次涨停": item.get("首次涨停"),
                    "开板次数": item.get("开板次数"),
                    "封单金额": item.get("封单金额"),
                    "最大封单额_万": item.get("最大封单额_万"),
                    "涨停成交额_万": item.get("涨停成交额_万"),
                    "主力净额万元": fund.get("主力净额万元"),
                    "主力占比": fund.get("主力占比"),
                },
                "明日验证点": infer_next_validation(item),
            }
        )
    write_json(
        json_path,
        {
            "生成时间": now_text(),
            "交易日期": date,
            "生成方": "Codex从每日涨停全景RAW拆分",
            "数据源": rel(source_path),
            "口径": "剔除ST后的2板及以上连板票逐票落盘；题材、事件、盘口来自TDX，产业逻辑/个股地位/明日验证点由Codex按固定规则从事实字段推导",
            "2板及以上总数": len(rows),
            "质量等级": "complete_fact_slots_from_daily_limit",
            "通达信涨停原因6维事实源": rows,
        },
    )
    lines = [
        f"# {date} 通达信涨停原因6维事实源",
        "",
        f"- 生成时间：{now_text()}",
        f"- 数据源：`{rel(source_path)}`",
        f"- 2板及以上总数：{len(rows)}",
        "- 说明：题材归属、事件催化、盘口质量来自TDX原始字段；产业逻辑、个股地位和明日验证点由Codex按规则从事实字段推导。",
        "",
        "| 高度 | 代码 | 名称 | 市场 | 题材归属 | 事件催化 | 个股地位 | 首次涨停 | 开板次数 | 封单金额 | 主力净额万元 | 明日验证点 |",
        "|---:|---|---|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for item in rows:
        quality = item["盘口质量"]
        lines.append(
            f"| {cell(item['连板天数'])} | {cell(item['代码'])} | {cell(item['名称'])} | {cell(item['市场'])} | "
            f"{cell(item['题材归属'])} | {cell(item['事件催化'])} | {cell(item['个股地位'])} | "
            f"{cell(quality.get('首次涨停'))} | {cell(quality.get('开板次数'))} | {cell(quality.get('封单金额'))} | "
            f"{cell(quality.get('主力净额万元'))} | {cell(item['明日验证点'])} |"
        )
    write_text(md_path, "\n".join(lines))
    return [json_path, md_path]


def write_ladder_md(date: str, records: list[dict]) -> Path | None:
    json_path = ROOT / f"raw/04-市场数据/通达信连板天梯/{date}/tdx-limit-ladder.json"
    if not json_path.exists():
        return None
    payload = read_json(json_path)
    items = payload.get("连板天梯") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None
    full_by_code = {item["代码"]: item for item in records}
    out = json_path.with_suffix(".md")
    lines = [
        f"# {date} 通达信连板天梯 RAW 全量表",
        "",
        f"- 生成时间：{now_text()}",
        f"- 数据源：`{rel(json_path)}`",
        f"- 连板总数：{payload.get('连板总数', len(items))}",
        f"- 高度分布：{json.dumps(payload.get('按高度分布', {}), ensure_ascii=False)}",
        "",
        "| 排名 | 高度 | 代码 | 名称 | 板型 | 首次涨停 | 开板 | 封单金额 | 涨停成交额万 | 主力净额万 | 涨停原因 | 原因揭秘 |",
        "|---:|---:|---|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    sorted_items = sorted(items, key=lambda x: (-(int(x.get("连板天数") or 0)), str(x.get("首次涨停") or "99:99:99")))
    for idx, item in enumerate(sorted_items, 1):
        full = full_by_code.get(str(item.get("代码") or ""), {})
        fund = full.get("资金流向") or {}
        lines.append(
            f"| {idx} | {cell(item.get('连板天数'))} | {cell(item.get('代码'))} | {cell(item.get('名称'))} | "
            f"{cell(item.get('板型'))} | {cell(item.get('首次涨停'))} | {cell(item.get('开板次数'))} | "
            f"{cell(item.get('封单'))} | {cell(full.get('涨停成交额_万'))} | {cell(fund.get('主力净额万元'))} | "
            f"{cell(item.get('涨停原因'))} | {cell(item.get('原因揭秘'))} |"
        )
    write_text(out, "\n".join(lines))
    return out


def write_tdx_hot_md(date: str, records: list[dict]) -> Path | None:
    json_path = ROOT / f"raw/04-市场数据/通达信热榜/{date}/tdx-hot-top100.json"
    if not json_path.exists():
        return None
    payload = read_json(json_path)
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None
    full_by_code = {item["代码"]: item for item in records}
    ladder_codes = {item["代码"] for item in records if item["连板天数"] > 1}
    limit_codes = set(full_by_code)
    out = json_path.with_suffix(".md")
    lines = [
        f"# {date} 通达信热榜 Top100 RAW",
        "",
        f"- 生成时间：{now_text()}",
        f"- 数据源：`{rel(json_path)}`",
        f"- 返回总数：{payload.get('返回总数', len(items))}",
        "",
        "| 排名 | 代码 | 名称 | 涨跌幅 | 人气值 | 是否涨停 | 是否连板 | 涨停原因 |",
        "|---:|---|---|---:|---:|---|---|---|",
    ]
    for item in items:
        code = str(item.get("代码") or "")
        full = full_by_code.get(code, {})
        lines.append(
            f"| {cell(item.get('排名'))} | {cell(code)} | {cell(item.get('名称'))} | {cell(item.get('涨跌幅'))} | "
            f"{cell(item.get('人气值'))} | {'是' if code in limit_codes else '否'} | {'是' if code in ladder_codes else '否'} | {cell(full.get('涨停原因'))} |"
        )
    write_text(out, "\n".join(lines))
    return out


def write_turnover_md(date: str, records: list[dict]) -> Path | None:
    json_path = ROOT / f"raw/04-市场数据/通达信成交额排名/{date}/tdx-成交额Top100.json"
    if not json_path.exists():
        return None
    payload = read_json(json_path)
    items = payload.get("数据") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None
    full_by_code = {item["代码"]: item for item in records}
    ladder_codes = {item["代码"] for item in records if item["连板天数"] > 1}
    out = json_path.with_suffix(".md")
    lines = [
        f"# {date} 通达信成交额 Top100 RAW",
        "",
        f"- 生成时间：{now_text()}",
        f"- 数据源：`{rel(json_path)}`",
        f"- 实际获取：{payload.get('元数据', {}).get('实际获取', len(items))}",
        "",
        "| 排名 | 代码 | 名称 | 涨跌幅 | 成交额 | 是否涨停 | 是否连板 |",
        "|---:|---|---|---:|---:|---|---|",
    ]
    for item in items:
        code = str(item.get("股票代码") or item.get("代码") or "")
        name = item.get("股票名称") or item.get("股票名") or item.get("名称") or ""
        pct = item.get("涨跌幅") or item.get("涨幅") or item.get("涨跌幅%")
        amount = item.get("成交额") or item.get("成交额_亿") or item.get("今日成交额")
        lines.append(
            f"| {cell(item.get('排名'))} | {cell(code)} | {cell(name)} | {cell(pct)} | {cell(amount)} | "
            f"{'是' if code in full_by_code else '否'} | {'是' if code in ladder_codes else '否'} |"
        )
    write_text(out, "\n".join(lines))
    return out


def write_board_strength_md(date: str) -> Path | None:
    json_path = ROOT / f"raw/04-市场数据/板块强度/{date}/tdx-board-strength.json"
    if not json_path.exists():
        return None
    payload = read_json(json_path)
    out = json_path.with_suffix(".md")
    lines = [
        f"# {date} 通达信板块强度 RAW",
        "",
        f"- 生成时间：{now_text()}",
        f"- 数据源：`{rel(json_path)}`",
        f"- 板块总数：{payload.get('板块总数_全市场', '')}",
        f"- 已拉取涨幅：{payload.get('已拉取涨幅', '')}",
        f"- 已拉取跌幅：{payload.get('已拉取跌幅', '')}",
        f"- 质量等级：{payload.get('质量等级', '')}",
        "",
        "## 涨幅前10",
        "",
        "| 排名 | 代码 | 名称 | 涨跌幅 |",
        "|---:|---|---|---:|",
    ]
    for item in payload.get("涨幅Top10", []):
        lines.append(f"| {cell(item.get('排名'))} | {cell(item.get('代码'))} | {cell(item.get('名称'))} | {cell(item.get('涨跌幅'))} |")
    lines += ["", "## 跌幅前10", "", "| 排名 | 代码 | 名称 | 涨跌幅 |", "|---:|---|---|---:|"]
    for item in payload.get("跌幅Top10", []):
        lines.append(f"| {cell(item.get('排名'))} | {cell(item.get('代码'))} | {cell(item.get('名称'))} | {cell(item.get('涨跌幅'))} |")
    lines += ["", "## 数据缺口", ""]
    gap = payload.get("缺口", [])
    if isinstance(gap, list):
        lines.extend(f"- {cell(item)}" for item in gap)
    else:
        lines.append(f"- {cell(gap)}")
    write_text(out, "\n".join(lines))
    return out


def write_report(date: str, source_path: Path, records: list[dict], outputs: list[Path]) -> list[Path]:
    first_count = sum(1 for item in records if item["连板天数"] <= 1)
    ladder_count = len(records) - first_count
    lines = [
        f"# {date} Codex数据提取补齐报告",
        "",
        f"- 生成时间：{now_text()}",
        "- 责任口径：原始数据由 Mac 本机自动任务或用户导入 RAW；Codex从原始数据拆分、补齐、分析、写RAW/WIKI。",
        "",
        "## 已补齐输出",
        "",
        "| 输出 | 状态 |",
        "|---|---|",
    ]
    for path in outputs:
        lines.append(f"| `{rel(path)}` | 完成 |")
    lines += [
        "",
        "## 关键数量",
        "",
        f"- 每日涨停全景：{len(records)}只",
        f"- 首板：{first_count}只",
        f"- 2板及以上：{ladder_count}只",
        "",
        "## 剩余真实缺口",
        "",
        "- 产业逻辑、明日验证点属于Codex正式复盘分析，不由事实层用模型硬写。",
        "- 交割单/用户口述仍必须从飞书、用户原始输入或交割单RAW进入，市场数据不能反推买卖理由。",
    ]
    raw_report = ROOT / f"raw/11-Codex分析产物/{date}/{date}-数据提取补齐报告.md"
    wiki_report = ROOT / f"wiki/09-统计与进化/{date}-数据提取补齐报告.md"
    text = "\n".join(lines)
    write_text(raw_report, text)
    write_text(wiki_report, text)
    return [raw_report, wiki_report]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    source = daily_limit_path(args.date)
    outputs: list[Path] = []
    if not source.exists():
        print(json.dumps({"ok": False, "reason": "missing daily limit source", "source": rel(source)}, ensure_ascii=False, indent=2))
        return 2

    payload = read_json(source)
    records = [normalize_limit_record(item) for item in records_from_daily_limit(payload)]
    if not records:
        print(json.dumps({"ok": False, "reason": "daily limit source has no records", "source": rel(source)}, ensure_ascii=False, indent=2))
        return 2

    outputs.append(write_daily_limit_md(args.date, source, records))
    outputs.extend(write_first_board(args.date, source, records))
    outputs.extend(write_limit_reasons(args.date, source, records))
    for optional in (
        write_ladder_md(args.date, records),
        write_tdx_hot_md(args.date, records),
        write_turnover_md(args.date, records),
        write_board_strength_md(args.date),
    ):
        if optional:
            outputs.append(optional)
    outputs.extend(write_report(args.date, source, records, outputs))

    print(json.dumps({"ok": True, "date": args.date, "outputs": [rel(path) for path in outputs]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
