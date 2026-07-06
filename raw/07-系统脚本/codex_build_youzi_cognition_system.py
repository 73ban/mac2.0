import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "raw" / "05-研报新闻"
WIKI_ROOT = ROOT / "wiki" / "04-L4交易模式与执行" / "游资认知体系"
REGISTRY = ROOT / ".system" / "ingest-registry.jsonl"
TODAY = datetime.now().strftime("%Y-%m-%d")


CATEGORIES = {
    "01-市场环境与情绪周期": {
        "keywords": ["市场", "指数", "量能", "情绪", "退潮", "冰点", "分歧", "修复", "高潮", "亏钱效应", "赚钱效应", "轮动", "抱团", "缩量", "放量", "撕裂"],
        "use": "判断明天能不能进攻、能不能重仓、用什么模式。",
    },
    "02-题材主线与预期差": {
        "keywords": ["题材", "主线", "分支", "龙头", "中军", "补涨", "核心", "容量", "预期差", "催化", "发酵", "产业", "逻辑", "兑现"],
        "use": "判断哪个方向值得跟，哪个只是轮动或杂毛。",
    },
    "03-交易模式与战法": {
        "keywords": ["低吸", "半路", "打板", "连板", "接力", "弱转强", "反包", "回封", "二波", "绕异动", "出监管", "重组", "首板", "空间板"],
        "use": "沉淀可统计、可复用、可验证的交易模式。",
    },
    "04-买卖点与竞价盘口": {
        "keywords": ["竞价", "盘口", "分时", "开盘", "尾盘", "卖点", "买点", "止盈", "止损", "高开", "低开", "承接", "封单", "撤单", "炸板"],
        "use": "把看法转成具体买卖动作和盘中确认条件。",
    },
    "05-风控纪律与仓位": {
        "keywords": ["纪律", "仓位", "空仓", "回撤", "亏损", "风险", "防守", "禁止", "不能", "止损", "大面", "核按钮"],
        "use": "约束重仓、止损、空仓和亏损后的行为。",
    },
    "06-心态认知与交易修炼": {
        "keywords": ["心态", "贪婪", "恐惧", "认知", "耐心", "执行", "自控", "人性", "反思", "悟", "修炼", "道心"],
        "use": "解决知道但做不到、盈利后放松、亏损后急躁的问题。",
    },
    "07-案例复盘与高手行为": {
        "keywords": ["复盘", "龙虎榜", "账户", "实盘", "老师", "游资", "席位", "买入", "卖出", "涨停", "跌停", "炸板", "核心票"],
        "use": "用具体案例训练盘感，验证模式在当时市场是否有效。",
    },
}


TRUSTED_SOURCE_HINTS = {
    "淘股吧", "安静拆主线", "小睿睿投资学", "股痴流沙河", "ymj0418", "大作手奇衡三", "作手奇衡三的冲天槊",
    "17学无止境", "鄂华少", "圣广鸿鹄复盘", "盘面说", "只核大a学生", "大蟒蛇神", "木火通明",
}


