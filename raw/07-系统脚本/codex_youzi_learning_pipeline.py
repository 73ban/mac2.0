from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "raw" / "09-短线知识" / "游资公众号"
LEGACY_RAW_ROOT = ROOT / "raw" / "05-研报新闻" / "公众号" / "游资号"
FEISHU_SHORTLINE_ROOT = ROOT / "raw" / "09-短线知识" / "飞书输入"
SYSTEM_DIR = ROOT / ".system"
SOURCE_CLASS_CONFIG = SYSTEM_DIR / "wechat-mp-source-classes.json"
LOG_DIR = SYSTEM_DIR / "logs"
STATE_PATH = SYSTEM_DIR / "youzi-learning-state.json"
REPORT_JSON = SYSTEM_DIR / "youzi-learning-report.json"
REPORT_MD = SYSTEM_DIR / "youzi-learning-report.md"
REGISTRY_PATH = SYSTEM_DIR / "ingest-registry.jsonl"
WIKI_ROOT = ROOT / "wiki" / "04-L4交易模式与执行" / "游资认知体系"
CARD_ROOT = WIKI_ROOT / "增量学习卡"
AUTHOR_ROOT = WIKI_ROOT / "作者库"
CATEGORY_ROOT = WIKI_ROOT / "分类库"
VERIFY_ROOT = WIKI_ROOT / "验证看板"
MASTER_INDEX = WIKI_ROOT / "游资学习总表.md"
TODAY = datetime.now().strftime("%Y-%m-%d")

STOPWORDS = {
    "今天", "明天", "后面", "继续", "因为", "如果", "这个", "那个", "还是", "就是", "一个", "我们", "你们",
    "他们", "自己", "已经", "可能", "需要", "可以", "没有", "不会", "时候", "感觉", "比较", "市场", "题材",
    "板块", "核心", "方向", "个股", "资金", "情绪", "老师", "这里", "这边", "里面", "文章", "公众号", "游资",
}

CATEGORY_DEFS = {
    "市场情绪": {
        "keywords": ["市场", "情绪", "指数", "冰点", "高潮", "分歧", "修复", "赚钱效应", "亏钱效应", "轮动", "放量", "缩量"],
        "question": "当前市场处于什么阶段，应该进攻还是防守？",
    },
    "题材主线": {
        "keywords": ["题材", "主线", "支线", "龙头", "中军", "补涨", "预期差", "催化", "发酵", "兑现", "穿越", "卡位"],
        "question": "哪些方向是真主线，哪些只是轮动或过渡？",
    },
    "买卖执行": {
        "keywords": ["竞价", "盘口", "分时", "开盘", "尾盘", "买点", "卖点", "承接", "封单", "炸板", "回封", "高开", "低开"],
        "question": "盘中怎么确认、怎么出手、怎么退出？",
    },
    "模式方法": {
        "keywords": ["低吸", "半路", "打板", "接力", "反包", "二波", "弱转强", "趋势", "绕异动", "出监管", "首板", "龙头战法"],
        "question": "这篇文章对应什么交易模式，适合在什么环境下用？",
    },
    "风控仓位": {
        "keywords": ["仓位", "风控", "止损", "止盈", "空仓", "回撤", "纪律", "风险", "防守", "重仓", "轻仓", "熔断"],
        "question": "仓位权重和止损纪律应该怎么定？",
    },
    "心态纪律": {
        "keywords": ["心态", "认知", "贪婪", "恐惧", "执行", "耐心", "自控", "反思", "修炼", "执念", "补偿", "犹豫"],
        "question": "容易犯什么心理错误，如何用规则压住它？",
    },
    "案例复盘": {
        "keywords": ["复盘", "案例", "实盘", "龙虎榜", "席位", "账户", "买入", "卖出", "涨停", "跌停", "炸板", "龙回头"],
        "question": "这篇文章给了什么可复用的案例证据？",
    },
    "产业链学习": {
        "keywords": ["AI", "PCB", "覆铜板", "MLCC", "光通信", "服务器", "机器人", "半导体", "电力", "军工", "业绩", "产业链"],
        "question": "这篇文章补充了哪些产业链和基本面认知？",
    },
}

