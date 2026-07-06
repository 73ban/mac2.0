#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path("/Users/qixinchaye/wiki/73神话")
TZ = dt.timezone(dt.timedelta(hours=8))

RAW_ROOTS = [
    ROOT / "raw/05-研报新闻",
    ROOT / "raw/04-市场数据",
    ROOT / "raw/09-短线知识",
]
L2_ROOT = ROOT / "wiki/02-L2方向题材"
L3_ROOT = ROOT / "wiki/03-L3个股档案"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
WIKI_ROOM = ROOT / "wiki/07-作战室"
SYSTEM = ROOT / ".system"

CATALYST_WORDS = {
    "V2": 8,
    "v2": 8,
    "再发酵": 8,
    "二次": 7,
    "发布": 5,
    "论文": 5,
    "政策": 5,
    "方案": 4,
    "规划": 4,
    "量产": 7,
    "订单": 7,
    "中标": 7,
    "涨价": 7,
    "收购": 6,
    "并购": 6,
    "重组": 6,
    "扩产": 6,
    "突破": 6,
    "认证": 5,
    "客户": 5,
    "供货": 6,
    "制裁": 5,
    "断供": 5,
    "国产替代": 4,
    "先进封装": 4,
    "EDA": 4,
}

RISK_WORDS = {
    "减持": 6,
    "澄清": 6,
    "监管": 5,
    "问询": 5,
    "异动公告": 4,
    "亏损": 4,
    "终止": 5,
    "风险提示": 4,
}

SOURCE_WEIGHTS = {
    "财联社": 10,
    "公告": 10,
    "互动问答": 7,
    "淘股吧": 7,
    "三榜热度合并": 6,
    "热榜": 6,
    "通达信": 5,
    "同花顺": 5,
    "公众号": 4,
}

PRIMARY_APPLY_SOURCES = {"财联社", "公告"}
PRIMARY_RADAR_SOURCES = {"财联社", "公告", "公众号", "淘股吧"}
NON_TRADING_CONCEPTS = {
    "确定性",
    "结构性行情",
    "仓位管理",
    "买在分歧卖在一致",
    "情绪周期",
    "赚钱效应",
    "亏钱效应",
}
SKIP_SOURCE_PATTERNS = {
    "interactive-qa.md",
    "interactive-qa.json",
    "同花顺热榜Top100.json",
    "ths-hot-top100.json",
    "淘股吧热榜100-latest.md",
    "结构化样本.json",
}

IGNORE_DIRS_L2 = {"RAW增量题材卡", "核心题材生命周期"}
IGNORE_DIRS_L3 = {"RAW增量个股卡", "作战室个股雷达卡", "公告事件档案", "总结", "持股态度卡"}
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3})(?!\d)")


@dataclass
class WikiEntity:
    kind: str
    name: str
    path: Path
    aliases: set[str] = field(default_factory=set)


def now() -> dt.datetime:
    return dt.datetime.now(TZ)


def today() -> str:
    return now().date().isoformat()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("|", "/")).strip()


def date_set(date: str, days: int) -> set[str]:
    base = dt.datetime.strptime(date, "%Y-%m-%d").date()
    return {(base - dt.timedelta(days=i)).isoformat() for i in range(max(days, 1))}


def next_trade_date(date: str) -> str:
    day = dt.datetime.strptime(date, "%Y-%m-%d").date() + dt.timedelta(days=1)
    while day.weekday() >= 5:
        day += dt.timedelta(days=1)
    return day.isoformat()


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    meta: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def title_from_text(path: Path, text: str) -> str:
    meta = parse_frontmatter(text)
    if meta.get("title"):
        return clean(meta["title"])
    for line in text.splitlines()[:60]:
        line = line.strip()
        if line.startswith("# "):
            return clean(line[2:])
        if line.startswith("title:"):
            return clean(line.split(":", 1)[1])
    return path.stem


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4 :]
    return text


