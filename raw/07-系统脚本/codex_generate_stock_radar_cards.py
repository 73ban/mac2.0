import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TODAY = datetime.now().strftime("%Y-%m-%d")
SRC = ROOT / "wiki" / "03-L3个股档案" / f"高价值个股资料池-{TODAY}.md"
OUT = ROOT / "wiki" / "03-L3个股档案" / "作战室个股雷达卡"


def parse_rows() -> list[dict]:
    text = SRC.read_text(encoding="utf-8", errors="ignore")
    rows = []
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("|---") or "个股" in line and "资料数" in line:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 6:
            continue
        try:
            docs = int(parts[1])
            a_docs = int(parts[2])
        except Exception:
            continue
        rows.append(
            {
                "stock": parts[0],
                "docs": docs,
                "a_docs": a_docs,
                "themes": parts[3],
                "methods": parts[4],
                "representative": parts[5],
            }
        )
    return rows


def card(row: dict) -> str:
    stock = row["stock"]
    themes = [x for x in row["themes"].split("、") if x]
    methods = [x for x in row["methods"].split("、") if x]
    role = "待定"
    if "光通信光纤" in themes or "AI算力" in themes:
        role = "AI/算力/光通信资料池核心候选"
    if "PCB覆铜板" in themes:
        role = "PCB/覆铜板资料池候选"
    if "机器人" in themes:
        role = "机器人资料池候选"
    if "并购重组" in themes:
        role = "并购重组/事件驱动候选"
    return "\n".join(
        [
            f"# {stock}-作战室个股雷达卡-{TODAY}",
            "",
            "## 资料强度",
            "",
            f"- 资料数：{row['docs']}",
            f"- A级资料数：{row['a_docs']}",
            f"- 代表资料：{row['representative']}",
            "",
            "## 关联方向",
            "",
            f"- 题材：{row['themes']}",
            f"- 模式：{row['methods']}",
            f"- 当前角色：{role}",
            "",
            "## 作战室用途",
            "",
            "- 突发新闻出现时，优先检查该股是否与新闻题材、产业链和市场情绪共振。",
            "- 盘前作战室只在该股同时满足题材强度、盘口强度、人气强度和模式匹配时纳入候选。",
            "- 如果该股出现在多平台热门榜、龙虎榜、竞价超预期或主线扩散中，应提升复核优先级。",
            "",
            "## 竞价观察",
            "",
            "- 9:15：是否超预期，是否有一字/大幅高开/风险低开。",
            "- 9:20：强度是否真实，是否撤单，板块是否同步。",
            "- 9:25：是否符合计划，是否进入开盘后确认池。",
            "",
            "## 禁止条件",
            "",
            "- 只有资料多，但当日题材不强，不进入主计划。",
            "- 只有研报逻辑，没有短线资金确认，不重仓。",
            "- 高开低走、放量滞涨、板块后排大面时，降级观察。",
            "- 没有退出条件，不允许开仓。",
            "",
            "## 后续跟踪",
            "",
            "- 若进入作战室，必须加入 D+1/D+3/D+5/D+10 跟踪池。",
            "- 若实际交易，必须记录主模式、买入方式、仓位、持股周期和盈亏。",
            "",
        ]
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = parse_rows()
    priority = [r for r in rows if r["a_docs"] >= 8 or r["docs"] >= 10]
    index = [
        f"# 作战室个股雷达卡索引-{TODAY}",
        "",
        "| 个股 | 资料数 | A级资料数 | 题材 | 模式 | 文件 |",
        "|---|---:|---:|---|---|---|",
    ]
    for row in priority:
        path = OUT / f"{row['stock']}-作战室个股雷达卡-{TODAY}.md"
        path.write_text(card(row), encoding="utf-8")
        index.append(
            f"| {row['stock']} | {row['docs']} | {row['a_docs']} | {row['themes']} | {row['methods']} | {path.relative_to(ROOT).as_posix()} |"
        )
    index_path = OUT / f"作战室个股雷达卡索引-{TODAY}.md"
    index_path.write_text("\n".join(index), encoding="utf-8")
    print(f"stock_radar_cards={len(priority)} index={index_path}")


if __name__ == "__main__":
    main()
