#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LINT_JSON = ROOT / f"raw/11-Codex分析产物/交易模式质量检查/{date.today().isoformat()}/mode-page-lint.json"
OUT_DIR = ROOT / f"raw/11-Codex分析产物/交易模式结构补齐/{date.today().isoformat()}"
MODE_DIR = ROOT / "wiki/04-L4交易模式与执行/游资交易模式卡片库"


SECTION_BLOCKS = {
    "## 别名": """## 别名

- 淘股吧叫法：待继续从淘股吧/实盘赛/高手分享补充。
- 游资号叫法：待继续从公众号/复盘材料补充。
- 用户复盘叫法：默认按本页标准名归因，后续可追加用户口述叫法。
""",
    "## 适用环境": """## 适用环境

- 市场状态：继承本页已有“适用条件/适用市场”描述，后续用每日情绪周期校准。
- 情绪周期：待按启动、主升、分歧、修复、退潮分层统计。
- 题材阶段：待按新题材试错、主线确认、主升扩散、末端补涨、退潮回流分层统计。
- 股票角色：待按龙头、前排、容量中军、补涨、后排分层统计。
""",
    "## 行情分层胜率": """## 行情分层胜率

同一个模式在不同行情下成功率不同，先占位，后续只用交割单和D+验证填真实统计，不编造胜率。

| 市场状态 | 情绪周期 | 题材阶段 | 股票角色 | 样本数 | 胜率 | 平均收益 | 最大回撤 | 结论 |
|---|---|---|---|---:|---:|---:|---:|---|
| 题材主升 | 待统计 | 待统计 | 待统计 | 0 | 待统计 | 待统计 | 待统计 | 待验证 |
| 情绪修复 | 待统计 | 待统计 | 待统计 | 0 | 待统计 | 待统计 | 待统计 | 待验证 |
| 混沌轮动 | 待统计 | 待统计 | 待统计 | 0 | 待统计 | 待统计 | 待统计 | 待验证 |
| 退潮期 | 待统计 | 待统计 | 待统计 | 0 | 待统计 | 待统计 | 待统计 | 待验证 |
""",
    "## 有效条件": """## 有效条件

- 以本页已有“买入条件/适用条件/竞价确认”为第一版有效条件。
- 必须能和当日市场环境、主线强度、股票角色、买入方式对应。
- 后续通过D+1/D+3/D+5验证，连续有效后再升级为可作战规则。
""",
    "## 失效条件": """## 失效条件

- 以本页已有“禁用条件/卖出退出条件/常见错误”为第一版失效条件。
- 若板块无扩散、核心票走弱、热榜退潮或盘口不承接，本模式降权。
- 若出现消息澄清、监管、异动压制、亏钱效应扩散，本模式不得机械套用。
""",
    "## 买点": """## 买点

- 竞价：只记录是否强于同题材核心、是否超预期，不能只看高开。
- 开盘：看5到10分钟承接、主动性和板块共振。
- 盘中：只在模式触发条件完整时归因，不能事后硬套。
- 尾盘：仅用于回流确认、避险或做T，不默认等同于主买点。
""",
    "## 卖点": """## 卖点

- 主动卖点：达到模式预期但不能继续带动板块、冲高放量回落、封板失败。
- 被动止损：买入逻辑被证伪、核心票补跌、板块退潮、热榜明显下滑。
- 次日不及预期：竞价弱于板块或低开低走时，按复盘规则优先处理。
""",
    "## 仓位权限": """## 仓位权限

- 观察仓：模式样本不足、置信度低、只适合验证。
- 标准仓：模式条件完整，且市场环境、主线、股票角色共振。
- 禁止重仓条件：退潮期、后排票、消息纯度不足、盘口不承接、D+验证长期无效。
""",
    "## 统计字段": """## 统计字段

- `mode_standard_name`
- `mode_alias_used`
- `mode_source`: 用户口述 / Codex推定 / 盘后修正
- `mode_confidence`: high / medium / low
- `market_state`
- `emotion_cycle`
- `theme_stage`
- `stock_role`
- `entry_type`
- `exit_type`
- `position_size`
- `d1_return`
- `d3_return`
- `d5_return`
- `max_drawdown`
- `matched_rules`
- `failed_rules`
""",
    "## 修正记录": """## 修正记录

后期理解变化时，只追加，不删除旧内容。

| 日期 | 修正类型 | 新增/修正内容 | 原因 | 影响范围 |
|---|---|---|---|---|
| {today} | 结构补齐 | 补齐模式页标准统计章节 | 为逐笔交易归因、D+验证、胜率分层提供统一字段 | 本模式后续统计 |
""",
    "## 当前等级": """## 当前等级

- 当前等级：RAW观察。
- 升级条件：至少有用户交割单样本、D+验证、适用/失效条件复核。
- 降级条件：连续误判、只适合特定行情、无法解释买卖点。
""",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_section(section: str) -> str:
    block = SECTION_BLOCKS[section]
    return block.format(today=date.today().isoformat())


def backfill_page(path: Path, missing: list[str]) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    appended: list[str] = []
    blocks: list[str] = []
    for section in missing:
        if section in text or section not in SECTION_BLOCKS:
            continue
        blocks.append(render_section(section).rstrip())
        appended.append(section)
    if not blocks:
        return appended
    suffix = f"\n\n---\n\n## {date.today().isoformat()} 标准结构补齐\n\n"
    suffix += "以下章节为系统化归因和统计补齐字段，只追加，不覆盖本页原有判断。\n\n"
    suffix += "\n\n".join(blocks)
    path.write_text(text.rstrip() + suffix + "\n", encoding="utf-8")
    return appended


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%H%M%S")
    payload = read_json(LINT_JSON)
    changed = []
    for item in payload.get("items", []):
        if item.get("ok"):
            continue
        path = ROOT / item["file"]
        appended = backfill_page(path, item.get("missing") or [])
        if appended:
            changed.append({"file": item["file"], "appended": appended})
    cumulative = []
    for path in sorted(MODE_DIR.glob("*.md")):
        if "索引" in path.name:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "标准结构补齐" in text:
            cumulative.append(path.relative_to(ROOT).as_posix())
    result = {
        "schema": "73wiki-mode-page-structure-backfill-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "changed_count": len(changed),
        "changed": changed,
        "cumulative_backfilled_count": len(cumulative),
        "cumulative_backfilled": cumulative,
    }
    (OUT_DIR / "mode-page-structure-backfill.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / f"mode-page-structure-backfill-{stamp}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# {date.today().isoformat()} 交易模式页面结构补齐",
        "",
        f"- 生成时间：{result['generatedAt']}",
        f"- 本次新增补齐页面数：{len(changed)}",
        f"- 累计已补齐页面数：{len(cumulative)}",
        "- 口径：只追加缺失标准章节，不删除旧内容，不编造胜率。",
        "",
        "| 模式页 | 追加章节 |",
        "|---|---|",
    ]
    for row in changed:
        lines.append(f"| `{row['file']}` | {'、'.join(x.replace('## ', '') for x in row['appended'])} |")
    if not changed:
        lines.append("| 无 | 无 |")
    md = "\n".join(lines) + "\n"
    (OUT_DIR / "mode-page-structure-backfill.md").write_text(md, encoding="utf-8")
    (OUT_DIR / f"mode-page-structure-backfill-{stamp}.md").write_text(md, encoding="utf-8")
    print(json.dumps({"ok": True, "changed": len(changed), "output": str((OUT_DIR / 'mode-page-structure-backfill.md').relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