METHOD_DEFS = {
    "低吸": ["低吸", "恐慌低吸", "分歧低吸", "回调低吸"],
    "半路": ["半路", "盘中确认", "拉升介入"],
    "打板": ["打板", "封板", "回封", "扫板"],
    "接力": ["接力", "连板", "晋级", "空间板"],
    "弱转强": ["弱转强", "超预期", "反核", "高开走强"],
    "反包": ["反包", "修复", "反包板"],
    "二波": ["二波", "龙回头", "二次启动"],
    "趋势抱团": ["趋势", "抱团", "中军", "新高", "容量"],
    "绕异动": ["绕异动", "异动", "临停"],
    "出监管": ["出监管", "监管函", "重点监控"],
    "业绩博弈": ["业绩", "中报", "季报", "预告"],
    "轮动切换": ["轮动", "切换", "高低切", "跷跷板"],
}

THEME_DEFS = {
    "AI硬件": ["AI", "算力", "服务器", "GPU", "HBM", "液冷"],
    "光通信": ["光通信", "光模块", "CPO", "硅光", "光纤"],
    "PCB/覆铜板": ["PCB", "覆铜板", "CCL", "玻纤布", "树脂"],
    "MLCC/元件": ["MLCC", "元件", "被动元件", "电子布"],
    "半导体": ["半导体", "芯片", "晶圆", "封装", "刻蚀", "设备"],
    "机器人": ["机器人", "人形机器人", "减速器", "丝杠", "执行器"],
    "电力": ["电力", "电网", "电改", "火电", "绿电"],
    "军工": ["军工", "卫星", "低空", "导弹", "航空"],
    "并购重组": ["并购", "重组", "借壳", "资产注入"],
    "业绩线": ["业绩", "中报", "年报", "预告", "景气"],
}

RULE_HINTS = ("要", "不要", "不能", "必须", "只做", "重点", "注意", "适合", "不宜", "确认", "观察", "优先", "避免")


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def to_posix(path: Path) -> str:
    return path.as_posix()


def rel_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except Exception:
        return path.as_posix()


def log(message: str, log_path: Path) -> None:
    line = f"[{now_text()}] {message}"
    print(line)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def active_youzi_sources() -> set[str]:
    config = load_json(SOURCE_CLASS_CONFIG, {})
    sources = config.get("sources") if isinstance(config, dict) else {}
    if not isinstance(sources, dict):
        return set()
    return {str(name) for name, source_class in sources.items() if source_class == "游资心得"}


def legacy_source_name(path: Path) -> str:
    try:
        rel = path.relative_to(LEGACY_RAW_ROOT)
    except ValueError:
        return ""
    return rel.parts[0] if rel.parts else ""


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def sanitize_filename(text: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:80].strip(" ._") or "untitled"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    meta_text = text[4:end]
    body = text[end + 5 :]
    meta: dict[str, str] = {}
    for line in meta_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip("\"'")
    return meta, body


def extract_main_body(body: str) -> str:
    text = body.replace("\r\n", "\n")
    marker = "\n---\n"
    if marker in text:
        text = text.split(marker, 1)[1]
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        if line.startswith("!["):
            continue
        if line.startswith(">"):
            line = line.lstrip(">").strip()
            if line.startswith("图片 OCR"):
                continue
        line = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", line)
        line = re.sub(r"<[^>]+>", " ", line)
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_text(text: str) -> str:
    text = re.sub(r"`{1,3}", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\u3000", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？；\n]+", text)
    return [part.strip(" -:：") for part in parts if len(part.strip()) >= 10]


def tokenize(text: str) -> list[str]:
    terms = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", text)
    out: list[str] = []
    for term in terms:
        lower = term.lower()
        if lower in STOPWORDS or term in STOPWORDS:
            continue
        if re.fullmatch(r"\d+", term):
            continue
        out.append(term)
    return out


def top_terms(text: str, limit: int = 10) -> list[str]:
    counter = Counter(tokenize(text))
    return [term for term, _ in counter.most_common(limit)]


def match_groups(text: str, defs: dict[str, list[str]] | dict[str, dict]) -> list[str]:
    upper = text.upper()
    matched: list[str] = []
    for name, meta in defs.items():
        keywords = meta["keywords"] if isinstance(meta, dict) else meta
        if any(keyword.upper() in upper for keyword in keywords):
            matched.append(name)
    return matched


def score_categories(text: str) -> tuple[list[str], dict[str, int]]:
    upper = text.upper()
    scores: dict[str, int] = {}
    for name, meta in CATEGORY_DEFS.items():
        scores[name] = sum(upper.count(keyword.upper()) for keyword in meta["keywords"])
    ordered = [name for name, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True) if scores[name] > 0]
    if not ordered:
        ordered = ["案例复盘"]
    return ordered, scores