def load_l2_entities() -> list[WikiEntity]:
    entities: list[WikiEntity] = []
    if not L2_ROOT.exists():
        return entities
    for path in L2_ROOT.rglob("*.md"):
        if any(part in IGNORE_DIRS_L2 for part in path.parts):
            continue
        if "RAW" in path.name or path.name.startswith("."):
            continue
        name = path.stem
        if len(name) < 2:
            continue
        if name in NON_TRADING_CONCEPTS:
            continue
        if re.search(r"-\d{6}$", name):
            continue
        text = read_text(path)
        aliases = {name}
        meta = parse_frontmatter(text)
        if meta.get("title"):
            aliases.add(meta["title"])
        entities.append(WikiEntity(kind="题材", name=name, path=path, aliases={a for a in aliases if len(a) >= 2}))
    return entities


def load_l3_entities() -> list[WikiEntity]:
    entities: list[WikiEntity] = []
    if not L3_ROOT.exists():
        return entities
    for path in L3_ROOT.rglob("*.md"):
        if any(part in IGNORE_DIRS_L3 for part in path.parts):
            continue
        if "RAW" in path.name or "资料映射" in path.name or path.name.startswith("."):
            continue
        text = read_text(path)
        meta = parse_frontmatter(text)
        aliases: set[str] = set()
        code = meta.get("code", "").strip()
        name = meta.get("name", "").strip()
        if code:
            aliases.add(code)
        if name:
            aliases.add(name)
        stem = path.stem
        aliases.add(stem)
        m = re.search(r"(.+?)-(\d{6})$", stem)
        if m:
            aliases.add(m.group(1))
            aliases.add(m.group(2))
        primary = name or stem
        entities.append(WikiEntity(kind="个股", name=primary, path=path, aliases={a for a in aliases if len(a) >= 2}))
    return entities


def candidate_files(date: str, days: int, limit: int) -> list[Path]:
    dates = date_set(date, days)
    files: list[Path] = []
    for root in RAW_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".jsonl", ".txt"}:
                continue
            if any(pattern in path.name for pattern in SKIP_SOURCE_PATTERNS):
                continue
            text_path = str(path)
            if any(d in text_path for d in dates):
                files.append(path)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def source_type(path: Path) -> str:
    text = rel(path)
    for key in SOURCE_WEIGHTS:
        if key in text:
            return key
    return "本地RAW"


def keyword_hits(text: str, weights: dict[str, int]) -> tuple[int, list[str]]:
    score = 0
    hits: list[str] = []
    lower = text.lower()
    for key, weight in weights.items():
        count = lower.count(key.lower())
        if count:
            score += min(count, 3) * weight
            hits.append(key)
    return score, hits


def match_entities(text: str, entities: list[WikiEntity]) -> list[WikiEntity]:
    haystack = text.replace(" ", "")
    matched: list[WikiEntity] = []
    seen: set[Path] = set()
    for entity in entities:
        for alias in sorted(entity.aliases, key=len, reverse=True):
            if len(alias) < 2:
                continue
            if alias in haystack:
                if entity.path not in seen:
                    matched.append(entity)
                    seen.add(entity.path)
                break
    return matched


def has_proximity(text: str, aliases: set[str], words: list[str], window: int = 260) -> bool:
    compact = clean(text)
    if not words:
        return False
    for alias in aliases:
        pos = compact.find(alias)
        while pos >= 0:
            start = max(0, pos - window)
            end = min(len(compact), pos + len(alias) + window)
            near = compact[start:end]
            if any(word in near for word in words):
                return True
            pos = compact.find(alias, pos + len(alias))
    return False


def short_snippet(text: str, title: str, aliases: set[str], limit: int = 180) -> str:
    compact = clean(strip_frontmatter(text))
    positions = [compact.find(alias) for alias in aliases if alias and compact.find(alias) >= 0]
    pos = min(positions) if positions else compact.find(title[:8])
    if pos < 0:
        pos = 0
    start = max(0, pos - 60)
    return compact[start:start + limit]


