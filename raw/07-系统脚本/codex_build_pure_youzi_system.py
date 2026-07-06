import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "raw" / "05-研报新闻"
OUT = ROOT / "wiki" / "04-L4交易模式与执行" / "游资认知体系" / "高纯度游资心得"
TODAY = datetime.now().strftime("%Y-%m-%d")

SOURCES = {
    "淘股吧", "安静拆主线", "小睿睿投资学", "股痴流沙河", "ymj0418", "大作手奇衡三", "作手奇衡三的冲天槊",
    "17学无止境", "鄂华少", "圣广鸿鹄复盘", "盘面说", "只核大a学生", "大蟒蛇神",
}

SECTIONS = {
    "01-市场理解": ["市场", "指数", "情绪", "赚钱效应", "亏钱效应", "退潮", "冰点", "分歧", "修复", "高潮", "轮动", "量能"],
    "02-题材理解": ["题材", "主线", "分支", "龙头", "中军", "核心", "补涨", "预期差", "催化", "发酵", "兑现", "跷跷板"],
    "03-模式方法": ["低吸", "半路", "打板", "连板", "接力", "弱转强", "反包", "回封", "二波", "绕异动", "出监管", "一字"],
    "04-买卖点执行": ["竞价", "盘口", "分时", "开盘", "尾盘", "买点", "卖点", "承接", "高开", "低开", "封单", "炸板"],
    "05-仓位风控": ["仓位", "空仓", "止损", "止盈", "纪律", "风险", "回撤", "亏损", "大面", "核按钮", "防守"],
    "06-心态认知": ["心态", "认知", "人性", "贪婪", "恐惧", "执行", "耐心", "自控", "反思", "道心", "修炼"],
    "07-案例训练": ["复盘", "实盘", "账户", "龙虎榜", "席位", "老师", "买入", "卖出", "涨停", "跌停", "炸板"],
}


RULES = {
    "01-市场理解": [
        "先定市场状态，再定仓位；市场不支持时，模式再好也要降级。",
        "高潮不是继续追的理由，高潮后最重要是看分歧是否良性。",
        "冰点不是马上抄底的理由，冰点后要看核心票是否止跌和修复。",
        "短线赚钱效应看核心、前排、连板高度和断板反馈，不看单日涨停数。",
    ],
    "02-题材理解": [
        "题材要分清主线、支线、轮动和杂毛，不能只因为消息多就重仓。",
        "主线必须有核心股、中军、补涨和板块宽度，单票强不等于主线强。",
        "预期差来自市场尚未充分定价，高潮一致后预期差会快速消失。",
        "题材分歧日要看核心承接，核心不倒，后续才有修复基础。",
    ],
    "03-模式方法": [
        "低吸、半路、打板是确认程度不同，不是固定偏好。",
        "连板接力只在情绪支持时做，退潮期接力容易大面。",
        "弱转强必须有板块和盘口配合，否则只是高开诱多。",
        "绕异动和出监管是用户近期有效模式，但必须严格跟踪失效信号。",
    ],
    "04-买卖点执行": [
        "竞价只能确认计划，不能制造计划。",
        "9:15看方向，9:20看真假，9:25看最终预期。",
        "买点必须有承接和板块配合，孤立拉升降低权重。",
        "卖点看低于预期、风险锚恶化和模式失效，不靠幻想。",
    ],
    "05-仓位风控": [
        "仓位是市场和模式给的，不是主观想赚快钱给的。",
        "没有退出条件的交易不能开仓。",
        "连续盈利后要防纪律放松，连续亏损后要防急于扳本。",
        "重仓只属于题材主升、A类模式、竞价确认、退出明确的交集。",
    ],
    "06-心态认知": [
        "交易认知必须制度化，否则知道也做不到。",
        "心态问题最终要落到仓位、止损、计划、复盘和统计。",
        "不要用情绪解释亏损，要用规则定位错误。",
        "高手的稳定来自长期重复正确动作，不是单次暴利。",
    ],
    "07-案例训练": [
        "案例不是用来抄作业，而是反推当时市场和资金选择。",
        "看高手实盘要看仓位变化、买卖节奏、选股角色和错了怎么处理。",
        "案例必须标注当时市场环境，否则无法迁移。",
        "所有案例都要进入D+跟踪，验证模式是否真的有效。",
    ],
}


