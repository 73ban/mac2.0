#!/usr/bin/env python3
"""Prepare daily war-room and AI context files for one trading day.

Usage:
  python3 raw/07-系统脚本/codex_prepare_trading_day.py --date 2026-06-29

The script is conservative:
- It requires the daily candidate score table and auction checklist to exist.
- It does not overwrite existing daily files unless --force is passed.
- It generates the daily D+ validation task from the core validation queue.
- It updates .system/current-ai-context.json through codex_update_ai_context.py.
"""

from __future__ import annotations

import argparse
import re
import subprocess
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


def parse_meta(score_text: str) -> dict[str, str]:
    meta = {}
    patterns = {
        "generated_at": r"生成时间:\s*(.+)",
        "plan_trade_date": r"计划交易日:\s*(.+)",
        "evidence_trade_date": r"证据交易日:\s*(.+)",
        "market_state": r"市场状态:\s*(.+)",
        "position_permission": r"仓位权限:\s*(.+)",
        "data_gap": r"数据缺口:\s*(.+)",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, score_text)
        meta[key] = m.group(1).strip() if m else ""
    return meta


def parse_main_plan(score_text: str) -> tuple[str, list[str]]:
    primary = ""
    backups: list[str] = []
    m = re.search(r"^- Primary:\s*(.+)$", score_text, re.M)
    if m:
        primary = m.group(1).strip()
    m = re.search(r"^- Backups:\s*(.+)$", score_text, re.M)
    if m:
        backups = [x.strip() for x in re.split(r"/|,|，", m.group(1)) if x.strip()]
    return primary, backups