def score_file(path: Path, text: str, title: str, entity: WikiEntity) -> dict[str, Any] | None:
    cat_score, cat_hits = keyword_hits(title + "\n" + text[:5000], CATALYST_WORDS)
    risk_score, risk_hits = keyword_hits(title + "\n" + text[:5000], RISK_WORDS)
    if not cat_hits and not risk_hits:
        return None
    if not has_proximity(title + "\n" + text[:12000], entity.aliases, cat_hits + risk_hits):
        return None
    source = source_type(path)
    if source not in PRIMARY_RADAR_SOURCES and not any(key in title for key in ("V2", "再发酵", "二次", "发布", "涨价", "量产", "订单")):
        return None
    source_score = SOURCE_WEIGHTS.get(source, 3)
    score = source_score + cat_score - min(risk_score, 12)
    if entity.kind == "题材":
        score += 8
    else:
        score += 5
    if "V2" in cat_hits or "再发酵" in cat_hits or "二次" in cat_hits:
        score += 8
    if score < 14:
        return None
    action = "作战室复核"
    can_apply = source in PRIMARY_APPLY_SOURCES and (
        any(alias in title for alias in entity.aliases)
        or any(word in title for word in ("V2", "再发酵", "二次", "发布", "涨价", "量产", "订单", "政策"))
    )
    if score >= 26 and not risk_hits and can_apply:
        action = "高置信追加Wiki并进入作战室"
    elif score >= 26 and not risk_hits:
        action = "高置信作战室复核"
    elif risk_hits:
        action = "风险/兑现复核"
    return {
        "对象类型": entity.kind,
        "对象": entity.name,
        "对象文件": rel(entity.path),
        "分数": score,
        "动作": action,
        "来源类型": source,
        "标题": title,
        "来源文件": rel(path),
        "催化词": cat_hits,
        "风险词": risk_hits,
        "摘要": short_snippet(text, title, entity.aliases),
    }


def build(date: str, days: int, limit: int) -> dict[str, Any]:
    entities = load_l2_entities() + load_l3_entities()
    hits: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path in candidate_files(date, days, limit):
        text = read_text(path)
        if not text:
            continue
        title = title_from_text(path, text)
        matched = match_entities(title + "\n" + text[:12000], entities)
        for entity in matched[:30]:
            item = score_file(path, text, title, entity)
            if not item:
                continue
            key = (item["对象文件"], item["来源文件"])
            if key in seen:
                continue
            seen.add(key)
            hits.append(item)
    hits.sort(key=lambda x: int(x["分数"]), reverse=True)
    recatalyst = [x for x in hits if x["对象类型"] == "题材" and int(x["分数"]) >= 24]
    stock_updates = [x for x in hits if x["对象类型"] == "个股" and int(x["分数"]) >= 22]
    next_date = next_trade_date(date)
    return {
        "schema": "73wiki-second-catalyst-radar-v1",
        "日期": date,
        "扫描天数": days,
        "生成时间": now().isoformat(timespec="seconds"),
        "下一交易日": next_date,
        "动作清单": {
            "旧题材二次催化": recatalyst[:80],
            "个股增量更新": stock_updates[:120],
            "全部命中": hits[:200],
        },
        "规则": [
            "命中已有L2/L3 Wiki对象，且同一RAW出现催化词或风险词，才进入本雷达。",
            "V2、再发酵、二次、发布、量产、订单、涨价、收购、政策等触发词会提高二次催化权重。",
            "高置信二次催化自动进入下一交易日作战室，但仍需竞价、板块、情绪周期确认。",
            "自动追加Wiki只记录事实、来源和待验证项，不直接生成买入结论。",
        ],
    }


