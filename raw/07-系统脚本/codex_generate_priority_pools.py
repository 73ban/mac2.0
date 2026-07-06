import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TODAY = datetime.now().strftime("%Y-%m-%d")
CARD_ROOT = ROOT / "wiki" / "08-信息来源" / "RAW独立知识卡" / TODAY


def read_card(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    def grab(label: str) -> str:
        m = re.search(rf"- {label}：(.+)", text)
        return m.group(1).strip() if m else ""
    title = text.splitlines()[0].lstrip("#").strip() if text else path.stem
    return {
        "path": path,
        "rel": str(path.relative_to(ROOT)).replace("\\", "/"),
        "title": title,
        "date": grab("日期"),
        "source": grab("来源"),
        "grade": grab("价值等级"),
        "themes": [x for x in grab("题材").split("、") if x and "无明确" not in x],
        "stocks": [x for x in grab("个股").split("、") if x and "无明确" not in x],
        "methods": [x for x in grab("模式").split("、") if x and "无明确" not in x],
        "summary": re.search(r"## 结构化摘要\s+([\s\S]+?)\s+## 关联标签", text).group(1).strip() if re.search(r"## 结构化摘要\s+([\s\S]+?)\s+## 关联标签", text) else "",
    }


def md_table(rows: list[list[str]]) -> str:
    if not rows:
        return "无。"
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * len(rows[0])) + "|"]
    for row in rows[1:]:
        out.append("| " + " | ".join(str(x).replace("\n", " ") for x in row) + " |")
    return "\n".join(out)


def is_stock_noise(stock: str) -> bool:
    if not stock:
        return True
    if re.fullmatch(r"\d{6}", stock):
        return True
    if re.search(r"[A-Za-z]", stock):
        return True
    if len(stock) > 8:
        return True
    if stock in {"AI", "GPU", "PCB", "CPO"}:
        return True
    return False


TRUSTED_SOURCES = {"知识星球", "公众号", "ymj0418", "小睿睿投资学", "股痴流沙河", "大作手奇衡三", "作手奇衡三的冲天槊"}
VALID_METHODS = {
    "题材主升",
    "连板接力",
    "趋势抱团",
    "冰点修复",
    "弱转强",
    "低吸",
    "打板",
    "半路",
    "出监管",
    "绕异动",
    "并购重组预期差",
    "纪律风控",
    "市场情绪周期",
}


