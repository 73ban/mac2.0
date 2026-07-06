import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_GLOB = "codex-raw-watch-queue.indexed-2026-06-13-*.jsonl"
REGISTRY = ROOT / ".system" / "ingest-registry.jsonl"
TODAY = datetime.now().strftime("%Y-%m-%d")


THEME_KEYWORDS = {
    "AI算力": ["AI", "算力", "英伟达", "服务器", "GPU", "液冷", "数据中心", "HBM", "CPO"],
    "PCB覆铜板": ["PCB", "覆铜板", "CCL", "M10", "正交背板", "T布", "LowCTE", "铜箔"],
    "半导体": ["半导体", "芯片", "晶圆", "封装", "先进封装", "光刻胶", "硅片", "存储", "MLCC"],
    "机器人": ["机器人", "Optimus", "减速器", "灵巧手", "执行器", "人形机器人"],
    "商业航天": ["商业航天", "卫星", "火箭", "低空", "飞行汽车", "eVTOL"],
    "光通信光纤": ["光通信", "光模块", "光纤", "CPO", "硅光", "光芯片", "800G", "1.6T"],
    "并购重组": ["并购", "重组", "资产注入", "借壳", "收购", "控制权"],
    "消费电子": ["消费电子", "苹果", "折叠屏", "MR", "AI手机"],
    "资源有色": ["铜", "钨", "钼", "稀土", "黄金", "锂", "矿", "有色"],
    "金融证券": ["券商", "证券", "金融", "牛市", "指数", "流动性"],
}

