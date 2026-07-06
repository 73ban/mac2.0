#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_TRADE = ROOT / "raw/01-交割单"
RAW_REVIEW = ROOT / "raw/02-每日复盘"
WIKI_TRADE = ROOT / "wiki/06-持仓与资金管理"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
DICT_PATH = ROOT / "data/facts/shortline_mode_dictionary.json"
OUT_ROOT = ROOT / "raw/11-Codex分析产物/交易模式逐笔归因"
FACTS = ROOT / "data/facts/trade_mode_attributions.jsonl"

DATE_RE = re.compile(r"(20\d{2})[-./年]?(0\d|1[0-2])[-./月]?([0-3]\d)")
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|8\d{5})(?!\d)")
BUY_WORD_RE = re.compile(r"(融资买入|担保品买入|证券买入|买入|加仓|建仓)")
BAD_STATUS_RE = re.compile(r"(已撤|废单|未成交|已报|撤单|失败)")

MODE_RULES = [
    ("分歧转一致", ["弱转强", "分歧转一致", "超预期", "低开转强", "开盘拉升", "回封"], "出现弱转强/分歧转强语言"),
    ("趋势主升", ["趋势主升", "主升浪", "趋势", "容量", "中军", "抱团", "新高"], "出现趋势/容量/中军语言"),
    ("一进二回封", ["一进二", "二板", "首板次日", "回封", "换手回封"], "出现一进二/回封语言"),
    ("龙头战法", ["龙头", "总龙头", "市场龙头", "空间板", "核心票", "辨识度"], "出现龙头/核心辨识度语言"),
    ("断板反包", ["断板", "反包", "首阴", "N字", "二波", "修复"], "出现断板反包/修复语言"),
    ("首板新题材试错", ["首板", "新题材", "试错", "低位首板", "新方向"], "出现首板新题材语言"),
    ("强板块前排半路", ["半路", "板块拉升", "早盘拉升", "主动拉升", "前排", "板块整体"], "出现板块前排半路语言"),
    ("前排确认打板", ["打板", "涨停价", "封板", "排板", "板上", "确认板"], "出现打板/封板语言"),
    ("主线核心低吸", ["低吸", "分歧低吸", "核心低吸", "跌停附近", "恐慌", "撬板", "承接"], "出现低吸/恐慌承接语言"),
    ("冰点恐慌修复", ["冰点", "恐慌", "反核", "撬板", "退潮后修复", "不连续退潮"], "出现冰点恐慌修复语言"),
    ("高低切补涨", ["高低切", "低位补涨", "补涨", "切低位", "低位"], "出现高低切/补涨语言"),
    ("龙回头", ["龙回头", "回踩", "二波低吸", "龙头二波"], "出现龙回头/二波语言"),
    ("旧主线回流", ["旧主线", "老主线", "回流", "老龙", "题材回流"], "出现旧主线回流语言"),
    ("一字定方向扩散", ["一字", "一字板", "扩散", "买不到龙头", "换手前排"], "出现一字定方向扩散语言"),
    ("绕异动控节奏", ["绕异动", "异动", "偏离值", "监管空间", "控异动"], "出现绕异动/监管空间语言"),
    ("出监管再选择", ["出监管", "监管解除", "复牌", "小黑屋"], "出现出监管再选择语言"),
    ("容量中军锚定", ["中军", "容量票", "成交额", "大成交", "锚"], "出现容量中军语言"),
    ("后排不碰", ["后排", "杂毛", "方向对票不对", "不碰"], "出现后排规避语言"),
]

GENERATED_BLOCKS = [
    ("<!-- codex-trade-mode-backfill:start -->", "<!-- codex-trade-mode-backfill:end -->"),
    ("<!-- codex-dplus-stats:start -->", "<!-- codex-dplus-stats:end -->"),
]


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if data.startswith(b"PK\x03\x04"):
        return ""
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return strip_generated_blocks(data.decode(encoding))
        except UnicodeDecodeError:
            continue
    return strip_generated_blocks(data.decode("utf-8", errors="ignore"))


def strip_generated_blocks(text: str) -> str:
    for start, end in GENERATED_BLOCKS:
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
        text = pattern.sub("", text)
    return text


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                seen.add(json.loads(line).get("attribution_id"))
            except Exception:
                continue
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            if row.get("attribution_id") in seen:
                continue
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def replace_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")


def rel(path: Path | None) -> str:
    if not path:
        return ""
    try:
        return path.relative_to(ROOT).as_posix()
    except Exception:
        return str(path)


