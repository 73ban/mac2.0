import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / ".system" / "codex-raw-watch-queue.jsonl"
REGISTRY = ROOT / ".system" / "ingest-registry.jsonl"
TODAY = datetime.now().strftime("%Y-%m-%d")


THEME_KEYWORDS = {
    "AI算力": ["AI", "算力", "英伟达", "服务器", "GPU", "液冷", "数据中心", "HBM"],
    "PCB覆铜板": ["PCB", "覆铜板", "CCL", "M10", "正交背板", "T布", "LowCTE"],
    "半导体": ["半导体", "芯片", "晶圆", "封装", "先进封装", "光刻胶", "硅片", "存储", "MLCC"],
    "机器人": ["机器人", "Optimus", "减速器", "灵巧手", "执行器", "人形机器人"],
    "商业航天": ["商业航天", "卫星", "火箭", "低空", "飞行汽车", "eVTOL"],
    "光通信光纤": ["光通信", "光模块", "光纤", "CPO", "硅光", "光芯片", "800G", "1.6T"],
    "并购重组": ["并购", "重组", "资产注入", "借壳", "收购", "控制权"],
    "消费电子": ["消费电子", "苹果", "折叠屏", "MR", "AI手机"],
    "资源有色": ["铜", "钨", "钼", "稀土", "黄金", "锂", "矿", "有色"],
    "金融证券": ["券商", "证券", "金融", "牛市", "指数"],
}

METHOD_KEYWORDS = {
    "题材主升": ["主升", "大题材", "持续强化", "板块梯队", "容量中军"],
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
    "纪律风控": ["纪律", "空仓", "仓位", "止损", "回撤", "心态"],
}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def safe_read_text(path: Path, limit: int = 200_000) -> str:
    if path.suffix.lower() not in {".md", ".txt", ".json", ".csv"}:
        return ""
    try:
        data = path.read_bytes()[:limit]
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def clean_text(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_title(path: Path, text: str) -> str:
    for line in text.splitlines()[:40]:
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


def extract_date(path: Path, text: str) -> str:
    joined = f"{path.name}\n{text[:1000]}"
    m = re.search(r"(20\d{2})[-.年](\d{1,2})[-.月](\d{1,2})", joined)
    if not m:
        return ""
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def extract_url(text: str) -> str:
    m = re.search(r"https?://[^\s)>\"]+", text)
    return m.group(0) if m else ""


def extract_source(path: Path) -> str:
    parts = path.parts
    try:
        idx = parts.index("09-短线知识")
        if idx + 1 < len(parts):
            return "短线知识/" + parts[idx + 1]
    except ValueError:
        pass
    try:
        idx = parts.index("05-研报新闻")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    except ValueError:
        pass
    try:
        idx = parts.index("raw")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    except ValueError:
        pass
    return "unknown"


def hits(text: str, mapping: dict[str, list[str]]) -> list[str]:
    found = []
    upper_text = text.upper()
    for key, words in mapping.items():
        if any(word.upper() in upper_text for word in words):
            found.append(key)
    return found


def load_stock_terms() -> set[str]:
    terms: set[str] = set()
    stock_dir = ROOT / "wiki" / "03-L3个股档案"
    if stock_dir.exists():
        for file in stock_dir.glob("*.md"):
            name = file.stem
            for part in re.split(r"[-_]", name):
                part = part.strip()
                if len(part) >= 2 and not re.fullmatch(r"\d{4,6}", part):
                    terms.add(part)
            m = re.match(r"(\d{6})", name)
            if m:
                terms.add(m.group(1))
    hardcoded = [
        "中际旭创", "新易盛", "天孚通信", "胜宏科技", "沪电股份", "工业富联", "寒武纪", "海光信息",
        "中芯国际", "北方华创", "长电科技", "通富微电", "生益科技", "东山精密", "光迅科技",
        "三花智控", "拓普集团", "绿的谐波", "宗申动力", "中国卫星", "长飞光纤", "源杰科技",
    ]
    terms.update(hardcoded)
    return terms


def extract_stocks(text: str, terms: set[str]) -> list[str]:
    found = set(re.findall(r"(?<!\d)([03668]\d{5})(?!\d)", text))
    for term in terms:
        if term and term in text:
            found.add(term)
    return sorted(found)


def md_table(rows: list[list[str]]) -> list[str]:
    if not rows:
        return ["无。"]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * len(rows[0])) + "|"]
    for row in rows[1:]:
        out.append("| " + " | ".join(str(x).replace("\n", " ") for x in row) + " |")
    return out