def clean(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def read(path: Path) -> str:
    try:
        return path.read_bytes()[:800_000].decode("utf-8", errors="ignore")
    except Exception:
        return ""


def source(path: Path) -> str:
    parts = path.parts
    try:
        idx = parts.index("05-研报新闻")
        if parts[idx + 1] == "公众号" and idx + 2 < len(parts):
            return parts[idx + 2]
        return parts[idx + 1]
    except Exception:
        return "unknown"


def title(path: Path, text: str) -> str:
    for line in text.splitlines()[:20]:
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


def date(path: Path, text: str) -> str:
    m = re.search(r"(20\d{2})[-.年](\d{1,2})[-.月](\d{1,2})", f"{path.name}\n{text[:1000]}")
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def classify(text: str) -> tuple[str, list[str], dict[str, int]]:
    scores = {name: sum(text.count(k) for k in kws) for name, kws in SECTIONS.items()}
    ordered = [k for k, v in sorted(scores.items(), key=lambda kv: kv[1], reverse=True) if v > 0]
    return (ordered[0] if ordered else "07-案例训练", ordered[:4], scores)


def evidence(text: str, kws: list[str], limit: int = 6) -> list[str]:
    out = []
    for s in re.split(r"[。！？!?；;\n]", text):
        s = s.strip()
        if len(s) < 18:
            continue
        if any(k in s for k in kws):
            out.append(s[:160])
        if len(out) >= limit:
            break
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    articles = []
    for path in RAW_ROOT.rglob("*.md"):
        src = source(path)
        if src not in SOURCES:
            continue
        raw = read(path)
        txt = clean(raw)
        main, tags, scores = classify(f"{title(path, raw)} {txt[:300_000]}")
        articles.append({"path": path, "source": src, "title": title(path, raw), "date": date(path, raw), "text": txt, "main": main, "tags": tags, "scores": scores})

    by_section = defaultdict(list)
    by_source = defaultdict(list)
    for a in articles:
        by_section[a["main"]].append(a)
        by_source[a["source"]].append(a)

    index = [
        f"# 高纯度游资心得索引-{TODAY}",
        "",
        f"文章数：{len(articles)}",
        "",
        "本目录只保留交易者/复盘类公众号，不混入财联社、第一财经、研报新闻等信息源。",
        "",
        "## 分类分布",
        "",
        "| 分类 | 数量 |",
        "|---|---:|",
    ]
    for sec in SECTIONS:
        index.append(f"| {sec} | {len(by_section[sec])} |")
    index += ["", "## 作者分布", "", "| 作者 | 数量 | 主要分类 |", "|---|---:|---|"]
    for src, items in sorted(by_source.items(), key=lambda kv: len(kv[1]), reverse=True):
        top = Counter(i["main"] for i in items).most_common(3)
        index.append(f"| {src} | {len(items)} | {'、'.join(k for k, _ in top)} |")
    index += ["", "## 全量清单", "", "| 日期 | 作者 | 标题 | 主分类 | 标签 | RAW |", "|---|---|---|---|---|---|"]
    for a in sorted(articles, key=lambda x: (x["date"], x["source"], x["title"]), reverse=True):
        index.append(f"| {a['date']} | {a['source']} | {a['title'][:80]} | {a['main']} | {'、'.join(a['tags'][1:])} | {rel(a['path'])} |")
    (OUT / f"高纯度游资心得索引-{TODAY}.md").write_text("\n".join(index), encoding="utf-8")

    for sec, kws in SECTIONS.items():
        items = sorted(by_section[sec], key=lambda x: (x["date"], x["source"], x["title"]), reverse=True)
        lines = [
            f"# {sec}-{TODAY}",
            "",
            "## 可执行规律",
            "",
        ]
        lines += [f"- {r}" for r in RULES[sec]]
        lines += ["", "## 代表文章证据", ""]
        for a in items[:25]:
            lines += [f"### {a['title']}", "", f"- 作者：{a['source']}", f"- 日期：{a['date'] or '未知'}", f"- RAW：{rel(a['path'])}", ""]
            ev = evidence(a["text"], kws)
            lines += [f"- {e}" for e in ev] if ev else ["- 该文已归类，需后续人工/大鸟深度复核。"]
            lines.append("")
        lines += ["## 全量清单", "", "| 日期 | 作者 | 标题 | 标签 | RAW |", "|---|---|---|---|---|"]
        for a in items:
            lines.append(f"| {a['date']} | {a['source']} | {a['title'][:80]} | {'、'.join(a['tags'][1:])} | {rel(a['path'])} |")
        (OUT / f"{sec}-{TODAY}.md").write_text("\n".join(lines), encoding="utf-8")

    manual = [
        f"# 高纯度游资心得使用方法-{TODAY}",
        "",
        "## 怎么供你使用",
        "",
        "1. 盘前：先读市场理解、题材理解，确定今天能不能进攻。",
        "2. 选股：用题材理解定位主线、核心、中军、补涨和风险锚。",
        "3. 执行：用买卖点与竞价盘口，写入 9:15/9:20/9:25 条件。",
        "4. 交易：用模式方法选择低吸、半路、打板、接力、弱转强等执行方式。",
        "5. 风控：用仓位风控决定是否重仓、轻仓、空仓。",
        "6. 复盘：用案例训练和心态认知定位错误，进入统计看板。",
        "",
        "## 作战室转化",
        "",
        "每条游资心得只有满足以下条件，才允许进入作战室：",
        "",
        "- 与当前 L1 市场环境匹配。",
        "- 与当前主线题材或核心个股匹配。",
        "- 能落到一个 L4 模式。",
        "- 有明确触发、禁止、退出条件。",
        "- 能通过竞价或盘中数据确认。",
        "",
        "## 不允许",
        "",
        "- 不允许把游资观点直接当买入理由。",
        "- 不允许只学金句，不统计结果。",
        "- 不允许没有当时市场环境就迁移案例。",
    ]
    (OUT / f"高纯度游资心得使用方法-{TODAY}.md").write_text("\n".join(manual), encoding="utf-8")

    print(json.dumps({"articles": len(articles), "root": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