def norm_date(raw: str) -> str | None:
    match = DATE_RE.search(raw)
    if not match:
        return None
    y, m, d = match.groups()
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return None


def discover_dates(limit: int) -> list[str]:
    dates = set()
    today = date.today().isoformat()
    for base in (RAW_TRADE, RAW_REVIEW, WIKI_TRADE, WIKI_STATS):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or ".stversions" in path.parts or "sync-conflict" in path.name:
                continue
            d = norm_date(path.as_posix())
            if d and d <= today:
                dates.add(d)
    return sorted(dates, reverse=True)[:limit]


def find_trade_files(d: str) -> list[Path]:
    files: list[Path] = []
    candidates = [
        RAW_TRADE / d / f"{d}-交割单.md",
        RAW_TRADE / d / "交割单.md",
        RAW_TRADE / f"{d}-交割单.md",
        WIKI_TRADE / f"{d}-交割单.md",
    ]
    files.extend(path for path in candidates if path.exists())
    for base in (RAW_TRADE / d, RAW_TRADE, WIKI_TRADE):
        if not base.exists():
            continue
        for path in sorted(base.glob(f"{d}*.md")):
            if path not in files and "交割单" in path.name:
                files.append(path)
    return files


def find_review_files(d: str) -> list[Path]:
    files: list[Path] = []
    candidates = [
        RAW_REVIEW / f"{d}-复盘.md",
        RAW_REVIEW / f"{d}-盘后复盘RAW.md",
        RAW_REVIEW / f"{d}-飞书复盘RAW.md",
        RAW_REVIEW / f"{d}-口述原文.md",
        WIKI_STATS / f"{d}-复盘.md",
    ]
    files.extend(path for path in candidates if path.exists())
    for base in (RAW_REVIEW, WIKI_STATS):
        if not base.exists():
            continue
        for path in sorted(base.glob(f"{d}*.md")):
            if path not in files and ("复盘" in path.name or "口述" in path.name):
                files.append(path)
    return files[:8]


def split_md_table(line: str) -> list[str]:
    if "|" not in line:
        return []
    return [part.strip().strip("*` ") for part in line.strip().strip("|").split("|")]


def parse_trade_line(line: str, source: Path) -> dict | None:
    if not line.lstrip().startswith("|"):
        return None
    if not BUY_WORD_RE.search(line):
        return None
    if BAD_STATUS_RE.search(line):
        return None
    code_match = CODE_RE.search(line)
    if not code_match:
        return None
    code = code_match.group(0)
    cells = split_md_table(line)
    name = ""
    time = ""
    action = ""
    price = ""
    amount = ""
    if cells:
        action_idx = -1
        for idx, cell in enumerate(cells):
            if code in cell:
                inline_name = cell.replace(code, "").strip(" -_/")
                if inline_name:
                    name = inline_name
                elif idx + 1 < len(cells):
                    name = cells[idx + 1]
                if not time:
                    for left in reversed(cells[:idx]):
                        m = re.search(r"\d{1,2}:\d{2}(?::\d{2})?", left)
                        if m:
                            time = m.group(0)
                            break
            if BUY_WORD_RE.search(cell):
                action = cell
                action_idx = idx
        tail_cells = cells[action_idx + 1 :] if action_idx >= 0 else cells
        num_items = []
        for idx, cell in enumerate(tail_cells):
            cleaned = cell.replace("—", "")
            if not re.fullmatch(r"-?\d+(?:,\d{3})*(?:\.\d+)?", cleaned):
                continue
            try:
                value = float(cleaned.replace(",", ""))
            except Exception:
                continue
            num_items.append((idx, cell, value))
        money_candidates = []
        for idx, cell, value in num_items:
            compact = cell.replace(",", "")
            if "," in cell and value > 0:
                money_candidates.append((idx, cell))
                continue
            if "." in cell:
                continue
            if len(compact) >= 9 and not "," in cell:
                continue
            if compact.isdigit() and int(compact) >= 1000:
                money_candidates.append((idx, cell))
        money_idx = money_candidates[-1][0] if money_candidates else None
        price_candidates = [
            cell
            for idx, cell, value in num_items
            if "." in cell and "," not in cell and value > 0 and value <= 5000 and (money_idx is None or idx < money_idx)
        ]
        if price_candidates:
            price = price_candidates[-1]
        elif num_items:
            price = num_items[0][1]
        if money_candidates:
            amount = money_candidates[-1][1]
        elif num_items:
            amount = num_items[-1][1]
    if not name:
        tail = line[code_match.end(): code_match.end() + 30]
        m = re.search(r"([\u4e00-\u9fa5A-Za-z＊*STst]{2,12})", tail)
        if m:
            name = m.group(1)
    if not action:
        action = BUY_WORD_RE.search(line).group(1)
    return {
        "code": code,
        "name": name,
        "time": time,
        "action": action,
        "price": price,
        "amount": amount,
        "source": rel(source),
        "raw_line": line.strip(),
    }