def main() -> None:
    queue_items = read_jsonl(QUEUE)
    if not queue_items:
        print(json.dumps({"processed": 0}, ensure_ascii=False))
        return

    stock_terms = load_stock_terms()
    docs = []
    seen = set()
    for item in queue_items:
        source_path = item.get("source_path", "")
        content_hash = item.get("content_hash", "")
        key = (source_path, content_hash)
        if key in seen:
            continue
        seen.add(key)
        path = Path(source_path)
        if not path.exists():
            continue
        text_raw = safe_read_text(path)
        text_clean = clean_text(text_raw)
        title = extract_title(path, text_raw)
        combined = f"{title} {text_clean[:120_000]}"
        docs.append(
            {
                **item,
                "path": path,
                "rel": rel(path),
                "title": title,
                "date": extract_date(path, text_raw),
                "url": extract_url(text_raw),
                "source": extract_source(path),
                "top": rel(path).split("/")[1] if rel(path).startswith("raw/") and len(rel(path).split("/")) > 1 else "",
                "themes": hits(combined, THEME_KEYWORDS),
                "methods": hits(combined, METHOD_KEYWORDS),
                "stocks": extract_stocks(combined, stock_terms),
            }
        )

    out_dir = ROOT / "wiki" / "08-信息来源"
    out_dir.mkdir(parents=True, exist_ok=True)
    l2_dir = ROOT / "wiki" / "02-L2方向题材"
    l3_dir = ROOT / "wiki" / "03-L3个股档案"
    l4_dir = ROOT / "wiki" / "04-L4交易模式与执行"
    for d in (l2_dir, l3_dir, l4_dir):
        d.mkdir(parents=True, exist_ok=True)

    by_top = Counter(d["top"] for d in docs)
    by_source = Counter(d["source"] for d in docs)
    by_theme = defaultdict(list)
    by_method = defaultdict(list)
    by_stock = defaultdict(list)
    for d in docs:
        for theme in d["themes"]:
            by_theme[theme].append(d)
        for method in d["methods"]:
            by_method[method].append(d)
        for stock in d["stocks"]:
            by_stock[stock].append(d)

    index_path = out_dir / f"RAW全量沉淀索引-{TODAY}.md"
    lines = [
        f"# RAW全量沉淀索引-{TODAY}",
        "",
        "本页由大鸟批量摄入生成。作用是让 RAW 中的资料进入 WIKI 的可检索沉淀层，并登记防重复摄入。",
        "",
        f"处理文件数：{len(docs)}",
        "",
        "## 目录分布",
        "",
    ]
    lines += md_table([["目录", "数量"]] + [[k or "unknown", str(v)] for k, v in by_top.most_common()])
    lines += ["", "## 来源分布", ""]
    lines += md_table([["来源", "数量"]] + [[k or "unknown", str(v)] for k, v in by_source.most_common(80)])
    lines += ["", "## 全量清单", ""]
    rows = [["日期", "来源", "标题", "题材", "模式", "个股", "RAW路径"]]
    for d in sorted(docs, key=lambda x: (x["date"], x["source"], x["title"]), reverse=True):
        rows.append([
            d["date"],
            d["source"],
            d["title"][:80],
            "、".join(d["themes"][:4]),
            "、".join(d["methods"][:4]),
            "、".join(d["stocks"][:6]),
            d["rel"],
        ])
    lines += md_table(rows)
    index_path.write_text("\n".join(lines), encoding="utf-8")

    theme_path = l2_dir / f"RAW题材资料映射-{TODAY}.md"
    lines = [
        f"# RAW题材资料映射-{TODAY}",
        "",
        "本页把 RAW 资料按题材归类。用途：突发新闻出现时，快速查看 WIKI 是否已有相关题材资料、历史研报、公众号观点和个股线索。",
        "",
    ]
    for theme, items in sorted(by_theme.items(), key=lambda kv: len(kv[1]), reverse=True):
        lines += [f"## {theme}", "", f"资料数：{len(items)}", ""]
        rows = [["日期", "来源", "标题", "个股", "RAW路径"]]
        for d in sorted(items, key=lambda x: x["date"], reverse=True)[:120]:
            rows.append([d["date"], d["source"], d["title"][:70], "、".join(d["stocks"][:6]), d["rel"]])
        lines += md_table(rows)
        lines.append("")
    theme_path.write_text("\n".join(lines), encoding="utf-8")

    stock_path = l3_dir / f"RAW个股资料映射-{TODAY}.md"
    lines = [
        f"# RAW个股资料映射-{TODAY}",
        "",
        "本页把 RAW 资料按个股/公司名映射。用途：突发新闻或作战室候选股出现时，快速判断 WIKI 是否已有相关资料。",
        "",
    ]
    for stock, items in sorted(by_stock.items(), key=lambda kv: len(kv[1]), reverse=True):
        if len(items) < 2 and not re.fullmatch(r"\d{6}", stock):
            continue
        lines += [f"## {stock}", "", f"资料数：{len(items)}", ""]
        rows = [["日期", "来源", "标题", "题材", "模式", "RAW路径"]]
        for d in sorted(items, key=lambda x: x["date"], reverse=True)[:80]:
            rows.append([d["date"], d["source"], d["title"][:70], "、".join(d["themes"][:4]), "、".join(d["methods"][:4]), d["rel"]])
        lines += md_table(rows)
        lines.append("")
    stock_path.write_text("\n".join(lines), encoding="utf-8")

    method_path = l4_dir / f"游资公众号心得待提炼池-{TODAY}.md"
    lines = [
        f"# 短线知识与游资心得待提炼池-{TODAY}",
        "",
        "本页不是最终模式结论，而是把 RAW 中出现的短线知识、游资心得、模式、纪律、买卖点资料先沉淀到 L4 待提炼池。",
        "后续大鸟需要把高频且能被交易结果验证的内容，升级进入短线模式原理库、验证队列和具体模式页。",
        "",
    ]
    for method, items in sorted(by_method.items(), key=lambda kv: len(kv[1]), reverse=True):
        lines += [f"## {method}", "", f"资料数：{len(items)}", ""]
        rows = [["日期", "来源", "标题", "题材", "个股", "RAW路径"]]
        for d in sorted(items, key=lambda x: x["date"], reverse=True)[:120]:
            rows.append([d["date"], d["source"], d["title"][:70], "、".join(d["themes"][:4]), "、".join(d["stocks"][:6]), d["rel"]])
        lines += md_table(rows)
        lines.append("")
    method_path.write_text("\n".join(lines), encoding="utf-8")

    target_pages = [rel(index_path), rel(theme_path), rel(stock_path), rel(method_path)]
    registry_rows = []
    existing_keys = set()
    if REGISTRY.exists():
        for row in read_jsonl(REGISTRY):
            existing_keys.add((row.get("source_path"), row.get("content_hash"), row.get("status")))
    for d in docs:
        row = {
            "raw_id": f"{d.get('content_hash')}:codex-batch-index",
            "source_path": str(d["path"]),
            "source_agent": d.get("source_agent", "unknown"),
            "preferred_ingestor": "codex",
            "status": "indexed_to_wiki",
            "ingested_by": "codex",
            "deepseek_action": "skip",
            "truth_grade": d.get("truth_grade", "S3"),
            "fate": "B",
            "content_hash": d.get("content_hash", ""),
            "first_seen_at": d.get("first_seen_at", ""),
            "ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S +08:00"),
            "target_pages": target_pages,
            "notes": "批量进入WIKI沉淀索引、题材映射、个股映射和L4待提炼池；需要后续深度提炼的资料继续由大鸟处理。",
        }
        key = (row["source_path"], row["content_hash"], row["status"])
        if key not in existing_keys:
            registry_rows.append(row)
            existing_keys.add(key)

    if registry_rows:
        with REGISTRY.open("a", encoding="utf-8") as f:
            for row in registry_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    archive = ROOT / ".system" / f"codex-raw-watch-queue.indexed-{TODAY}-{datetime.now().strftime('%H%M%S')}.jsonl"
    write_jsonl(archive, queue_items)
    write_jsonl(QUEUE, [])

    print(
        json.dumps(
            {
                "processed": len(docs),
                "registry_added": len(registry_rows),
                "index": str(index_path),
                "theme": str(theme_path),
                "stock": str(stock_path),
                "method": str(method_path),
                "archive": str(archive),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