def extract_rules(sentences: list[str], limit: int = 6) -> list[str]:
    rules: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        compact = re.sub(r"\s+", "", sentence)
        if len(compact) < 12 or len(compact) > 120:
            continue
        if not any(hint in compact for hint in RULE_HINTS):
            continue
        if compact in seen:
            continue
        seen.add(compact)
        rules.append(compact)
        if len(rules) >= limit:
            break
    return rules


def extract_evidence(sentences: list[str], keywords: list[str], limit: int = 6) -> list[str]:
    evidence: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        compact = re.sub(r"\s+", "", sentence)
        if len(compact) < 16:
            continue
        if keywords and not any(keyword in compact for keyword in keywords):
            continue
        if compact in seen:
            continue
        seen.add(compact)
        evidence.append(compact[:180])
        if len(evidence) >= limit:
            break
    if evidence:
        return evidence
    fallback: list[str] = []
    for sentence in sentences:
        compact = re.sub(r"\s+", "", sentence)
        if len(compact) >= 24:
            fallback.append(compact[:180])
        if len(fallback) >= min(limit, 3):
            break
    return fallback


def extract_core_points(sentences: list[str], categories: list[str], methods: list[str], themes: list[str]) -> list[str]:
    priority_keywords: list[str] = []
    for name in categories[:3]:
        priority_keywords.extend(CATEGORY_DEFS.get(name, {}).get("keywords", []))
    for name in methods[:3]:
        priority_keywords.extend(METHOD_DEFS.get(name, []))
    for name in themes[:3]:
        priority_keywords.extend(THEME_DEFS.get(name, []))
    points = extract_evidence(sentences, priority_keywords, limit=5)
    return points[:4]


def parse_date(text: str) -> str:
    match = re.search(r"(20\d{2})[-./年](\d{1,2})[-./月](\d{1,2})", text)
    if not match:
        return ""
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def days_since(date_text: str) -> int | None:
    if not date_text:
        return None
    try:
        target = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (datetime.now().date() - target).days


def safe_int(value) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def validation_summary(meta: dict, body_text: str, rules: list[str], evidence: list[str], themes: list[str], methods: list[str]) -> dict:
    image_count = safe_int(meta.get("image_count", 0))
    ocr_count = safe_int(meta.get("ocr_image_count", 0))
    coverage = 1.0 if image_count <= 0 else round(ocr_count / max(1, image_count), 2)
    score = 0
    score += 1 if len(body_text) >= 1200 else 0
    score += 1 if len(rules) >= 3 else 0
    score += 1 if len(evidence) >= 3 else 0
    score += 1 if meta.get("source_url") else 0
    score += 1 if coverage >= 0.5 else 0
    if len(themes) >= 1:
        score += 1
    if len(methods) >= 1:
        score += 1
    if score >= 6:
        level = "high"
    elif score >= 4:
        level = "medium"
    else:
        level = "low"
    return {
        "score": score,
        "level": level,
        "body_length": len(body_text),
        "rule_count": len(rules),
        "evidence_count": len(evidence),
        "image_count": image_count,
        "ocr_image_count": ocr_count,
        "ocr_coverage": coverage,
        "capture_pipeline": meta.get("capture_pipeline", ""),
    }


def verification_points(date_text: str, categories: list[str], methods: list[str], themes: list[str]) -> list[str]:
    points = [
        "验证文章观点是否与次日盘面、竞价强度和核心股承接一致。",
        "验证文中强调的核心方向是否真的成为市场主线，而非一日轮动。",
        "验证建议的买卖节奏是否符合你的仓位和纪律，不得直接照抄。",
    ]
    if methods:
        points.append(f"重点回看模式：{'、'.join(methods[:3])}，确认是否有可重复的触发条件。")
    if themes:
        points.append(f"重点跟踪主题：{'、'.join(themes[:3])}，看 D+1 / D+3 是否延续。")
    age = days_since(date_text)
    if age is not None and age <= 7:
        points.append("这是一篇近 7 天文章，纳入 D+1 / D+3 / D+5 跟踪。")
    return points[:6]


