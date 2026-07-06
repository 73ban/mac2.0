#!/usr/bin/env python3
"""Build a monthly trade-statistics draft from RAW trade slips and reviews.

This script is evidence-first. It does not pretend every RAW file has the same
schema. It extracts high-confidence facts, records weaker extracted values as
draft data, and writes a reviewable wiki page plus JSON evidence index.

Usage:
  python3 raw/07-系统脚本/codex_build_monthly_trade_stats.py --month 2026-06 --as-of 2026-06-28
"""

from __future__ import annotations

import argparse
from datetime import date as Date
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.lower() == ".xlsx" or data.startswith(b"PK\x03\x04") or data.startswith(b"\xd0\xcf\x11\xe0"):
        return ""
    for encoding in ("utf-8", "gbk", "gb18030", "latin1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def is_template_text(text: str) -> bool:
    markers = [
        "买入/卖出 [股票名称/代码]",
        "时间：\n- 价格：",
        "今日操作\n\n### 操作 1",
        "2026-06-29-盘后复盘RAW",
    ]
    return any(marker in text for marker in markers)


def clean_number(raw: str) -> float:
    text = raw.replace(",", "").replace("，", "").strip()
    text = text.replace("约", "").replace("元", "")
    return float(text)


def date_from_path(path: Path, month: str) -> str | None:
    pattern = month.replace("-", r"[-.]?")
    match = re.search(rf"{pattern}[-.]?(\d{{2}})", str(path))
    if match:
        return f"{month}-{match.group(1)}"
    compact = month.replace("-", "")
    match = re.search(rf"{compact}(\d{{2}})", str(path))
    if match:
        return f"{month}-{match.group(1)}"
    return None


@dataclass
class Evidence:
    path: str
    kind: str


@dataclass
class DayStats:
    date: str
    evidence: list[Evidence] = field(default_factory=list)
    pnl_candidates: list[dict] = field(default_factory=list)
    stocks: set[str] = field(default_factory=set)
    buy_count: int = 0
    sell_count: int = 0
    notes: list[str] = field(default_factory=list)

    def best_pnl(self) -> dict | None:
        priority = {
            "全口径": 1,
            "今日全口径": 1,
            "当日全口径": 1,
            "今日已实现盈亏": 2,
            "已实现盈亏": 2,
            "今日盈亏": 3,
            "当日盈亏": 3,
            "浮动盈亏": 4,
        }
        if not self.pnl_candidates:
            return None
        return sorted(self.pnl_candidates, key=lambda x: (priority.get(x["label"], 9), -abs(x["value"])))[0]


PNL_PATTERNS = [
    ("全口径", r"全口径[^+\-\d]{0,40}([+\-]\s*[\d,]+(?:\.\d+)?)"),
    ("今日全口径", r"今日全口径[^+\-\d]{0,40}([+\-]\s*[\d,]+(?:\.\d+)?)"),
    ("当日全口径", r"当日全口径[^+\-\d]{0,40}([+\-]\s*[\d,]+(?:\.\d+)?)"),
    ("今日已实现盈亏", r"今日已实现盈亏[^+\-\d]{0,60}([+\-]\s*[\d,]+(?:\.\d+)?)"),
    ("已实现盈亏", r"已实现盈亏[^+\-\d]{0,60}([+\-]\s*[\d,]+(?:\.\d+)?)"),
    ("今日盈亏", r"今日盈亏[^+\-\d]{0,60}([+\-]\s*[\d,]+(?:\.\d+)?)"),
    ("当日盈亏", r"当日盈亏[^+\-\d]{0,60}([+\-]\s*[\d,]+(?:\.\d+)?)"),
    ("今日浮盈", r"今日浮盈[^+\-\d]{0,60}([+\-]\s*[\d,]+(?:\.\d+)?)"),
    ("浮动盈亏", r"浮动盈亏[^+\-\d]{0,60}([+\-]\s*[\d,]+(?:\.\d+)?)"),
]


STOCK_LINE_RE = re.compile(r"(?:\|[^|\n]*)?(?:\b\d{6}\b|=\"\d{6}\").*?\|([^|\n]+?)\|")
CODE_NAME_RE = re.compile(r"(?:\b|=\")(\d{6})(?:\"|\b)\s*\|?\s*([\u4e00-\u9fa5A-Za-z0-9]+)")


def extract_pnl(text: str) -> list[dict]:
    values: list[dict] = []
    for label, pattern in PNL_PATTERNS:
        for match in re.finditer(pattern, text):
            raw = match.group(1).replace(" ", "")
            try:
                value = clean_number(raw)
            except ValueError:
                continue
            values.append({"label": label, "value": value})
    return values


def extract_stocks(text: str) -> set[str]:
    stocks: set[str] = set()
    for code, name in CODE_NAME_RE.findall(text):
        if name in {"证券名称", "名称", "代码"}:
            continue
        stocks.add(f"{name} {code}")
    for name in re.findall(r"(大唐发电|风华高科|银之杰|洁美科技|英维克|卫星化学|赢时胜|圣泉集团|诺德股份|天娱数科|粤电力A|豫能控股|同有科技|鹏鼎控股|金螳螂|东百集团|华能蒙电)", text):
        stocks.add(name)
    return stocks


def count_ops(text: str) -> tuple[int, int]:
    buy = len(re.findall(r"(?:融资买入|担保品买入|买入| 买 | 新开)", text))
    sell = len(re.findall(r"(?:担保品卖出|卖券还款|卖出|清仓| 卖 )", text))
    return buy, sell


def load_overrides(month: str) -> dict:
    path = ROOT / f"data/trading/{month}-manual-overrides.json"
    if not path.exists():
        return {"exclude_dates": {}, "days": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def is_weekend(iso_date: str) -> bool:
    y, m, d = [int(x) for x in iso_date.split("-")]
    return Date(y, m, d).weekday() >= 5


def collect(month: str, as_of: str | None) -> dict[str, DayStats]:
    days: dict[str, DayStats] = {}
    overrides = load_overrides(month)
    exclude_dates = overrides.get("exclude_dates", {})
    sources = [
        (ROOT / "raw/01-交割单", "交割单"),
        (ROOT / "raw/02-每日复盘", "复盘"),
    ]
    for base, kind in sources:
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            date = date_from_path(path, month)
            if not date:
                continue
            if as_of and date > as_of:
                continue
            if date in exclude_dates:
                continue
            if is_weekend(date):
                continue
            rel = path.relative_to(ROOT).as_posix()
            text = read_text(path)
            if not text.strip() or is_template_text(text):
                continue
            day = days.setdefault(date, DayStats(date=date))
            day.evidence.append(Evidence(rel, kind))
            for item in extract_pnl(text):
                item["source"] = rel
                day.pnl_candidates.append(item)
            day.stocks.update(extract_stocks(text))
            buy, sell = count_ops(text)
            day.buy_count += buy
            day.sell_count += sell
    for date, override in overrides.get("days", {}).items():
        if as_of and date > as_of:
            continue
        if date in exclude_dates:
            continue
        day = days.setdefault(date, DayStats(date=date))
        for item in override.get("pnl_candidates", []):
            day.pnl_candidates.append(item)
        for note in override.get("notes", []):
            day.notes.append(note)
    return days


def money(value: float | None) -> str:
    if value is None:
        return "待核验"
    return f"{value:+,.0f}"


def build_markdown(month: str, days: dict[str, DayStats]) -> str:
    rows = []
    pnl_values: list[float] = []
    win = loss = 0
    covered = 0
    for date in sorted(days):
        day = days[date]
        best = day.best_pnl()
        value = best["value"] if best else None
        label = best["label"] if best else "待核验"
        if value is not None:
            covered += 1
            pnl_values.append(value)
            if value > 0:
                win += 1
            elif value < 0:
                loss += 1
        stocks = "、".join(sorted(day.stocks))[:120] or "待核验"
        evidence = "<br>".join(f"`{x.path}`" for x in day.evidence[:4])
        if len(day.evidence) > 4:
            evidence += f"<br>...另 {len(day.evidence) - 4} 个"
        rows.append(
            f"| {date} | {label} | {money(value)} | {day.buy_count} | {day.sell_count} | {stocks} | {evidence} |"
        )

    total = sum(pnl_values) if pnl_values else None
    overrides = load_overrides(month)
    monthly_confirmed = overrides.get("monthly_pnl_confirmed") if isinstance(overrides, dict) else None
    monthly_confirmed_value = None
    if isinstance(monthly_confirmed, dict):
        monthly_confirmed_value = monthly_confirmed.get("value")
    monthly_diff = None
    if isinstance(monthly_confirmed_value, (int, float)) and isinstance(total, (int, float)):
        monthly_diff = monthly_confirmed_value - total
    avg = (sum(pnl_values) / len(pnl_values)) if pnl_values else None
    win_rate = (win / (win + loss) * 100) if (win + loss) else None
    worst = min(pnl_values) if pnl_values else None
    best = max(pnl_values) if pnl_values else None
    win_rate_text = f"{win_rate:.1f}%" if win_rate is not None else "待核验"

    top_issues = [
        "盘前信息准备不足：6/25 明确记录没有提前处理美光财报，导致存储主线踏空。",
        "退潮日仍有进攻冲动：6/26 强退潮日买入大唐发电，需作为纪律样本跟踪。",
        "非龙头格局过度：6/23 赢时胜从高位回落后才卖，复盘中已归因为贪心。",
        "高位/监管窗口博弈频繁：风华高科、大唐发电、粤电力A等都涉及异动或高位博弈，必须用 D+结果约束仓位。",
        "做对的样本：6/23 银之杰涨停卖出锁定利润，6/25 英维克重仓兑现，是有效卖点样本。",
    ]

    return f"""# {month} 交易统计初稿

更新时间：2026-06-28

## 定位

本页由 `raw/07-系统脚本/codex_build_monthly_trade_stats.py` 从 `raw/01-交割单` 和 `raw/02-每日复盘` 自动生成。

这是“证据级统计初稿”，不是最终券商净值表。能明确抽取的数值直接写入；格式不统一或证据不足的日期标记为待核验。

## 月度快照

| 指标 | 数值 |
|---|---:|
| 有 RAW 证据日期 | {len(days)} |
| 抽到盈亏的日期 | {covered} |
| 抽取口径合计 | {money(total)} |
| 用户确认月度盈亏 | {money(monthly_confirmed_value) if monthly_confirmed_value is not None else '待确认'} |
| 确认值-抽取值差额 | {money(monthly_diff) if monthly_diff is not None else '待确认'} |
| 平均单日盈亏 | {money(avg)} |
| 胜日 | {win} |
| 亏日 | {loss} |
| 粗略胜率 | {win_rate_text} |
| 最大单日盈利 | {money(best)} |
| 最大单日亏损 | {money(worst)} |

> 口径说明：优先级为全口径 > 已实现盈亏 > 今日盈亏 > 浮动盈亏。同一天多个来源冲突时，本页只取最高优先级候选。若存在“用户确认月度盈亏”，月度正式结果以用户确认值为准，抽取合计用于追溯日度证据和后续校准。

## 每日证据表

| 日期 | 盈亏口径 | 抽取盈亏 | 买入信号数 | 卖出信号数 | 涉及标的 | 主要证据 |
|---|---|---:|---:|---:|---|---|
{chr(10).join(rows)}

## 6月下旬高置信事实链

| 日期 | 事实 | 结论 |
|---|---|---|
| 2026-06-22 | 清圣泉集团、诺德股份；买银之杰、赢时胜；今日盈亏 +16,341 | 金融科技切换成功，但圣泉卖飞需要卖后验证 |
| 2026-06-23 | 卖银之杰、赢时胜，已实现约 +65,973；买大唐发电 | 银之杰卖点有效；赢时胜卖点拖延；大唐仓位偏重 |
| 2026-06-24 | 清大唐主仓亏约 -14,400；买英维克、卫星化学、风华高科 | 分歧日低吸英维克有效；大唐前日买入执行粗糙 |
| 2026-06-25 | 卖英维克、风华、卫星、大唐；买洁美科技、银之杰；全口径约 +25,603 | 英维克兑现优秀；盘前没处理美光财报导致存储踏空 |
| 2026-06-26 | 卖洁美、银之杰；买大唐、风华；全口径约 -9,463 | 强退潮日仍进攻，大唐属于重点纪律审计样本 |

## 需要写入错误库的候选

{chr(10).join(f"- {x}" for x in top_issues)}

## 需要写入 L4 模式库的样本

| 样本 | 初步模式 | 结果 | 后续处理 |
|---|---|---|---|
| 6/23 银之杰涨停卖出 | 金融情绪弹性套利 | 盈利兑现 | 升级为卖点正样本 |
| 6/24 英维克分歧日低吸 | 主线核心低吸 | 次日重仓盈利兑现 | 进入 A/B 级样本复核 |
| 6/25 洁美科技换仓 | 同主线内空间切换 | 当日浮盈，次日小盈退出 | 保留观察 |
| 6/26 大唐发电买入 | 退潮跷跷板情绪票 | 当日浮亏 | 降级或限制仓位，等待 6/29 结果验证 |
| 6/25 银之杰轮动博弈 | 金融轮动左侧 | 次日止损 | 标记为左侧轮动风险样本 |

## 下一步自动任务

1. 把本页高置信样本拆进 `wiki/05-错误库` 和 `wiki/04-L4交易模式与执行/L4模式验证总表-2026-06-28.md`。
2. 将 6/29 盘后交割单覆盖当前持仓后，自动更新本页和仪表盘。
3. 对待核验日期继续做标准化，不用手工猜。
"""


def main() -> int:
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--as-of", default="2026-06-28", help="Ignore evidence dated after this YYYY-MM-DD")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()

    ROOT = Path(args.root).resolve()
    days = collect(args.month, args.as_of)

    report = ROOT / f"wiki/09-统计与进化/{args.month}-交易统计初稿.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(build_markdown(args.month, days), encoding="utf-8")

    data = {
        "month": args.month,
        "generated_at": "2026-06-28",
        "monthly_pnl_confirmed": load_overrides(args.month).get("monthly_pnl_confirmed"),
        "days": {
            date: {
                "evidence": [e.__dict__ for e in day.evidence],
                "pnl_candidates": day.pnl_candidates,
                "best_pnl": day.best_pnl(),
                "stocks": sorted(day.stocks),
                "buy_count": day.buy_count,
                "sell_count": day.sell_count,
                "notes": day.notes,
            }
            for date, day in sorted(days.items())
        },
    }
    json_path = ROOT / f"data/trading/{args.month}-trade-statistics-draft.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"report={report.relative_to(ROOT)}")
    print(f"json={json_path.relative_to(ROOT)}")
    print(f"days={len(days)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