def parse_candidates(score_text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line in score_text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 13 or cells[0] in {"#", "---"}:
            continue
        if not cells[0].isdigit():
            continue
        out.append(
            {
                "rank": cells[0],
                "code": cells[1],
                "name": cells[2],
                "role": cells[3],
                "score": cells[4],
                "themes": cells[5],
                "catalysts": cells[6],
                "risk": cells[7],
                "trigger": cells[10],
                "downgrade": cells[11],
            }
        )
    return out


def parse_dplus_due(date: str) -> list[dict[str, str]]:
    queue = ROOT / "wiki/09-统计与进化/核心候选个股D+验证队列.md"
    rows: list[dict[str, str]] = []
    for line in read(queue).splitlines():
        if not (line.startswith("| ") and "`wiki/" in line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 11:
            continue
        code, name, role, evidence, d1, d3, d5, d10, d20, d30, card = cells[:11]
        due = []
        for label, value in [("D+1", d1), ("D+3", d3), ("D+5", d5), ("D+10", d10), ("D+20", d20), ("D+30", d30)]:
            if value == date:
                due.append(label)
        if due:
            rows.append(
                {
                    "code": code,
                    "name": name,
                    "role": role,
                    "evidence": evidence,
                    "node": "/".join(due),
                    "card": card.strip("`"),
                }
            )
    return rows


def fmt_candidate_list(candidates: list[dict[str, str]], start: int = 0, stop: int | None = None) -> str:
    selected = candidates[start:stop]
    if not selected:
        return "- 待补"
    return "\n".join(f"- {c['name']} `{c['code']}`：{c['role']}，{c['themes']}" for c in selected)


def build_dplus_task(date: str, due: list[dict[str, str]]) -> str:
    rows = "\n".join(
        f"| {x['code']} | {x['name']} | {x['node']} | {x['role']} | {x['evidence']} | `{x['card']}` |"
        for x in due
    ) or "| - | - | - | - | - | - |"
    sections = []
    for x in due:
        sections.append(
            f"""## {x['code']} {x['name']}

```yaml
validation_node: {x['node']}
price_action:
theme_action:
relative_strength:
volume_action:
decision:
rule_update:
```

验证重点：

- 是否强于对应板块。
- 是否验证 `{x['role']}` 的核心候选判断。
- 若弱于主线，应降低自动核心池权重。
"""
        )
    sections_text = "\n".join(sections) if sections else "## 今日无到期项\n\n- 无需回填。"
    return f"""# {date} D+验证任务

更新时间：{date}

## 定位

本页用于 {date} 盘后回填到期 D+验证结果。今日不是预测页，而是验证页。

## 今日到期项

| 代码 | 名称 | 节点 | 主线定位 | 证据日 | 骨架卡 |
|---|---|---|---|---|---|
{rows}

## 回填模板

```yaml
date: {date}
code:
name:
validation_node:
price_action: 强于预期 | 符合预期 | 弱于预期 | 证伪
theme_action: 主线强化 | 分歧修复 | 轮动 | 退潮 | 无反馈
relative_strength: 强于板块 | 跟随板块 | 弱于板块
volume_action: 放量承接 | 缩量强势 | 放量滞涨 | 缩量走弱
decision: 升级 | 保留观察 | 降级 | 归档
rule_update:
```

{sections_text}

## 回写要求

- [[核心候选个股D+验证队列]]
- [[20万小资金统计与进化仪表盘]]
- 相关正式核心候选档案
- 若验证失败，写入错误库或自动打分修正规则
"""


def build_war_control(date: str, meta: dict[str, str], primary: str, backups: list[str], candidates: list[dict[str, str]], due: list[dict[str, str]]) -> str:
    due_rows = "\n".join(f"| {x['code']} | {x['name']} | {x['node']} | {x['role']} | {x['evidence']} |" for x in due) or "| - | - | - | - | - |"
    return f"""# {date} 作战总控

更新时间：{date}

## 总目标约束

```yaml
account_goal: 20万小资金快速做大
ai_goal: 通过实盘、复盘、D+验证和错误库进化成超级短线高手
plan_trade_date: {date}
evidence_trade_date: {meta.get('evidence_trade_date') or '待补'}
position_permission: {meta.get('position_permission') or '待补'}
data_gap: {meta.get('data_gap') or '待补'}
```

## 今日作战摘要

- 主计划：{primary or '待补'}
- 备选：{ '、'.join(backups) if backups else '待补' }
- 观察：
{fmt_candidate_list(candidates, 3, 5)}

入口：

- [[{date}-AI上下文包]]
- [[当前持仓决策]]
- [[当前作战室工作页]]
- [[{date}-作战室候选票评分表]]
- `raw/03-每日计划/{date}-竞价监控清单.md`

## 盘前必须确认

```text
[ ] 最新真实持仓已确认
[ ] 今日市场状态已确认
[ ] 今日主线是否仍在前排已确认
[ ] 主计划是否仍成立已确认
[ ] 仓位权限是否仍为 {meta.get('position_permission') or '待补'} 已确认
[ ] 今日禁做清单已写
```

## 竞价执行口径

| 时间 | 看什么 | 动作 |
|---|---|---|
| 9:15 | 一字方向、核心票强弱、风险锚 | 只观察，不下结论 |
| 9:20 | 封单是否撤、风险锚是否恶化 | 撤单或风险恶化则降级 |
| 9:25 | 板块扩散、核心开盘质量 | 不支持主计划则只观察 |
| 9:31-9:50 | 分时承接、量能、板块反馈 | 只做计划内确认 |

## 买入前硬约束

1. 属于作战室主计划或备选计划。
2. L1 市场环境不退潮。
3. L2 主线仍在前排。
4. 个股仍是核心或前排，不是后排补涨。
5. L4 模式明确。
6. 已写退出条件。
7. 仓位不超过当日权限。

## 今日 D+验证任务

- [[{date}-D+验证任务]]

| 代码 | 名称 | 节点 | 主线定位 | 证据日 |
|---|---|---|---|---|
{due_rows}

## 盘后必须回填

```text
[ ] 交割单已先落 RAW
[ ] 当日交易已标注 L4 模式
[ ] 盈亏、仓位、最大回撤已记录
[ ] 今日错误已写入错误库候选
[ ] D+验证任务已更新
[ ] 明日作战室输入已准备
```

盘后入口：

- [[20万小资金统计与进化仪表盘]]
- [[D+验证总账规则]]
- [[核心候选个股D+验证队列]]
- [[盘后AI训练回写清单]]

## 禁止动作

- 不因资料多而重仓。
- 不因竞价一瞬间强就追后排。
- 不在持仓未确认时扩大风险。
- 不跳过 D+验证谈进化。
- 不做计划外临时冲动交易。
"""


def build_ai_context(date: str, meta: dict[str, str], primary: str, backups: list[str], candidates: list[dict[str, str]], due: list[dict[str, str]]) -> str:
    due_rows = "\n".join(f"| {x['code']} | {x['name']} | {x['node']} | {x['role']} |" for x in due) or "| - | - | - | - |"
    return f"""# {date} AI上下文包

更新时间：{date}

## 用途

这是 {date} 交易日，AI 在 Wiki 对话框回答盘前、盘中、盘后问题时的最小必读包。

## 今日目标

```yaml
account_goal: 20万小资金快速做大
ai_goal: 通过实盘、复盘、D+验证和错误库进化成超级短线高手
date: {date}
status: 作战日
position_permission: {meta.get('position_permission') or '待补'}
data_gap: {meta.get('data_gap') or '待补'}
```

## 今日必读入口

| 层级 | 文件 |
|---|---|
| 总目标 | `purpose.md` |
| 20万/AI总控 | `wiki/00-总纲/20万小资金做大与AI超短进化总控.md` |
| 当前持仓 | `wiki/06-持仓与资金管理/当前持仓决策.md` |
| 证据审计 | `wiki/06-持仓与资金管理/2026-06-28-交割单与复盘证据审计.md` |
| 今日作战 | `wiki/07-作战室/{date}-作战总控.md` |
| 当前作战室 | `wiki/07-作战室/当前作战室工作页.md` |
| 候选评分 | `wiki/07-作战室/{date}-作战室候选票评分表.md` |
| 竞价清单 | `raw/03-每日计划/{date}-竞价监控清单.md` |
| D+任务 | `wiki/09-统计与进化/{date}-D+验证任务.md` |
| 模式权限 | `wiki/04-L4交易模式与执行/20万小资金超短模式总控.md` |
| 题材生命周期 | `wiki/02-L2方向题材/核心题材生命周期/核心题材生命周期总表-2026-06-28.md` |
| 统计进化 | `wiki/09-统计与进化/20万小资金统计与进化仪表盘.md` |

## 今日作战摘要

主计划：

- {primary or '待补'}

备选：

{chr(10).join('- ' + b for b in backups) if backups else '- 待补'}

观察：

{fmt_candidate_list(candidates, 3, 5)}

## 盘前启动包

| 模块 | 内容 | 读取位置 |
|---|---|---|
| 当前持仓 | 以最新交割单和当前持仓决策为准，未确认则不得扩大风险 | `wiki/06-持仓与资金管理/当前持仓决策.md` |
| 今日风险 | 退潮、监管、外围、公告负反馈、持仓风险锚 | `wiki/07-作战室/{date}-作战总控.md` |
| 昨日错误 | 优先读最新错误候选和复盘质量缺项 | `wiki/05-错误库/` |
| 作战室候选 | 只看评分表和竞价清单里的计划内标的 | `wiki/07-作战室/{date}-作战室候选票评分表.md` |
| 必看新闻 | 高分消息催化、公告事件、互动问答、龙虎榜 | `wiki/07-作战室/{date}-消息催化统一评分.md` |
| 禁止交易清单 | 后排补涨、计划外冲动、退潮日扩大仓位、持仓未确认加仓 | 本页和作战总控 |

## 今日 D+验证

| 代码 | 名称 | 节点 | 主线定位 |
|---|---|---|---|
{due_rows}

## AI回答时的动作权限

| 情况 | AI动作 |
|---|---|
| 持仓未确认 | 必须提示数据缺口，不给扩大风险建议 |
| 竞价不支持主计划 | 主计划降级为观察 |
| 风险锚恶化 | 降低仓位权限或暂停 |
| 主线确认且个股强 | 只讨论计划内动作 |
| 计划外标的出现 | 先问是否进入作战室，不直接建议买入 |
| 盘后有交易 | 要求交割单先进 RAW，再统计和复盘 |

## 禁止

- 不允许把主计划自动理解为必须买。
- 不允许把备选票当成并列主计划。
- 不允许在持仓未确认时做加仓建议。
- 不允许跳过 D+验证评价到期项。
- 不允许根据资料卡直接推荐后排票。
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--force", action="store_true", help="overwrite existing daily files")
    parser.add_argument("--skip-context-update", action="store_true", help="do not call codex_update_ai_context.py")
    args = parser.parse_args()

    date = args.date
    score_path = ROOT / f"wiki/07-作战室/{date}-作战室候选票评分表.md"
    auction_path = ROOT / f"raw/03-每日计划/{date}-竞价监控清单.md"
    if not score_path.exists():
        print(f"missing score table: {score_path.relative_to(ROOT)}", file=sys.stderr)
        return 2
    if not auction_path.exists():
        print(f"missing auction checklist: {auction_path.relative_to(ROOT)}", file=sys.stderr)
        return 2

    score_text = read(score_path)
    meta = parse_meta(score_text)
    primary, backups = parse_main_plan(score_text)
    candidates = parse_candidates(score_text)
    due = parse_dplus_due(date)

    outputs = [
        (ROOT / f"wiki/09-统计与进化/{date}-D+验证任务.md", build_dplus_task(date, due)),
        (ROOT / f"wiki/07-作战室/{date}-作战总控.md", build_war_control(date, meta, primary, backups, candidates, due)),
        (ROOT / f"wiki/07-作战室/{date}-AI上下文包.md", build_ai_context(date, meta, primary, backups, candidates, due)),
    ]
    written = []
    skipped = []
    for path, content in outputs:
        if write(path, content, force=args.force):
            written.append(str(path.relative_to(ROOT)))
        else:
            skipped.append(str(path.relative_to(ROOT)))

    if not args.skip_context_update:
        updater = ROOT / "raw/07-系统脚本/codex_update_ai_context.py"
        cmd = [sys.executable, str(updater), "--date", date]
        if args.force:
            cmd.append("--allow-missing")
        subprocess.run(cmd, cwd=str(ROOT), check=True)

    print(f"date={date}")
    print(f"candidates={len(candidates)}")
    print(f"dplus_due={len(due)}")
    print(f"written={len(written)}")
    for item in written:
        print(f"+ {item}")
    print(f"skipped={len(skipped)}")
    for item in skipped:
        print(f"= {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