def build_article_record(path: Path, log_path: Path | None) -> dict:
    raw_text = path.read_text(encoding="utf-8", errors="ignore")
    meta, body = parse_frontmatter(raw_text)
    article_body = normalize_text(extract_main_body(body))
    if not article_body:
        article_body = normalize_text(body)
    combined = f"{meta.get('title', '')}\n{article_body}"
    sentences = split_sentences(combined)
    categories, category_scores = score_categories(combined)
    methods = match_groups(combined, METHOD_DEFS)
    themes = match_groups(combined, THEME_DEFS)
    rules = extract_rules(sentences)
    evidence = extract_evidence(
        sentences,
        CATEGORY_DEFS.get(categories[0], {}).get("keywords", []),
        limit=6,
    )
    core_points = extract_core_points(sentences, categories, methods, themes)
    if not rules and core_points:
        rules = core_points[:3]
    top_keywords = top_terms(combined, limit=10)
    title = meta.get("title") or path.stem
    source = meta.get("source") or path.parent.name
    article_date = meta.get("created") or parse_date(f"{path.name}\n{raw_text[:1200]}")
    validation = validation_summary(meta, article_body, rules, evidence, themes, methods)
    verify_points = verification_points(article_date, categories, methods, themes)
    short_hash = sha256_file(path)[:12].lower()
    card_dir = CARD_ROOT / (article_date or "undated") / sanitize_filename(source)
    card_path = card_dir / f"{article_date or 'undated'}_{short_hash}.md"
    record = {
        "raw_rel": rel_path(path),
        "raw_path": to_posix(path),
        "content_hash": sha256_file(path),
        "title": title,
        "source": source,
        "date": article_date,
        "source_url": meta.get("source_url", ""),
        "capture_pipeline": meta.get("capture_pipeline", ""),
        "werss_article_id": meta.get("werss_article_id", ""),
        "mp_id": meta.get("mp_id", ""),
        "images_localized": meta.get("images_localized", ""),
        "image_count": safe_int(meta.get("image_count", 0)),
        "ocr_image_count": safe_int(meta.get("ocr_image_count", 0)),
        "content_form": meta.get("content_form", ""),
        "categories": categories[:4],
        "category_scores": category_scores,
        "methods": methods[:6],
        "themes": themes[:6],
        "top_keywords": top_keywords,
        "core_points": core_points[:4],
        "rules": rules[:6],
        "evidence": evidence[:6],
        "validation": validation,
        "verify_points": verify_points,
        "card_rel": rel_path(card_path),
        "card_path": to_posix(card_path),
        "updated_at": now_text(),
    }
    if log_path is not None:
        log(f"learned {path.name} -> {card_path.name}", log_path)
    return record