def parse_trade_file(path: Path) -> list[dict]:
    text = read_text(path)
    trades = []
    for line in text.splitlines():
        item = parse_trade_line(line, path)
        if item:
            trades.append(item)
    return trades


def merge_trades(trades: list[dict]) -> list[dict]:
    merged: dict[tuple, dict] = {}
    for item in trades:
        key = (item.get("code"), item.get("time"), item.get("action"), item.get("price"), item.get("amount"), item.get("raw_line"))
        merged[key] = item
    return list(merged.values())


def stock_context(code: str, name: str, review_text: str) -> str:
    if not review_text:
        return ""
    keys = [code]
    if name:
        keys.append(name)
    chunks = []
    lines = review_text.splitlines()
    for idx, line in enumerate(lines):
        if any(key and key in line for key in keys):
            start = max(0, idx - 5)
            end = min(len(lines), idx + 14)
            chunks.append("\n".join(lines[start:end]))
    if chunks:
        return "\n---\n".join(chunks)[:5000]
    return review_text[:1200]


def infer_modes(trade: dict, context: str, market_context: str) -> dict:
    hay = f"{trade.get('raw_line','')}\n{context}\n{market_context}"
    scores = defaultdict(int)
    evidence = defaultdict(list)
    for mode, words, reason in MODE_RULES:
        for word in words:
            if word and word in hay:
                scores[mode] += 1
                if len(evidence[mode]) < 4:
                    evidence[mode].append(f"{reason}：{word}")
    if "涨停价" in hay or "封板" in hay or "排板" in hay:
        scores["前排确认打板"] += 2
        evidence["前排确认打板"].append("交易或复盘出现涨停/封板/排板")
    if "跌停" in hay or "撬板" in hay or "恐慌" in hay:
        scores["冰点恐慌修复"] += 2
        scores["主线核心低吸"] += 1
        evidence["冰点恐慌修复"].append("交易语境出现跌停/撬板/恐慌")
    if "机器人" in hay and ("低位" in hay or "高低切" in hay):
        scores["高低切补涨"] += 2
        evidence["高低切补涨"].append("机器人低位/高低切语境")
    if "并购" in hay or "重组" in hay:
        scores["龙头战法"] += 1
        evidence["龙头战法"].append("并购/重组高辨识度事件驱动")
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if ordered:
        primary = ordered[0][0]
        secondary = [name for name, _ in ordered[1:4]]
        top_score = ordered[0][1]
        confidence = "high" if top_score >= 4 else "medium" if top_score >= 2 else "low"
    else:
        primary = "待人工归因"
        secondary = []
        confidence = "low"
        evidence[primary].append("交割单和复盘未出现足够明确的模式词")
    return {
        "primary_mode": primary,
        "secondary_modes": secondary,
        "mode_source": "Codex推定",
        "confidence": confidence,
        "evidence": (evidence.get(primary) or [])[:6],
    }


def market_context(review_text: str) -> str:
    keys = ("市场", "情绪", "退潮", "修复", "主线", "板块", "涨停", "跌停", "成交")
    lines = [line for line in review_text.splitlines() if any(key in line for key in keys)]
    return "\n".join(lines[:80])[:3000]


def build_for_dates(dates: list[str]) -> list[dict]:
    rows: list[dict] = []
    for d in dates:
        trade_files = find_trade_files(d)
        review_files = find_review_files(d)
        trades = []
        for path in trade_files:
            trades.extend(parse_trade_file(path))
        trades = merge_trades(trades)
        review_text = "\n\n".join(read_text(path) for path in review_files)
        mctx = market_context(review_text)
        for idx, trade in enumerate(trades, start=1):
            context = stock_context(trade["code"], trade.get("name", ""), review_text)
            infer = infer_modes(trade, context, mctx)
            digest = hashlib.sha1(f"{d}|{trade.get('code')}|{trade.get('raw_line','')}".encode("utf-8")).hexdigest()[:12]
            row = {
                "attribution_id": f"{d}:{idx}:{trade['code']}:{trade.get('time') or '-'}:{digest}",
                "date": d,
                "trade_index": idx,
                **trade,
                **infer,
                "context_excerpt": re.sub(r"\s+", " ", context).strip()[:500],
                "review_sources": [rel(path) for path in review_files],
            }
            rows.append(row)
    return rows


