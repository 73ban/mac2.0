#!/usr/bin/env python3
"""Prepare post-market review skeletons for one trading day.

Usage:
  python3 raw/07-系统脚本/codex_prepare_postmarket.py --date 2026-06-29

This script does not invent market conclusions. It creates the required
containers so trades, D+ validation, errors, and statistics can be filled in
after the close.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def write(path: Path, content: str, force: bool = False) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def extract_yaml_value(text: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def parse_watchlist(date: str) -> list[dict[str, str]]:
    score = ROOT / f"wiki/07-作战室/{date}-作战室候选票评分表.md"
    out: list[dict[str, str]] = []
    for line in read(score).splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 13 or not cells[0].isdigit():
            continue
        out.append(
            {
                "rank": cells[0],
                "code": cells[1],
                "name": cells[2],
                "role": cells[3],
                "score": cells[4],
                "themes": cells[5],
                "risk": cells[7],
            }
        )
    return out


def parse_dplus_task(date: str) -> list[dict[str, str]]:
    task = ROOT / f"wiki/09-统计与进化/{date}-D+验证任务.md"
    out: list[dict[str, str]] = []
    for line in read(task).splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6 or cells[0] in {"代码", "---", "-"}:
            continue
        if not re.match(r"^\d{6}$", cells[0]):
            continue
        out.append(
            {
                "code": cells[0],
                "name": cells[1],
                "node": cells[2],
                "role": cells[3],
                "evidence": cells[4],
                "card": cells[5].strip("`"),
            }
        )
    return out


def build_raw_review(date: str, watchlist: list[dict[str, str]], dplus: list[dict[str, str]]) -> str:
    watch_rows = "\n".join(
        f"| {x['code']} | {x['name']} | {x['role']} | {x['themes']} |  |  | |"
        for x in watchlist
    ) or "| - | - | - | - | - | - | - |"
    dplus_rows = "\n".join(
        f"| {x['code']} | {x['name']} | {x['node']} | {x['role']} |  |  | |"
        for x in dplus
    ) or "| - | - | - | - | - | - | - |"
    return f"""# {date} 盘后复盘RAW

## 基本信息

```yaml
trade_date: {date}
account_goal: 20万小资金快速做大
ai_goal: 通过实盘、复盘、D+验证和错误库进化成超级短线高手
source_type: postmarket_raw_skeleton
```

## 今日市场环境

| 项目 | 盘后回填 |
|---|---|
| 指数状态 |  |
| 成交额 |  |
| 情绪阶段 |  |
| 涨停/跌停 |  |
| 主线 |  |
| 风险点 |  |

## 今日作战计划回看

| 代码 | 名称 | 盘前角色 | 题材 | 竞价反馈 | 盘中反馈 | 结论 |
|---|---|---|---|---|---|---|
{watch_rows}

## 今日实际交易

| 时间 | 代码 | 名称 | 买/卖 | 价格 | 数量 | 金额 | 仓位 | 模式 | 是否计划内 | 结果 |
|---|---|---|---|---:|---:|---:|---:|---|---|---|
|  |  |  |  |  |  |  |  |  |  |  |

## 持仓与资金

```yaml
start_equity:
end_equity:
daily_pnl:
daily_return:
max_drawdown:
cash:
position_value:
```

## D+验证回填

| 代码 | 名称 | 节点 | 主线定位 | 价格表现 | 相对强弱 | 结论 |
|---|---|---|---|---|---|---|
{dplus_rows}

## 今日错误候选

| 错误类型 | 是否发生 | 证据 | 处理 |
|---|---|---|---|
| 模式外交易 |  |  |  |
| 退潮期硬做 |  |  |  |
| 追后排 |  |  |  |
| 卖点拖延 |  |  |  |
| 低确定性重仓 |  |  |  |

## 明日输入

- 明日需要继续跟踪的主线：
- 明日需要降级的标的：
- 明日仓位权限建议：
- 需要写入 WIKI 的规则变化：
"""


def build_stats_page(date: str, watchlist: list[dict[str, str]], dplus: list[dict[str, str]]) -> str:
    mode_rows = "\n".join(
        f"| {x['code']} {x['name']} | {x['role']} |  |  | |"
        for x in watchlist
    ) or "| - | - | - | - | - |"
    dplus_rows = "\n".join(
        f"| {x['code']} | {x['name']} | {x['node']} | 待回填 | |"
        for x in dplus
    ) or "| - | - | - | - | - |"
    return f"""# {date} 统计与AI训练回写

更新时间：{date}

## 总目标

- 账户目标：20万小资金快速做大。
- AI目标：通过实盘、复盘、D+验证和错误库进化成超级短线高手。

## 账户统计

```yaml
trade_date: {date}
start_equity:
end_equity:
daily_return:
month_return:
max_drawdown:
win_loss:
main_mode:
main_error:
d_plus_updated:
rule_update:
tomorrow_permission:
```

## 模式归因

| 标的 | 盘前角色 | 实际模式 | 结果 | 后续 |
|---|---|---|---|---|
{mode_rows}

## D+验证

| 代码 | 名称 | 节点 | 结果 | 规则影响 |
|---|---|---|---|---|
{dplus_rows}

## AI自我修正

1. 盘前判断中被验证的内容：
2. 盘前判断中被证伪的内容：
3. 需要降权的自动评分或资料判断：
4. 明日 AI 应该更激进、更保守，还是保持标准试错：
"""


def build_sell_validation(date: str) -> str:
    return f"""# {date} 卖出后验证

- 生成时间：{date}
- 卖出样本：待回填
- 重点回看：待回填
- 卖早：待回填
- 卖晚：待回填
- 基本合理：待回填
- 待补行情：待回填

## 重点回看 / 超预期继续走强

- 待回填

## 卖点偏早

- 待回填

## 卖点偏慢

- 待回填

## 卖点基本合理

- 待回填

## 待补行情回放

- 待回填
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    date = args.date
    war = ROOT / f"wiki/07-作战室/{date}-作战总控.md"
    dtask = ROOT / f"wiki/09-统计与进化/{date}-D+验证任务.md"
    if not war.exists():
        print(f"missing war control: {war.relative_to(ROOT)}", file=sys.stderr)
        return 2
    if not dtask.exists():
        print(f"missing D+ task: {dtask.relative_to(ROOT)}", file=sys.stderr)
        return 2

    watchlist = parse_watchlist(date)
    dplus = parse_dplus_task(date)
    outputs = [
        (ROOT / f"raw/02-每日复盘/{date}-盘后复盘RAW.md", build_raw_review(date, watchlist, dplus)),
        (ROOT / f"wiki/09-统计与进化/{date}-统计与AI训练回写.md", build_stats_page(date, watchlist, dplus)),
        (ROOT / f"wiki/09-统计与进化/卖出后验证/{date}-卖出后验证.md", build_sell_validation(date)),
    ]

    written = []
    skipped = []
    for path, content in outputs:
        if write(path, content, force=args.force):
            written.append(str(path.relative_to(ROOT)))
        else:
            skipped.append(str(path.relative_to(ROOT)))

    print(f"date={date}")
    print(f"watchlist={len(watchlist)}")
    print(f"dplus={len(dplus)}")
    print(f"written={len(written)}")
    for item in written:
        print(f"+ {item}")
    print(f"skipped={len(skipped)}")
    for item in skipped:
        print(f"= {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