def md_table(headers: list[str], rows: list[dict[str, Any]], keys: list[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    if not rows:
        lines.append("| " + " | ".join(["无"] + [""] * (len(headers) - 1)) + " |")
        return "\n".join(lines)
    for row in rows:
        lines.append("| " + " | ".join(clean(str(row.get(key, ""))) for key in keys) + " |")
    return "\n".join(lines)


def write_report(data: dict[str, Any]) -> tuple[Path, Path]:
    date = data["日期"]
    WIKI_STATS.mkdir(parents=True, exist_ok=True)
    json_path = WIKI_STATS / f"{date}-旧题材二次催化雷达.json"
    md_path = WIKI_STATS / f"{date}-旧题材二次催化雷达.md"
    write_text(json_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    actions = data["动作清单"]
    lines = [
        f"# {date} 旧题材二次催化雷达",
        "",
        f"- 生成时间：{data['生成时间']}",
        f"- 下一交易日：{data['下一交易日']}",
        "",
        "## 规则",
        "",
    ]
    lines.extend(f"- {rule}" for rule in data["规则"])
    lines += ["", "## 旧题材二次催化", ""]
    lines.append(md_table(["对象", "分数", "动作", "来源类型", "标题", "催化词", "来源文件"], actions["旧题材二次催化"], ["对象", "分数", "动作", "来源类型", "标题", "催化词", "来源文件"]))
    lines += ["", "## 个股增量更新", ""]
    lines.append(md_table(["对象", "分数", "动作", "来源类型", "标题", "催化词", "来源文件"], actions["个股增量更新"], ["对象", "分数", "动作", "来源类型", "标题", "催化词", "来源文件"]))
    lines += ["", "## 全部命中", ""]
    lines.append(md_table(["对象类型", "对象", "分数", "动作", "标题", "风险词"], actions["全部命中"], ["对象类型", "对象", "分数", "动作", "标题", "风险词"]))
    lines.append("")
    write_text(md_path, "\n".join(lines))
    write_text(SYSTEM / "second-catalyst-radar.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return json_path, md_path


def append_once(path: Path, marker: str, block: str) -> bool:
    text = read_text(path)
    if marker in text:
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    write_text(path, text + "\n" + block.strip() + "\n")
    return True


def apply_wiki_updates(data: dict[str, Any], max_apply: int) -> list[dict[str, str]]:
    applied: list[dict[str, str]] = []
    candidates = data["动作清单"]["旧题材二次催化"] + data["动作清单"]["个股增量更新"]
    for item in candidates:
        if len(applied) >= max_apply:
            break
        if "追加Wiki" not in item["动作"]:
            continue
        path = ROOT / item["对象文件"]
        source = item["来源文件"]
        marker = f"source:{source}"
        block = "\n".join([
            f"## {data['日期']} 自动增量：二次催化/资料更新",
            "",
            f"- 对象类型：{item['对象类型']}",
            f"- 触发动作：{item['动作']}",
            f"- 来源类型：{item['来源类型']}",
            f"- 标题：{item['标题']}",
            f"- 催化词：{', '.join(item['催化词']) if item['催化词'] else '无'}",
            f"- 风险词：{', '.join(item['风险词']) if item['风险词'] else '无'}",
            f"- 来源文件：`{source}`",
            f"- 去重标记：source:{source}",
            "",
            "### 摘要",
            "",
            item["摘要"],
            "",
            "### 待验证",
            "",
            "- D+1：是否有热度延续、板块共振、核心股承接。",
            "- D+3：是否从消息刺激转为主线扩散，或开始兑现。",
            "- D+5：是否能沉淀为有效题材生命周期样本。",
        ])
        if append_once(path, marker, block):
            applied.append({"对象": item["对象"], "文件": item["对象文件"], "来源": source})
    return applied


def write_warroom(data: dict[str, Any]) -> Path | None:
    rows = [item for item in data["动作清单"]["旧题材二次催化"] if "追加Wiki" in item["动作"]]
    if not rows:
        return None
    out = WIKI_ROOM / f"{data['下一交易日']}-旧题材二次催化候选.md"
    lines = [
        f"# {data['下一交易日']} 旧题材二次催化候选",
        "",
        f"- 生成时间：{data['生成时间']}",
        f"- 来源雷达：`wiki/09-统计与进化/{data['日期']}-旧题材二次催化雷达.md`",
        "",
        "## 候选题材",
        "",
        md_table(["题材", "分数", "动作", "标题", "催化词", "来源文件"], rows, ["对象", "分数", "动作", "标题", "催化词", "来源文件"]),
        "",
        "## 盘前使用规则",
        "",
        "- 先看旧龙头是否确认，不直接因消息追后排。",
        "- 再看新分支是否出现低位换手前排。",
        "- 题材热但容量票不跟，按冲高兑现处理。",
        "- 每个候选都必须进入 D+1/D+3/D+5 验证。",
        "",
    ]
    write_text(out, "\n".join(lines))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=today())
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--limit", type=int, default=1600)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--apply-wiki", action="store_true")
    parser.add_argument("--max-apply", type=int, default=20)
    args = parser.parse_args()

    data = build(args.date, args.days, args.limit)
    if args.write:
        _, md_path = write_report(data)
        room = write_warroom(data)
        applied = apply_wiki_updates(data, args.max_apply) if args.apply_wiki else []
        if applied:
            data["自动追加Wiki"] = applied
            write_report(data)
        print(str(md_path))
        if room:
            print(str(room))
        if applied:
            print(json.dumps({"自动追加Wiki": applied}, ensure_ascii=False))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