def clean_text(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"window\.[A-Za-z0-9_.$\[\]'\"]+[\s\S]{0,3000}?;", " ", text)
    text = re.sub(r"try\{[\s\S]{0,3000}?catch\(e\)\{\}", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def read_text(path: Path) -> str:
    try:
        return path.read_bytes()[:1_000_000].decode("utf-8", errors="ignore")
    except Exception:
        return ""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def title_from(path: Path, text: str) -> str:
    for line in text.splitlines()[:30]:
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


def source_from(path: Path) -> str:
    parts = list(path.parts)
    try:
        idx = parts.index("05-研报新闻")
        if idx + 1 < len(parts):
            if parts[idx + 1] == "公众号" and idx + 2 < len(parts):
                return parts[idx + 2]
            return parts[idx + 1]
    except ValueError:
        pass
    return "unknown"


def date_from(path: Path, text: str) -> str:
    m = re.search(r"(20\d{2})[-.年](\d{1,2})[-.月](\d{1,2})", f"{path.name}\n{text[:1000]}")
    if not m:
        return ""
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def url_from(text: str) -> str:
    m = re.search(r"https?://[^\s)>\"]+", text)
    return m.group(0) if m else ""


def score_categories(text: str) -> dict[str, int]:
    scores = {}
    for cat, meta in CATEGORIES.items():
        scores[cat] = sum(text.count(k) for k in meta["keywords"])
    return scores


def evidence(text: str, keywords: list[str], limit: int = 8) -> list[str]:
    sents = re.split(r"[。！？!?；;\n]", text)
    out = []
    for s in sents:
        s = s.strip()
        if len(s) < 16:
            continue
        if any(k in s for k in keywords):
            out.append(s[:180])
        if len(out) >= limit:
            break
    if not out:
        for s in sents:
            s = s.strip()
            if len(s) >= 30:
                out.append(s[:180])
            if len(out) >= 3:
                break
    return out


def category_rules(cat: str) -> list[str]:
    base = {
        "01-市场环境与情绪周期": [
            "先判断市场状态，再选择模式；不要先有持仓再倒推理由。",
            "高潮后看分歧质量，冰点后看修复强度，退潮期优先防守。",
            "赚钱效应来自核心票、前排、容量中军和连板高度的共同反馈。",
            "亏钱效应来自高标A杀、后排大面、炸板率高和风险锚恶化。",
        ],
        "02-题材主线与预期差": [
            "题材强弱看持续性、宽度、梯队、核心股承接，不只看新闻热度。",
            "真正主线必须有龙头、中军、补涨和风险锚，单票强不等于主线。",
            "预期差来自市场还没充分理解或资金尚未完全定价的方向。",
            "题材进入一致高潮后，后排追涨收益风险比快速下降。",
        ],
        "03-交易模式与战法": [
            "模式必须绑定市场环境，不能孤立使用。",
            "同一模式在主升、轮动、退潮中的胜率完全不同。",
            "低吸、半路、打板不是偏好，而是不同确认阶段的执行方式。",
            "模式必须可统计：胜率、盈亏额、持股周期、最大回撤。",
        ],
        "04-买卖点与竞价盘口": [
            "竞价只用于确认盘前计划，不用于临时乱追。",
            "9:15看方向，9:20看真假，9:25看最终预期。",
            "买点必须有承接、量能、板块和情绪配合。",
            "卖点优先看低于预期、风险锚恶化、模式失效和持仓偏离计划。",
        ],
        "05-风控纪律与仓位": [
            "仓位权来自市场环境和模式确定性，不来自主观想赚快钱。",
            "没有退出条件，不允许开仓；计划外交易默认错误。",
            "连续亏损时先降频和降仓，不急于扳本。",
            "重仓只属于题材主升、A类模式、竞价确认、退出明确的交集。",
        ],
        "06-心态认知与交易修炼": [
            "交易修炼的核心是把认知、纪律和执行统一。",
            "盈利后最容易放松纪律，亏损后最容易急于扳本。",
            "看懂不等于能做，能做不等于能长期重复。",
            "心态问题最终要落到制度：仓位、止损、计划、复盘和统计。",
        ],
        "07-案例复盘与高手行为": [
            "案例不是用来抄作业，而是反推当时市场、模式和资金选择。",
            "高手行为要看仓位变化、买卖节奏、选股角色和错误处理。",
            "复盘重点是当时为什么能做、为什么不能做、哪里超预期或不及预期。",
            "所有案例最终要进入候选票D+1/D+3/D+5跟踪。",
        ],
    }
    return base.get(cat, [])


def main() -> None:
    WIKI_ROOT.mkdir(parents=True, exist_ok=True)
    articles = []
    for path in RAW_ROOT.rglob("*.md"):
        if "知识星球" in path.parts:
            continue
        source = source_from(path)
        raw = read_text(path)
        clean = clean_text(raw)
        if not clean:
            continue
        is_youzi = source in TRUSTED_SOURCE_HINTS or any(h in str(path) for h in TRUSTED_SOURCE_HINTS)
        if not is_youzi and "公众号" not in path.parts:
            continue
        title = title_from(path, raw)
        search = f"{title} {source} {clean[:400_000]}"
        scores = score_categories(search)
        total = sum(scores.values())
        if total == 0 and not is_youzi:
            continue
        cats = [k for k, v in sorted(scores.items(), key=lambda kv: kv[1], reverse=True) if v > 0]
        main_cat = cats[0] if cats else "07-案例复盘与高手行为"
        articles.append(
            {
                "path": path,
                "rel": rel(path),
                "title": title,
                "source": source,
                "date": date_from(path, raw),
                "url": url_from(raw),
                "clean": clean,
                "scores": scores,
                "categories": cats[:4],
                "main_cat": main_cat,
                "hash": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
            }
        )

    by_cat = defaultdict(list)
    by_source = defaultdict(list)
    for a in articles:
        by_cat[a["main_cat"]].append(a)
        by_source[a["source"]].append(a)

    # Full index.
    index_lines = [
        f"# 公众号大游资心得全量索引-{TODAY}",
        "",
        f"处理文章数：{len(articles)}",
        "",
        "## 分类分布",
        "",
        "| 分类 | 数量 | 用途 |",
        "|---|---:|---|",
    ]
    for cat in CATEGORIES:
        index_lines.append(f"| {cat} | {len(by_cat[cat])} | {CATEGORIES[cat]['use']} |")
    index_lines += [
        "",
        "## 来源分布",
        "",
        "| 来源 | 数量 | 主要倾向 |",
        "|---|---:|---|",
    ]
    for source, items in sorted(by_source.items(), key=lambda kv: len(kv[1]), reverse=True):
        top_cats = Counter(i["main_cat"] for i in items).most_common(3)
        index_lines.append(f"| {source} | {len(items)} | {'、'.join(k for k, _ in top_cats)} |")
    index_lines += [
        "",
        "## 全量文章",
        "",
        "| 日期 | 来源 | 标题 | 主分类 | 其他标签 | RAW |",
        "|---|---|---|---|---|---|",
    ]
    for a in sorted(articles, key=lambda x: (x["date"], x["source"], x["title"]), reverse=True):
        index_lines.append(
            f"| {a['date']} | {a['source']} | {a['title'][:80]} | {a['main_cat']} | {'、'.join(a['categories'][1:])} | {a['rel']} |"
        )
    (WIKI_ROOT / f"公众号大游资心得全量索引-{TODAY}.md").write_text("\n".join(index_lines), encoding="utf-8")

    # Category files.
    for cat, meta in CATEGORIES.items():
        items = sorted(by_cat[cat], key=lambda x: (x["date"], x["source"], x["title"]), reverse=True)
        lines = [
            f"# {cat}-{TODAY}",
            "",
            f"用途：{meta['use']}",
            "",
            "## 规律总结",
            "",
        ]
        lines += [f"- {r}" for r in category_rules(cat)]
        lines += [
            "",
            "## 代表证据",
            "",
        ]
        for a in items[:30]:
            ev = evidence(a["clean"], meta["keywords"], 3)
            lines += [
                f"### {a['title']}",
                "",
                f"- 来源：{a['source']}",
                f"- 日期：{a['date'] or '未知'}",
                f"- RAW：{a['rel']}",
                "",
            ]
            lines += [f"- {e}" for e in ev]
            lines.append("")
        lines += [
            "## 全量清单",
            "",
            "| 日期 | 来源 | 标题 | 其他标签 | RAW |",
            "|---|---|---|---|---|",
        ]
        for a in items:
            lines.append(f"| {a['date']} | {a['source']} | {a['title'][:80]} | {'、'.join(a['categories'][1:])} | {a['rel']} |")
        (WIKI_ROOT / f"{cat}-{TODAY}.md").write_text("\n".join(lines), encoding="utf-8")

    # Author profiles.
    profile_lines = [
        f"# 公众号游资作者认知画像-{TODAY}",
        "",
        "本页按来源统计每个作者更擅长或更常讨论的角度。用途是以后看文章时知道它更适合补充哪类认知。",
        "",
        "| 作者/来源 | 文章数 | 主要认知倾向 | 使用方式 |",
        "|---|---:|---|---|",
    ]
    for source, items in sorted(by_source.items(), key=lambda kv: len(kv[1]), reverse=True):
        top = Counter(i["main_cat"] for i in items).most_common(4)
        profile_lines.append(
            f"| {source} | {len(items)} | {'、'.join(k for k, _ in top)} | 作为 {' / '.join(k.split('-', 1)[-1] for k, _ in top[:2])} 的资料源 |"
        )
    (WIKI_ROOT / f"公众号游资作者认知画像-{TODAY}.md").write_text("\n".join(profile_lines), encoding="utf-8")

    # Usage manual.
    manual = [
        f"# 公众号游资心得使用说明-{TODAY}",
        "",
        "## 定位",
        "",
        "公众号游资心得不是直接买入信号，而是训练交易大脑的认知语料。",
        "",
        "## 使用路径",
        "",
        "```text",
        "看到新文章/新观点",
        "→ 进入RAW",
        "→ 生成独立知识卡",
        "→ 归入游资认知体系七类",
        "→ 若涉及具体模式，进入L4模式候选",
        "→ 若涉及具体个股，进入L3个股雷达",
        "→ 若服务明天交易，进入作战室",
        "→ D+1/D+3/D+5验证",
        "```",
        "",
        "## 七类如何使用",
        "",
        "| 分类 | 使用场景 | 输出到哪里 |",
        "|---|---|---|",
        "| 市场环境与情绪周期 | 判断仓位权限和进攻/防守 | L1市场环境、作战室 |",
        "| 题材主线与预期差 | 判断主线、龙头、中军、补涨 | L2题材、作战室 |",
        "| 交易模式与战法 | 沉淀可统计模式 | L4模式库、统计看板 |",
        "| 买卖点与竞价盘口 | 形成执行条件 | 竞价监控清单、作战室 |",
        "| 风控纪律与仓位 | 防止大亏和乱重仓 | 纪律库、统计看板 |",
        "| 心态认知与交易修炼 | 解决执行偏差 | 错误库、交易复盘 |",
        "| 案例复盘与高手行为 | 学习高手行为，不抄作业 | 候选票跟踪池 |",
        "",
        "## 禁止",
        "",
        "1. 禁止把公众号观点直接当作买入理由。",
        "2. 禁止只摘金句，不记录市场环境。",
        "3. 禁止不验证就升级为 A 类模式。",
        "4. 禁止资料多就重仓，必须有盘面和竞价确认。",
        "",
    ]
    (WIKI_ROOT / f"公众号游资心得使用说明-{TODAY}.md").write_text("\n".join(manual), encoding="utf-8")

    registry_rows = []
    for a in articles:
        registry_rows.append(
            {
                "raw_id": f"{a['hash']}:youzi-cognition-system",
                "source_path": str(a["path"]),
                "source_agent": "codex",
                "preferred_ingestor": "codex",
                "status": "youzi_cognition_classified",
                "ingested_by": "codex",
                "deepseek_action": "skip",
                "truth_grade": "S3",
                "fate": "B",
                "content_hash": a["hash"],
                "ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S +08:00"),
                "target_pages": [rel(WIKI_ROOT / f"{a['main_cat']}-{TODAY}.md")],
                "notes": "公众号/游资心得已进入游资认知体系分类库。",
            }
        )
    with REGISTRY.open("a", encoding="utf-8") as f:
        for row in registry_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(json.dumps({"articles": len(articles), "categories": len(CATEGORIES), "root": str(WIKI_ROOT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