METHOD_KEYWORDS = {
    "题材主升": ["主升", "大题材", "持续强化", "板块梯队", "容量中军", "主线"],
    "连板接力": ["连板", "接力", "空间板", "晋级", "高度板"],
    "趋势抱团": ["抱团", "趋势", "容量票", "中军", "新高"],
    "冰点修复": ["冰点", "修复", "恐慌", "反包", "止跌"],
    "弱转强": ["弱转强", "超预期", "竞价", "高开", "反核"],
    "低吸": ["低吸", "分歧低吸", "尾盘抄底", "恐慌低吸"],
    "打板": ["打板", "封板", "炸板", "回封", "扫板"],
    "半路": ["半路", "拉升", "分时", "盘口"],
    "出监管": ["出监管", "监管", "异动"],
    "绕异动": ["绕异动", "偏离值", "异动"],
    "并购重组预期差": ["重组", "并购", "资产注入", "控制权", "预期差"],
    "纪律风控": ["纪律", "空仓", "仓位", "止损", "回撤", "心态", "亏钱"],
    "市场情绪周期": ["情绪", "高潮", "退潮", "冰点", "分歧", "修复", "亏钱效应", "赚钱效应"],
}


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def slug(text: str, limit: int = 70) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return text[:limit] or hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def clean_text(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"try\{[\s\S]{0,2000}?catch\(e\)\{\}", " ", text)
    text = re.sub(r"window\.[A-Za-z0-9_.$\[\]'\"]+[\s\S]{0,2000}?;", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def read_text(path: Path, limit: int = 600_000) -> str:
    if path.suffix.lower() not in {".md", ".txt", ".json", ".csv"}:
        return ""
    try:
        return path.read_bytes()[:limit].decode("utf-8", errors="ignore")
    except Exception:
        return ""


def title_from(path: Path, text: str) -> str:
    for line in text.splitlines()[:30]:
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


def date_from(path: Path, text: str) -> str:
    m = re.search(r"(20\d{2})[-.年](\d{1,2})[-.月](\d{1,2})", f"{path.name}\n{text[:1000]}")
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def url_from(text: str) -> str:
    m = re.search(r"https?://[^\s)>\"]+", text)
    return m.group(0) if m else ""


def source_from(path: Path) -> str:
    parts = path.parts
    try:
        idx = parts.index("05-研报新闻")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    except ValueError:
        pass
    return "RAW"


def hits(text: str, mapping: dict[str, list[str]]) -> list[str]:
    upper = text.upper()
    return [key for key, words in mapping.items() if any(w.upper() in upper for w in words)]


def stock_terms() -> set[str]:
    terms = {
        "中际旭创", "新易盛", "天孚通信", "胜宏科技", "沪电股份", "工业富联", "寒武纪", "海光信息",
        "中芯国际", "北方华创", "长电科技", "通富微电", "生益科技", "东山精密", "光迅科技",
        "三花智控", "拓普集团", "绿的谐波", "宗申动力", "中国卫星", "长飞光纤", "源杰科技",
        "深南电路", "东材科技", "剑桥科技", "光库科技", "斯达半导", "大族激光", "浪潮信息",
        "中兴通讯", "亨通光电", "华正新材", "太辰光", "光迅科技", "江海股份", "世运电路",
    }
    stock_dir = ROOT / "wiki" / "03-L3个股档案"
    if stock_dir.exists():
        for file in stock_dir.glob("*.md"):
            stem = file.stem
            m = re.match(r"(\d{6})[-_](.+)", stem)
            if m:
                terms.add(m.group(1))
                terms.add(m.group(2).split("-")[0])
    return terms


def stocks_from(text: str, terms: set[str]) -> list[str]:
    found = set(re.findall(r"(?<!\d)([03668]\d{5})(?!\d)", text))
    for term in terms:
        if len(term) >= 2 and term in text:
            found.add(term)
    return sorted(found)


def evidence_lines(text: str, keywords: list[str], limit: int = 5) -> list[str]:
    sentences = re.split(r"[。！？!?；;\n]", text)
    out = []
    for s in sentences:
        s = s.strip()
        if len(s) < 12:
            continue
        if any(k and k in s for k in keywords):
            out.append(s[:160])
        if len(out) >= limit:
            break
    if not out and text:
        for s in sentences:
            s = s.strip()
            if len(s) >= 20:
                out.append(s[:160])
            if len(out) >= min(3, limit):
                break
    return out


def value_grade(source: str, themes: list[str], methods: list[str], stocks: list[str], size: int) -> str:
    score = 0
    if source == "知识星球":
        score += 3
    if source == "公众号" or source in {"ymj0418", "小睿睿投资学", "股痴流沙河", "大作手奇衡三", "作手奇衡三的冲天槊"}:
        score += 2
    score += min(3, len(themes))
    score += min(3, len(methods))
    score += min(3, len(stocks))
    if size > 1_000_000:
        score += 1
    if score >= 8:
        return "A"
    if score >= 4:
        return "B"
    return "C"


def card_text(d: dict) -> str:
    source = d["source"]
    truth = "S2" if source == "知识星球" else "S3"
    kws = d["themes"] + d["methods"] + d["stocks"] + [d["title"]]
    evidences = evidence_lines(d["clean"], kws)
    summary = "；".join(evidences[:3]) if evidences else "该资料已进入 WIKI，可作为后续题材、个股或模式研究的原始证据。"
    usage = []
    if d["themes"]:
        usage.append("用于题材资料沉淀和突发新闻映射。")
    if d["stocks"]:
        usage.append("用于个股档案补充和催化追踪。")
    if d["methods"]:
        usage.append("用于交易模式学习、统计和后续验证。")
    if not usage:
        usage.append("作为原始资料索引保留，暂不进入作战室。")
    return "\n".join(
        [
            f"# {d['title']}",
            "",
            "## 元数据",
            "",
            f"- 日期：{d['date'] or '未知'}",
            f"- 来源：{source}",
            f"- 原文：{d['url'] or '本地RAW'}",
            f"- RAW路径：{d['rel']}",
            f"- 可信度：{truth}",
            f"- 价值等级：{d['grade']}",
            "",
            "## 结构化摘要",
            "",
            summary,
            "",
            "## 关联标签",
            "",
            f"- 题材：{'、'.join(d['themes']) if d['themes'] else '无明确题材'}",
            f"- 个股：{'、'.join(d['stocks'][:30]) if d['stocks'] else '无明确个股'}",
            f"- 模式：{'、'.join(d['methods']) if d['methods'] else '无明确模式'}",
            "",
            "## 可交易用途",
            "",
            "\n".join(f"- {x}" for x in usage),
            "",
            "## 风险与限制",
            "",
            "- 本卡是资料沉淀卡，不等于买入建议。",
            "- 进入作战室前，必须再经过市场环境、竞价、成交量、板块强度和用户交易模式验证。",
            "- 公众号和社区观点默认 S3，研报和授权资料默认 S2，只有公告/交易所/公司原文才可视为 S1。",
            "",
        ]
    )


def md_table(rows: list[list[str]]) -> str:
    if not rows:
        return "无。"
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * len(rows[0])) + "|"]
    for row in rows[1:]:
        out.append("| " + " | ".join(str(x).replace("\n", " ") for x in row) + " |")
    return "\n".join(out)