def main() -> None:
    cards = [read_card(p) for p in CARD_ROOT.glob("*.md")]
    high = [c for c in cards if c["grade"] in {"A", "B"} and c["source"] in TRUSTED_SOURCES]
    by_stock = defaultdict(list)
    by_theme = defaultdict(list)
    by_method = defaultdict(list)
    for c in high:
        for s in c["stocks"]:
            if not is_stock_noise(s):
                by_stock[s].append(c)
        for t in c["themes"]:
            by_theme[t].append(c)
        for m in c["methods"]:
            if m in VALID_METHODS:
                by_method[m].append(c)

    out_root = ROOT / "wiki" / "07-作战室" / "资料池"
    out_root.mkdir(parents=True, exist_ok=True)
    stock_path = ROOT / "wiki" / "03-L3个股档案" / f"高价值个股资料池-{TODAY}.md"
    theme_path = ROOT / "wiki" / "02-L2方向题材" / f"高价值题材资料池-{TODAY}.md"
    method_path = ROOT / "wiki" / "04-L4交易模式与执行" / f"游资心得正式模式候选-{TODAY}.md"
    action_path = out_root / f"高价值资料优先处理清单-{TODAY}.md"

    stock_rows = [["个股", "资料数", "A级数", "共振题材", "共振模式", "代表资料"]]
    for stock, items in sorted(by_stock.items(), key=lambda kv: (len(kv[1]), sum(1 for x in kv[1] if x["grade"] == "A")), reverse=True):
        if len(items) < 2:
            continue
        themes = sorted({t for c in items for t in c["themes"]})
        methods = sorted({m for c in items for m in c["methods"]})
        rep = sorted(items, key=lambda x: (x["grade"] == "A", x["date"]), reverse=True)[0]
        stock_rows.append([stock, str(len(items)), str(sum(1 for x in items if x["grade"] == "A")), "、".join(themes[:6]), "、".join(methods[:6]), rep["rel"]])
    stock_path.write_text(
        "\n".join(
            [
                f"# 高价值个股资料池-{TODAY}",
                "",
                "本页从独立知识卡中筛选 A/B 级、资料数不少于 2 的个股。用途：突发新闻和作战室候选股出现时，优先查这里。",
                "",
                md_table(stock_rows),
                "",
                "## 使用规则",
                "",
                "- 资料数多不等于可以买，只代表 WIKI 已有沉淀。",
                "- A级数多、题材和模式共振强的个股，优先进入作战室复核。",
            ]
        ),
        encoding="utf-8",
    )

    theme_rows = [["题材", "资料数", "A级数", "代表模式", "代表个股", "代表资料"]]
    for theme, items in sorted(by_theme.items(), key=lambda kv: (len(kv[1]), sum(1 for x in kv[1] if x["grade"] == "A")), reverse=True):
        methods = sorted({m for c in items for m in c["methods"]})
        stocks = sorted({s for c in items for s in c["stocks"] if not is_stock_noise(s)})
        rep = sorted(items, key=lambda x: (x["grade"] == "A", x["date"]), reverse=True)[0]
        theme_rows.append([theme, str(len(items)), str(sum(1 for x in items if x["grade"] == "A")), "、".join(methods[:8]), "、".join(stocks[:12]), rep["rel"]])
    theme_path.write_text(
        "\n".join(
            [
                f"# 高价值题材资料池-{TODAY}",
                "",
                "本页用于判断哪些题材已有足够资料沉淀，可在突发催化时快速映射个股和模式。",
                "",
                md_table(theme_rows),
            ]
        ),
        encoding="utf-8",
    )

    method_rows = [["模式", "资料数", "A级数", "适用题材", "代表个股", "代表资料"]]
    for method, items in sorted(by_method.items(), key=lambda kv: (len(kv[1]), sum(1 for x in kv[1] if x["grade"] == "A")), reverse=True):
        themes = sorted({t for c in items for t in c["themes"]})
        stocks = sorted({s for c in items for s in c["stocks"] if not is_stock_noise(s)})
        rep = sorted(items, key=lambda x: (x["grade"] == "A", x["date"]), reverse=True)[0]
        method_rows.append([method, str(len(items)), str(sum(1 for x in items if x["grade"] == "A")), "、".join(themes[:8]), "、".join(stocks[:12]), rep["rel"]])
    method_path.write_text(
        "\n".join(
            [
                f"# 游资心得正式模式候选-{TODAY}",
                "",
                "本页是从独立知识卡中筛出的正式模式候选池。进入《游资模式库总表》前，还需要盘面验证和用户交易统计验证。",
                "",
                md_table(method_rows),
            ]
        ),
        encoding="utf-8",
    )

    top_stock = stock_rows[1:41]
    top_theme = theme_rows[1:16]
    top_method = method_rows[1:20]
    action_path.write_text(
        "\n".join(
            [
                f"# 高价值资料优先处理清单-{TODAY}",
                "",
                "## 下一步优先级",
                "",
                "1. 先处理 A 级资料集中的题材和个股，服务突发新闻映射。",
                "2. 再处理游资心得中高频模式，升级为正式模式卡。",
                "3. 最后处理 B 级资料，作为个股档案和题材档案补充。",
                "",
                "## 优先题材",
                "",
                md_table(theme_rows[:1] + top_theme),
                "",
                "## 优先个股",
                "",
                md_table(stock_rows[:1] + top_stock),
                "",
                "## 优先模式",
                "",
                md_table(method_rows[:1] + top_method),
            ]
        ),
        encoding="utf-8",
    )

    print(json.dumps({"stocks": len(stock_rows) - 1, "themes": len(theme_rows) - 1, "methods": len(method_rows) - 1, "action": str(action_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