def write_article_card(record: dict) -> None:
    path = Path(record["card_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    def yaml_quote(value: object) -> str:
        return str(value or "").replace("\\", "\\\\").replace('"', '\\"')

    frontmatter = [
        "---",
        f"title: \"{yaml_quote(record['title'])}\"",
        f"created: {record['date'] or TODAY}",
        f"updated: {TODAY}",
        "type: youzi_learning_card",
        f"source: \"{yaml_quote(record['source'])}\"",
        f"source_url: \"{yaml_quote(record['source_url'])}\"",
        f"raw_path: \"{yaml_quote(record['raw_rel'])}\"",
        f"capture_pipeline: \"{yaml_quote(record['capture_pipeline'])}\"",
        f"knowledge_level: \"{yaml_quote(record['validation']['level'])}\"",
        f"validation_score: {record['validation']['score']}",
        "---",
        "",
    ]
    lines = frontmatter + [
        f"# {record['title']}",
        "",
        f"- 来源：{record['source']}",
        f"- 日期：{record['date'] or '未知'}",
        f"- RAW：{record['raw_rel']}",
        f"- 原文：{record['source_url'] or '无'}",
        f"- 抓取链路：{record['capture_pipeline'] or 'unknown'}",
        f"- 学习评级：{record['validation']['level']} ({record['validation']['score']})",
        "",
        "## 核心信息",
        "",
    ]
    for point in record["core_points"][:4]:
        lines.append(f"- {point}")
    if not record["core_points"]:
        lines.append("- 该文更多是原始素材，需后续人工复核。")
    lines += [
        "",
        "## 可执行规则",
        "",
    ]
    for rule in record["rules"][:6]:
        lines.append(f"- {rule}")
    if not record["rules"]:
        lines.append("- 暂未自动抽出稳定规则，建议结合原文人工提炼。")
    lines += [
        "",
        "## 分类标签",
        "",
        f"- 主分类：{record['categories'][0] if record['categories'] else '案例复盘'}",
        f"- 次级分类：{'、'.join(record['categories'][1:4]) if len(record['categories']) > 1 else '无'}",
        f"- 模式：{'、'.join(record['methods'][:6]) if record['methods'] else '无'}",
        f"- 主题：{'、'.join(record['themes'][:6]) if record['themes'] else '无'}",
        f"- 关键词：{'、'.join(record['top_keywords'][:10]) if record['top_keywords'] else '无'}",
        "",
        "## 证据摘录",
        "",
    ]
    for sentence in record["evidence"][:6]:
        lines.append(f"- {sentence}")
    if not record["evidence"]:
        lines.append("- 暂无高置信证据摘录。")
    lines += [
        "",
        "## 验证与跟踪",
        "",
        f"- 正文长度：{record['validation']['body_length']}",
        f"- 规则条数：{record['validation']['rule_count']}",
        f"- 证据条数：{record['validation']['evidence_count']}",
        f"- 图片 OCR 覆盖：{record['validation']['ocr_image_count']}/{record['validation']['image_count']} ({record['validation']['ocr_coverage']})",
        "",
    ]
    for point in record["verify_points"]:
        lines.append(f"- {point}")
    lines += [
        "",
        "## 原始资料定位",
        "",
        f"- WeRSS 文章ID：{record['werss_article_id'] or '无'}",
        f"- mp_id：{record['mp_id'] or '无'}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def aggregate_by_source(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["source"]].append(record)
    return grouped


def aggregate_by_category(records: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        category = record["categories"][0] if record["categories"] else "案例复盘"
        grouped[category].append(record)
    return grouped


def write_author_pages(records: list[dict]) -> list[str]:
    AUTHOR_ROOT.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for source, items in sorted(aggregate_by_source(records).items()):
        items = sorted(items, key=lambda item: (item["date"], item["title"]), reverse=True)
        category_counter = Counter(item["categories"][0] for item in items if item["categories"])
        method_counter = Counter(method for item in items for method in item["methods"])
        theme_counter = Counter(theme for item in items for theme in item["themes"])
        path = AUTHOR_ROOT / f"{sanitize_filename(source)}.md"
        lines = [
            f"# {source}",
            "",
            f"- 文章数：{len(items)}",
            f"- 最近更新：{items[0]['date'] or '未知'}",
            f"- 主要分类：{'、'.join(name for name, _ in category_counter.most_common(3)) or '无'}",
            f"- 高频模式：{'、'.join(name for name, _ in method_counter.most_common(6)) or '无'}",
            f"- 高频主题：{'、'.join(name for name, _ in theme_counter.most_common(6)) or '无'}",
            "",
            "## 作者使用方法",
            "",
            "- 先看这位作者最常讨论什么，再决定把它当市场、题材、模式还是纪律素材使用。",
            "- 只吸收可验证、可执行、可复盘的规则，不直接拿作者观点当交易指令。",
            "",
            "## 最近学习卡",
            "",
            "| 日期 | 标题 | 主分类 | 模式 | 学习卡 | RAW |",
            "|---|---|---|---|---|---|",
        ]
        for item in items[:80]:
            lines.append(
                f"| {item['date']} | {item['title'][:80]} | {item['categories'][0] if item['categories'] else '案例复盘'} | {'、'.join(item['methods'][:3])} | {item['card_rel']} | {item['raw_rel']} |"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(rel_path(path))
    return written


def write_category_pages(records: list[dict]) -> list[str]:
    CATEGORY_ROOT.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    grouped = aggregate_by_category(records)
    for category_name, meta in CATEGORY_DEFS.items():
        items = sorted(grouped.get(category_name, []), key=lambda item: (item["date"], item["title"]), reverse=True)
        rule_counter = Counter(rule for item in items for rule in item["rules"])
        theme_counter = Counter(theme for item in items for theme in item["themes"])
        path = CATEGORY_ROOT / f"{sanitize_filename(category_name)}.md"
        lines = [
            f"# {category_name}",
            "",
            f"- 学习问题：{meta['question']}",
            f"- 文章数：{len(items)}",
            f"- 高频主题：{'、'.join(name for name, _ in theme_counter.most_common(6)) or '无'}",
            "",
            "## 高频规则",
            "",
        ]
        for rule, _ in rule_counter.most_common(12):
            lines.append(f"- {rule}")
        if not rule_counter:
            lines.append("- 暂无足够规则样本。")
        lines += [
            "",
            "## 代表文章",
            "",
            "| 日期 | 来源 | 标题 | 模式 | 学习卡 |",
            "|---|---|---|---|---|",
        ]
        for item in items[:80]:
            lines.append(
                f"| {item['date']} | {item['source']} | {item['title'][:80]} | {'、'.join(item['methods'][:3])} | {item['card_rel']} |"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(rel_path(path))
    return written


def write_verify_board(records: list[dict]) -> str:
    VERIFY_ROOT.mkdir(parents=True, exist_ok=True)
    board_path = VERIFY_ROOT / f"游资学习验证看板-{TODAY}.md"
    recent = []
    for record in records:
        age = days_since(record["date"])
        if age is None or age <= 7:
            recent.append((age if age is not None else 999, record))
    recent.sort(key=lambda item: (item[0], item[1]["date"]), reverse=False)
    lines = [
        f"# 游资学习验证看板-{TODAY}",
        "",
        "## 使用方式",
        "",
        "- 只验证最近 7 天仍可能影响盘面的游资文章。",
        "- 重点看 D+1 / D+3 / D+5 是否出现题材延续、核心股承接和模式复现。",
        "- 若文章只在知识层面有价值，但不适合当前市场，不进入作战室。",
        "",
        "## 待验证清单",
        "",
        "| 日期 | 来源 | 标题 | 主题 | 模式 | 学习评级 | 学习卡 |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, record in recent[:200]:
        lines.append(
            f"| {record['date']} | {record['source']} | {record['title'][:80]} | {'、'.join(record['themes'][:3])} | {'、'.join(record['methods'][:3])} | {record['validation']['level']} | {record['card_rel']} |"
        )
    if len(lines) == 9:
        lines.append("| 无 | 无 | 无 | 无 | 无 | 无 | 无 |")
    board_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rel_path(board_path)


def write_master_index(records: list[dict], new_records: list[dict], author_pages: list[str], category_pages: list[str], verify_board: str) -> str:
    WIKI_ROOT.mkdir(parents=True, exist_ok=True)
    source_counter = Counter(record["source"] for record in records)
    category_counter = Counter(record["categories"][0] for record in records if record["categories"])
    theme_counter = Counter(theme for record in records for theme in record["themes"])
    method_counter = Counter(method for record in records for method in record["methods"])
    lines = [
        "# 游资学习总表",
        "",
        f"- 更新时间：{now_text()}",
        f"- 学习卡总数：{len(records)}",
        f"- 本轮新增/更新：{len(new_records)}",
        f"- 作者库页面：{len(author_pages)}",
        f"- 分类库页面：{len(category_pages)}",
        f"- 验证看板：{verify_board}",
        "",
        "## 高频来源",
        "",
        "| 来源 | 数量 |",
        "|---|---:|",
    ]
    for source, count in source_counter.most_common(20):
        lines.append(f"| {source} | {count} |")
    lines += [
        "",
        "## 高频分类",
        "",
        "| 分类 | 数量 |",
        "|---|---:|",
    ]
    for category, count in category_counter.most_common():
        lines.append(f"| {category} | {count} |")
    lines += [
        "",
        "## 高频主题",
        "",
        "| 主题 | 数量 |",
        "|---|---:|",
    ]
    for theme, count in theme_counter.most_common(15):
        lines.append(f"| {theme} | {count} |")
    lines += [
        "",
        "## 高频模式",
        "",
        "| 模式 | 数量 |",
        "|---|---:|",
    ]
    for method, count in method_counter.most_common(15):
        lines.append(f"| {method} | {count} |")
    lines += [
        "",
        "## 最新学习卡",
        "",
        "| 日期 | 来源 | 标题 | 主分类 | 模式 | 主题 | 学习评级 | 学习卡 | RAW |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for record in sorted(records, key=lambda item: (item["date"], item["updated_at"], item["title"]), reverse=True)[:300]:
        lines.append(
            f"| {record['date']} | {record['source']} | {record['title'][:80]} | {record['categories'][0] if record['categories'] else '案例复盘'} | {'、'.join(record['methods'][:3])} | {'、'.join(record['themes'][:3])} | {record['validation']['level']} | {record['card_rel']} | {record['raw_rel']} |"
        )
    MASTER_INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rel_path(MASTER_INDEX)


def write_daily_report(records: list[dict], new_records: list[dict], verify_board: str) -> str:
    report_path = WIKI_ROOT / f"游资学习日报-{TODAY}.md"
    new_records = sorted(new_records, key=lambda item: (item["date"], item["title"]), reverse=True)
    rule_counter = Counter(rule for item in new_records for rule in item["rules"])
    lines = [
        f"# 游资学习日报-{TODAY}",
        "",
        f"- 当日新增/更新：{len(new_records)}",
        f"- 验证看板：{verify_board}",
        "",
        "## 今日新增来源",
        "",
        "| 来源 | 数量 |",
        "|---|---:|",
    ]
    for source, count in Counter(item["source"] for item in new_records).most_common():
        lines.append(f"| {source} | {count} |")
    if len(lines) == 8:
        lines.append("| 无 | 0 |")
    lines += [
        "",
        "## 今日高频规则",
        "",
    ]
    for rule, _ in rule_counter.most_common(12):
        lines.append(f"- {rule}")
    if not rule_counter:
        lines.append("- 今日没有新增规则。")
    lines += [
        "",
        "## 今日学习卡",
        "",
        "| 日期 | 来源 | 标题 | 主分类 | 模式 | 学习卡 |",
        "|---|---|---|---|---|---|",
    ]
    for item in new_records[:200]:
        lines.append(
            f"| {item['date']} | {item['source']} | {item['title'][:80]} | {item['categories'][0] if item['categories'] else '案例复盘'} | {'、'.join(item['methods'][:3])} | {item['card_rel']} |"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rel_path(report_path)


def write_report(report_path: Path, result: dict) -> None:
    lines = [
        "# 游资学习流水线报告",
        "",
        f"- 生成时间：{result['generated_at']}",
        f"- 扫描文章：{result['summary']['scanned']}",
        f"- 新增/更新：{result['summary']['updated']}",
        f"- 跳过未变化：{result['summary']['unchanged']}",
        f"- 学习卡总数：{result['summary']['cards']}",
        "",
        "## 产物",
        "",
        f"- 总表：{result['artifacts']['master_index']}",
        f"- 日报：{result['artifacts']['daily_report']}",
        f"- 验证看板：{result['artifacts']['verify_board']}",
        "",
        "## 本轮更新",
        "",
        "| 日期 | 来源 | 标题 | 分类 | 模式 | 学习卡 |",
        "|---|---|---|---|---|---|",
    ]
    for record in result["updated_records"][:200]:
        lines.append(
            f"| {record['date']} | {record['source']} | {record['title'][:80]} | {record['categories'][0] if record['categories'] else '案例复盘'} | {'、'.join(record['methods'][:3])} | {record['card_rel']} |"
        )
    if len(lines) == 14:
        lines.append("| 无 | 无 | 无 | 无 | 无 | 无 |")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def discover_articles() -> list[Path]:
    roots = [RAW_ROOT, LEGACY_RAW_ROOT, FEISHU_SHORTLINE_ROOT]
    youzi_sources = active_youzi_sources()
    files: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            if not path.is_file():
                continue
            if "sync-conflict" in path.name:
                continue
            if root == LEGACY_RAW_ROOT and youzi_sources and legacy_source_name(path) not in youzi_sources:
                continue
            key = path.resolve().as_posix()
            if key in seen:
                continue
            seen.add(key)
            files.append(path)
    return sorted(files)


def load_state_items(path: Path) -> dict[str, dict]:
    state = load_json(path, {"items": []})
    out: dict[str, dict] = {}
    for item in state.get("items", []):
        raw_rel = item.get("raw_rel")
        if raw_rel:
            out[raw_rel] = item
    return out


def append_registry_updates(records: list[dict]) -> int:
    existing_keys = set()
    for row in read_jsonl(REGISTRY_PATH):
        key = (str(row.get("source_path", "")), str(row.get("content_hash", "")), str(row.get("status", "")))
        existing_keys.add(key)
    rows: list[dict] = []
    for record in records:
        key = (record["raw_path"], record["content_hash"], "youzi_learning_completed")
        if key in existing_keys:
            continue
        rows.append(
            {
                "raw_id": f"{record['content_hash']}:youzi-learning",
                "source_path": record["raw_path"],
                "source_agent": "codex",
                "preferred_ingestor": "codex",
                "status": "youzi_learning_completed",
                "ingested_by": "codex",
                "deepseek_action": "skip",
                "truth_grade": "S3",
                "fate": "B",
                "content_hash": record["content_hash"],
                "ingested_at": now_text() + " +08:00",
                "target_pages": [
                    record["card_rel"],
                    rel_path(MASTER_INDEX),
                ],
                "notes": "游资号文章已完成核心信息提炼、验证清单生成，并写入游资认知体系。",
            }
        )
        existing_keys.add(key)
    append_jsonl(REGISTRY_PATH, rows)
    return len(rows)


def main() -> int:
    global ROOT, RAW_ROOT, LEGACY_RAW_ROOT, FEISHU_SHORTLINE_ROOT, SYSTEM_DIR, SOURCE_CLASS_CONFIG, LOG_DIR, STATE_PATH, REPORT_JSON, REPORT_MD, REGISTRY_PATH, WIKI_ROOT, CARD_ROOT, AUTHOR_ROOT, CATEGORY_ROOT, VERIFY_ROOT, MASTER_INDEX
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--state", default=str(STATE_PATH))
    parser.add_argument("--report-json", default=str(REPORT_JSON))
    parser.add_argument("--report-md", default=str(REPORT_MD))
    parser.add_argument("--log", default=str(LOG_DIR / "youzi-learning.log"))
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true", help="Scan and print the planned result without writing state, reports, registry or cards.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON payload, including updated_records.")
    args = parser.parse_args()

    ROOT = Path(args.root)
    RAW_ROOT = ROOT / "raw" / "09-短线知识" / "游资公众号"
    LEGACY_RAW_ROOT = ROOT / "raw" / "05-研报新闻" / "公众号" / "游资号"
    FEISHU_SHORTLINE_ROOT = ROOT / "raw" / "09-短线知识" / "飞书输入"
    SYSTEM_DIR = ROOT / ".system"
    SOURCE_CLASS_CONFIG = SYSTEM_DIR / "wechat-mp-source-classes.json"
    LOG_DIR = SYSTEM_DIR / "logs"
    STATE_PATH = Path(args.state)
    REPORT_JSON = Path(args.report_json)
    REPORT_MD = Path(args.report_md)
    REGISTRY_PATH = SYSTEM_DIR / "ingest-registry.jsonl"
    WIKI_ROOT = ROOT / "wiki" / "04-L4交易模式与执行" / "游资认知体系"
    CARD_ROOT = WIKI_ROOT / "增量学习卡"
    AUTHOR_ROOT = WIKI_ROOT / "作者库"
    CATEGORY_ROOT = WIKI_ROOT / "分类库"
    VERIFY_ROOT = WIKI_ROOT / "验证看板"
    MASTER_INDEX = WIKI_ROOT / "游资学习总表.md"
    log_path = Path(args.log)

    current_paths = discover_articles()
    state_items = load_state_items(STATE_PATH)
    updated_records: list[dict] = []
    unchanged = 0

    for path in current_paths:
        raw_rel = rel_path(path)
        digest = sha256_file(path)
        existing = state_items.get(raw_rel)
        if not args.full and existing and existing.get("content_hash") == digest:
            unchanged += 1
            continue
        record = build_article_record(path, None if args.dry_run else log_path)
        if not args.dry_run:
            write_article_card(record)
            state_items[raw_rel] = record
        updated_records.append(record)
        if args.limit > 0 and len(updated_records) >= args.limit:
            break

    valid_records = []
    current_set = {rel_path(path) for path in current_paths}
    for raw_rel, item in state_items.items():
        card_path = Path(item.get("card_path", ""))
        if args.limit > 0:
            if card_path.exists():
                valid_records.append(item)
        elif raw_rel in current_set and card_path.exists():
            valid_records.append(item)

    valid_records = sorted(valid_records, key=lambda item: (item["date"], item["title"]), reverse=True)
    if args.dry_run:
        result = {
            "generated_at": now_text(),
            "dry_run": True,
            "summary": {
                "scanned": len(current_paths),
                "would_update": len(updated_records),
                "unchanged": unchanged,
                "existing_cards": len(valid_records),
                "registry_added": 0,
            },
            "artifacts": {
                "state": "not_written",
                "reports": "not_written",
                "registry": "not_written",
                "cards": "not_written",
            },
            "updated_records": updated_records,
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({k: v for k, v in result.items() if k != "updated_records"}, ensure_ascii=False, indent=2))
        return 0

    author_pages = write_author_pages(valid_records)
    category_pages = write_category_pages(valid_records)
    verify_board = write_verify_board(valid_records)
    master_index = write_master_index(valid_records, updated_records, author_pages, category_pages, verify_board)
    daily_report = write_daily_report(valid_records, updated_records, verify_board)
    registry_added = append_registry_updates(updated_records)

    state_payload = {
        "generated_at": now_text(),
        "items": valid_records,
    }
    save_json(STATE_PATH, state_payload)

    result = {
        "generated_at": now_text(),
        "summary": {
            "scanned": len(current_paths),
            "updated": len(updated_records),
            "unchanged": unchanged,
            "cards": len(valid_records),
            "registry_added": registry_added,
        },
        "artifacts": {
            "master_index": master_index,
            "daily_report": daily_report,
            "verify_board": verify_board,
            "author_pages": len(author_pages),
            "category_pages": len(category_pages),
        },
        "updated_records": updated_records,
    }
    save_json(REPORT_JSON, result)
    write_report(REPORT_MD, result)
    output_payload = result if args.json else {k: v for k, v in result.items() if k != "updated_records"}
    payload = json.dumps(output_payload, ensure_ascii=False, indent=2)
    try:
        print(payload)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_payload = payload.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