def render_md(rows: list[dict], dates: list[str]) -> str:
    by_date = defaultdict(list)
    for row in rows:
        by_date[row["date"]].append(row)
    lines = [
        f"# 最近{len(dates)}个日期逐笔交易模式归因",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "- 归因来源：Codex根据交割单、复盘上下文、模式词典自动推定。",
        "- 重要边界：这是待校准归因，不等于用户当时明确口述。",
        "",
        "## 总览",
        "",
        "| 日期 | 买入笔数 | high | medium | low |",
        "|---|---:|---:|---:|---:|",
    ]
    for d in dates:
        items = by_date.get(d, [])
        counts = defaultdict(int)
        for item in items:
            counts[item["confidence"]] += 1
        lines.append(f"| {d} | {len(items)} | {counts['high']} | {counts['medium']} | {counts['low']} |")

    lines += ["", "## 逐笔归因", ""]
    for d in dates:
        items = by_date.get(d, [])
        if not items:
            continue
        lines += [f"### {d}", "", "| # | 时间 | 股票 | 操作 | 主模式 | 辅助模式 | 来源 | 置信度 | 推定依据 | 原始行 |", "|---:|---|---|---|---|---|---|---|---|---|"]
        for item in items:
            evidence = "；".join(item.get("evidence") or []) or "待人工补充"
            secondary = "、".join(item.get("secondary_modes") or [])
            raw_line = item.get("raw_line", "").replace("|", "/")[:180]
            lines.append(
                f"| {item['trade_index']} | {item.get('time') or '-'} | {item.get('name') or ''} {item['code']} | {item.get('action') or ''} | {item['primary_mode']} | {secondary} | {item['mode_source']} | {item['confidence']} | {evidence} | {raw_line} |"
            )
        lines.append("")
    lines += [
        "## 后续处理",
        "",
        "- high：可先进入模式统计，但仍保留可修正。",
        "- medium：进入待校准队列，优先看大亏/大赚交易。",
        "- low：不能进入正式统计，只作为缺口提醒。",
    ]
    return "\n".join(lines) + "\n"


def render_summary(rows: list[dict]) -> str:
    mode_counts = defaultdict(int)
    confidence_counts = defaultdict(int)
    for row in rows:
        mode_counts[row["primary_mode"]] += 1
        confidence_counts[row["confidence"]] += 1
    lines = [
        f"# {date.today().isoformat()} 逐笔交易模式归因汇总",
        "",
        f"- 样本笔数：{len(rows)}",
        f"- high：{confidence_counts['high']}；medium：{confidence_counts['medium']}；low：{confidence_counts['low']}",
        "",
        "## 主模式分布",
        "",
        "| 主模式 | 笔数 |",
        "|---|---:|",
    ]
    for mode, count in sorted(mode_counts.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"| {mode} | {count} |")
    lines += [
        "",
        "## 说明",
        "",
        "这是自动归因第一版。用户没有口述模式的交易，均标注为 `Codex推定`，后续按飞书校准和D+验证修正。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--date", action="append", help="指定日期，可重复。默认自动取最近日期。")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--replace", action="store_true", help="重写事实层JSONL，适合全量重跑，避免生成块污染或旧规则残留。")
    args = parser.parse_args()

    dates = sorted(args.date, reverse=True) if args.date else discover_dates(args.limit)
    rows = build_for_dates(dates)
    today = date.today().isoformat()
    out_dir = OUT_ROOT / today
    payload = {
        "schema": "73wiki-trade-mode-attribution-enrich-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dates": dates,
        "row_count": len(rows),
        "rows": rows,
    }
    if args.write:
        out_dir.mkdir(parents=True, exist_ok=True)
        write_text(out_dir / "recent-trade-mode-attribution.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        write_text(out_dir / "recent-trade-mode-attribution.md", render_md(rows, dates))
        write_text(WIKI_STATS / f"{today}-逐笔交易模式归因汇总.md", render_summary(rows))
        if args.replace:
            replace_jsonl(FACTS, rows)
        else:
            append_jsonl(FACTS, rows)
    print(json.dumps({"ok": True, "dates": len(dates), "rows": len(rows), "output": rel(out_dir / "recent-trade-mode-attribution.md") if args.write else ""}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