def main() -> None:
    archives = sorted((ROOT / ".system").glob(ARCHIVE_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    if not archives:
        print(json.dumps({"error": "no archive"}, ensure_ascii=False))
        return
    rows = read_jsonl(archives[0])
    terms = stock_terms()
    docs = []
    seen = set()
    for row in rows:
        path = Path(row.get("source_path", ""))
        if not path.exists():
            continue
        rel_path = rel(path)
        if "raw/07-系统脚本/" in rel_path:
            continue
        if "raw/05-研报新闻/" not in rel_path and "raw/02-每日复盘/" not in rel_path:
            continue
        key = (str(path), row.get("content_hash", ""))
        if key in seen:
            continue
        seen.add(key)
        raw_text = read_text(path)
        clean = clean_text(raw_text)
        search = f"{path.name} {clean[:250_000]}"
        themes = hits(search, THEME_KEYWORDS)
        methods = hits(search, METHOD_KEYWORDS)
        stocks = stocks_from(search, terms)
        source = source_from(path)
        title = title_from(path, raw_text)
        grade = value_grade(source, themes, methods, stocks, int(row.get("size", 0) or 0))
        if grade == "C" and source not in {"知识星球", "公众号", "ymj0418", "小睿睿投资学", "股痴流沙河", "大作手奇衡三", "作手奇衡三的冲天槊"}:
            continue
        docs.append(
            {
                **row,
                "path": path,
                "rel": rel_path,
                "source": source,
                "title": title,
                "date": date_from(path, raw_text),
                "url": url_from(raw_text),
                "clean": clean,
                "themes": themes,
                "methods": methods,
                "stocks": stocks,
                "grade": grade,
            }
        )

    card_root = ROOT / "wiki" / "08-信息来源" / "RAW独立知识卡" / TODAY
    card_root.mkdir(parents=True, exist_ok=True)
    theme_root = ROOT / "wiki" / "02-L2方向题材" / "RAW增量题材卡"
    stock_root = ROOT / "wiki" / "03-L3个股档案" / "RAW增量个股卡"
    method_root = ROOT / "wiki" / "04-L4交易模式与执行" / "RAW增量模式卡"
    for p in (theme_root, stock_root, method_root):
        p.mkdir(parents=True, exist_ok=True)

    by_theme = defaultdict(list)
    by_stock = defaultdict(list)
    by_method = defaultdict(list)
    registry_rows = []
    for i, d in enumerate(sorted(docs, key=lambda x: (x["grade"], x["source"], x["date"], x["title"]), reverse=True), 1):
        file_name = f"{i:04d}-{slug(d['source'])}-{slug(d['date'] or 'nodate')}-{slug(d['title'])}.md"
        card_path = card_root / file_name
        card_path.write_text(card_text(d), encoding="utf-8")
        d["card_rel"] = rel(card_path)
        for theme in d["themes"]:
            by_theme[theme].append(d)
        for stock in d["stocks"]:
            by_stock[stock].append(d)
        for method in d["methods"]:
            by_method[method].append(d)
        registry_rows.append(
            {
                "raw_id": f"{d.get('content_hash')}:codex-knowledge-card",
                "source_path": str(d["path"]),
                "source_agent": d.get("source_agent", "unknown"),
                "preferred_ingestor": "codex",
                "status": "knowledge_card_created",
                "ingested_by": "codex",
                "deepseek_action": "skip",
                "truth_grade": "S2" if d["source"] == "知识星球" else "S3",
                "fate": d["grade"],
                "content_hash": d.get("content_hash", ""),
                "ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S +08:00"),
                "target_pages": [d["card_rel"]],
                "notes": "已生成独立知识卡；是否升级为正式模式或作战室规则需要二次验证。",
            }
        )

    def write_group_cards(root: Path, groups: dict[str, list[dict]], kind: str) -> int:
        count = 0
        for key, items in sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True):
            if not key:
                continue
            lines = [
                f"# {key}-RAW增量{kind}卡-{TODAY}",
                "",
                f"资料数：{len(items)}",
                "",
                "## 核心资料",
                "",
            ]
            rows2 = [["日期", "来源", "价值", "标题", "题材", "模式", "个股", "知识卡"]]
            for d in sorted(items, key=lambda x: (x["grade"], x["date"]), reverse=True)[:120]:
                rows2.append(
                    [
                        d["date"],
                        d["source"],
                        d["grade"],
                        d["title"][:60],
                        "、".join(d["themes"][:4]),
                        "、".join(d["methods"][:4]),
                        "、".join(d["stocks"][:6]),
                        d["card_rel"],
                    ]
                )
            lines.append(md_table(rows2))
            lines += [
                "",
                "## 使用规则",
                "",
                "- 本卡用于资料沉淀和快速映射，不等于交易建议。",
                "- 进入作战室前必须结合当日市场环境、竞价、成交量、板块梯队和用户交易模式。",
            ]
            (root / f"{slug(key)}-RAW增量{kind}卡-{TODAY}.md").write_text("\n".join(lines), encoding="utf-8")
            count += 1
        return count

    theme_count = write_group_cards(theme_root, by_theme, "题材")
    stock_count = write_group_cards(stock_root, by_stock, "个股")
    method_count = write_group_cards(method_root, by_method, "模式")

    summary_path = ROOT / "wiki" / "08-信息来源" / f"RAW独立知识卡生成报告-{TODAY}.md"
    grade_count = Counter(d["grade"] for d in docs)
    source_count = Counter(d["source"] for d in docs)
    summary_lines = [
        f"# RAW独立知识卡生成报告-{TODAY}",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"知识卡数量：{len(docs)}",
        f"题材增量卡：{theme_count}",
        f"个股增量卡：{stock_count}",
        f"模式增量卡：{method_count}",
        "",
        "## 价值等级分布",
        "",
        md_table([["等级", "数量"]] + [[k, str(v)] for k, v in grade_count.most_common()]),
        "",
        "## 来源分布",
        "",
        md_table([["来源", "数量"]] + [[k, str(v)] for k, v in source_count.most_common(50)]),
        "",
        "## 后续动作",
        "",
        "1. A 级卡优先进入正式模式复核、个股档案复核和作战室资料池。",
        "2. B 级卡作为题材/个股/模式补充资料。",
        "3. C 级卡只保留索引，不进入作战室。",
    ]
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")

    append_jsonl(REGISTRY, registry_rows)
    print(
        json.dumps(
            {
                "knowledge_cards": len(docs),
                "theme_cards": theme_count,
                "stock_cards": stock_count,
                "method_cards": method_count,
                "summary": str(summary_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
