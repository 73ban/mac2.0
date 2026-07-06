#!/usr/bin/env python3
"""Rank fresh catalysts and generate war-room change alerts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW_ROOTS = [
    ROOT / "raw" / "05-研报新闻",
    ROOT / "raw" / "04-市场数据",
]
OUT_DIR = ROOT / ".llm-wiki" / "catalyst-radar"
WIKI_ROOM = ROOT / "wiki" / "07-作战室"
WIKI_STATS = ROOT / "wiki" / "09-统计与进化"
PENDING_DIR = ROOT / ".system" / "feishu-notify-pending"
STATE_PATH = ROOT / ".system" / "catalyst-radar-state.json"


BULLISH_WEIGHTS = {
    "国务院": 5,
    "发改委": 4,
    "工信部": 4,
    "财政部": 4,
    "商务部": 4,
    "证监会": 4,
    "政策": 3,
    "并购": 5,
    "重组": 5,
    "收购": 4,
    "资产注入": 5,
    "涨价": 5,
    "缺货": 4,
    "供给收缩": 4,
    "订单": 4,
    "中标": 4,
    "英伟达": 4,
    "NVIDIA": 4,
    "AI": 2,
    "算力": 3,
    "CPO": 4,
    "光模块": 4,
    "PCB": 4,
    "铜缆": 4,
    "液冷": 3,
    "HBM": 4,
    "存储": 4,
    "半导体": 3,
    "机器人": 3,
    "固态电池": 3,
    "核聚变": 3,
    "MLCC": 4,
    "关税": 3,
    "制裁": 3,
}

RISK_WEIGHTS = {
    "外围大跌": 6,
    "美股大跌": 6,
    "纳指大跌": 6,
    "日经大跌": 5,
    "A50": 4,
    "离岸人民币": 4,
    "汇率": 3,
    "监管": 5,
    "问询": 5,
    "澄清": 4,
    "减持": 5,
    "亏损": 4,
    "退潮": 5,
    "补跌": 5,
    "跌停": 5,
    "负反馈": 5,
    "高标": 3,
    "异动": 4,
    "停牌": 4,
}

MARKET_RISK_KEYS = {"外围大跌", "美股大跌", "纳指大跌", "日经大跌", "A50", "离岸人民币", "汇率"}
MARKET_SNAPSHOT_PATTERNS = (
    "热榜",
    "三榜热度合并",
    "每日涨停全景",
    "通达信涨停原因",
    "通达信热榜",
    "同花顺热榜",
    "淘股吧热榜",
    "龙虎榜全量",
)
ACTIONABLE_SOURCE_PATTERNS = (
    "财联社",
    "公告",
    "互动问答",
    "公众号",
    "研报新闻",
)
BROAD_PACKAGE_PATTERNS = (
    "Top100",
    "热榜100",
    "三榜热度合并",
    "每日公告全量",
    "公告全量",
    "盘前纪要",
    "财经早餐",
    "周复盘",
    "复盘：",
    "板块已进入右侧",
    "板块进入右侧",
    "周末发酵事件",
    "事件最全梳理",
    "最全梳理",
    "合集",
)


@dataclass
class StockHit:
    code: str
    name: str
    rank: int | None = None
    change_percent: float | None = None
    is_warroom: bool = False


@dataclass
class Catalyst:
    fingerprint: str
    title: str
    source: str
    path: str
    time_text: str
    score: int
    bullish_score: int
    risk_score: int
    action: str
    reason: str
    stock_hits: list[StockHit] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("|", "/")).lower()


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


def parse_time(value: str, fallback_mtime: float) -> datetime:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except Exception:
            pass
    return datetime.fromtimestamp(fallback_mtime)


def title_from_text(path: Path, text: str, meta: dict[str, str]) -> str:
    if meta.get("title"):
        return meta["title"]
    for line in text.splitlines()[:80]:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def keyword_score(text: str, weights: dict[str, int]) -> tuple[int, list[str]]:
    score = 0
    hits = []
    lower = text.lower()
    for key, weight in weights.items():
        count = lower.count(key.lower())
        if count:
            score += min(3, count) * weight
            hits.append(key)
    return min(score, 36), hits


def latest_hotlist_rows() -> list[dict[str, Any]]:
    payload = read_json(ROOT / ".llm-wiki" / "ths-hotlist" / "latest-ths-hotlist.json", {})
    rows = payload.get("rows") if isinstance(payload, dict) else []
    return rows if isinstance(rows, list) else []


def latest_warroom_stocks() -> set[str]:
    stocks: set[str] = set()
    payload = read_json(ROOT / ".llm-wiki" / "warroom-skeleton" / "latest-warroom-skeleton.json", {})
    for key in ("primary",):
        item = payload.get(key) if isinstance(payload, dict) else {}
        if isinstance(item, dict):
            if item.get("code"):
                stocks.add(str(item["code"]))
            if item.get("name"):
                stocks.add(str(item["name"]))
    for key in ("backups", "candidates"):
        items = payload.get(key) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("code"):
                stocks.add(str(item["code"]))
            if item.get("name"):
                stocks.add(str(item["name"]))
    return stocks


def stock_hits(text: str, hot_rows: list[dict[str, Any]], warroom: set[str]) -> tuple[list[StockHit], int]:
    hits: list[StockHit] = []
    boost = 0
    haystack = text.replace(" ", "")
    for row in hot_rows[:100]:
        code = str(row.get("code") or "").strip()
        name = str(row.get("name") or "").strip()
        if not code and not name:
            continue
        if (code and code in haystack) or (name and name in haystack):
            rank = int(row.get("rank") or 999)
            change = row.get("changePercent")
            try:
                change_f = float(change)
            except Exception:
                change_f = None
            is_warroom = code in warroom or name in warroom
            hits.append(StockHit(code=code, name=name, rank=rank, change_percent=change_f, is_warroom=is_warroom))
            if rank <= 10:
                boost += 6
            elif rank <= 30:
                boost += 4
            else:
                boost += 2
            if change_f is not None and change_f >= 19.5:
                boost += 4
            elif change_f is not None and change_f >= 9.5:
                boost += 2
            if is_warroom:
                boost += 6
    return hits[:8], min(boost, 28)


def source_boost(source: str, path: Path) -> int:
    text = f"{source} {path.as_posix()}"
    if "财联社" in text:
        return 4
    if "游资号" in text or "公众号" in text:
        return 3
    if "市场数据" in text:
        return 2
    return 1


def is_market_snapshot(path: Path, title: str = "") -> bool:
    text = f"{path.as_posix()} {title}"
    if "raw/04-市场数据" not in path.as_posix():
        return False
    return any(pattern in text for pattern in MARKET_SNAPSHOT_PATTERNS)


def is_actionable_message(path: Path, title: str = "") -> bool:
    text = f"{path.as_posix()} {title}"
    if is_market_snapshot(path, title):
        return False
    if any(pattern in text for pattern in BROAD_PACKAGE_PATTERNS):
        return False
    return any(pattern in text for pattern in ACTIONABLE_SOURCE_PATTERNS)


def collect_raw_files(lookback_hours: int, limit: int) -> list[Path]:
    cutoff = datetime.now() - timedelta(hours=lookback_hours)
    files: list[Path] = []
    for root in RAW_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            if not path.is_file() or "sync-conflict" in path.name or ".stversions" in path.parts:
                continue
            try:
                if datetime.fromtimestamp(path.stat().st_mtime) >= cutoff:
                    files.append(path)
            except Exception:
                continue
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def rank_file(path: Path, hot_rows: list[dict[str, Any]], warroom: set[str], max_age_hours: int = 18) -> Catalyst | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    meta = parse_frontmatter(text)
    title = title_from_text(path, text, meta)
    if is_market_snapshot(path, title):
        return None
    source = meta.get("source") or path.parent.name
    time_dt = parse_time(
        meta.get("info_time") or meta.get("published_at") or meta.get("created_at") or meta.get("created") or "",
        path.stat().st_mtime,
    )
    age_hours = max(0.0, (datetime.now() - time_dt).total_seconds() / 3600)
    if age_hours > max_age_hours:
        return None
    search = f"{title}\n{text[:12000]}"
    bullish, bullish_keys = keyword_score(search, BULLISH_WEIGHTS)
    risk, risk_keys = keyword_score(search, RISK_WEIGHTS)
    hits, stock_boost = stock_hits(search, hot_rows, warroom)
    fresh = 5 if age_hours <= 1 else 4 if age_hours <= 3 else 2 if age_hours <= 12 else 1
    score = bullish + risk + stock_boost + source_boost(source, path) + fresh
    if score < 7 and not hits:
        return None
    market_risk = any(key in risk_keys for key in MARKET_RISK_KEYS)
    if market_risk and risk >= 8 and risk >= bullish:
        action = "防守/推倒重做复核"
    elif risk >= 18 and risk > bullish + 6:
        action = "风险降级复核"
    elif any(hit.is_warroom for hit in hits) and score >= 14:
        action = "作战室调入/调出复核"
    elif hits and score >= 12:
        action = "候选票加权复核"
    elif bullish >= 8:
        action = "题材权重上调观察"
    else:
        action = "记录观察"
    reason_bits = []
    if bullish_keys:
        reason_bits.append("催化词：" + "、".join(bullish_keys[:6]))
    if risk_keys:
        reason_bits.append("风险词：" + "、".join(risk_keys[:6]))
    if hits:
        reason_bits.append("关联热榜/作战室：" + "、".join(f"{h.name}{h.code}" for h in hits[:5]))
    reason = "；".join(reason_bits) or "近期 RAW 消息进入低分观察。"
    fp_raw = f"{source}|{title}|{path.relative_to(ROOT)}"
    return Catalyst(
        fingerprint=hashlib.sha1(fp_raw.encode("utf-8")).hexdigest()[:16],
        title=title[:140],
        source=source,
        path=str(path.relative_to(ROOT)),
        time_text=time_dt.strftime("%Y-%m-%d %H:%M:%S"),
        score=score,
        bullish_score=bullish,
        risk_score=risk,
        action=action,
        reason=reason,
        stock_hits=hits,
        keywords=sorted(set(bullish_keys + risk_keys), key=(bullish_keys + risk_keys).index),
    )


def catalyst_to_dict(item: Catalyst) -> dict[str, Any]:
    return {
        "fingerprint": item.fingerprint,
        "title": item.title,
        "source": item.source,
        "path": item.path,
        "time": item.time_text,
        "score": item.score,
        "bullishScore": item.bullish_score,
        "riskScore": item.risk_score,
        "action": item.action,
        "reason": item.reason,
        "keywords": item.keywords,
        "stockHits": [hit.__dict__ for hit in item.stock_hits],
    }


def render_md(date: str, generated_at: str, top: list[Catalyst]) -> str:
    lines = [
        f"# {date} 盘中重大消息雷达Top10",
        "",
        f"更新时间：{generated_at}",
        "",
        "## 用法",
        "",
        "本页每 15 分钟跟随云数据连接器刷新。它不直接替你买卖，只做三件事：重大消息排序、作战室变更建议、防守重做提醒。",
        "",
        "## Top10",
        "",
        "| 排名 | 分数 | 动作 | 消息 | 关联票 | 理由 | 来源 |",
        "|---:|---:|---|---|---|---|---|",
    ]
    for idx, item in enumerate(top[:10], 1):
        stocks = "、".join(f"{hit.name}{hit.code}" for hit in item.stock_hits) or "-"
        title = item.title.replace("|", "/")
        reason = item.reason.replace("|", "/")
        lines.append(f"| {idx} | {item.score} | {item.action} | {title} | {stocks} | {reason} | `{item.path}` |")
    if not top:
        lines.append("| - | - | - | 暂无达到阈值的新增消息 | - | - | - |")
    lines.extend(
        [
        "",
        "## 给用户校准的问题",
        "",
        "只有单条公告、财联社快讯、公司确认/辟谣、政策/产业事件才会进入飞书校准；热榜、三榜、涨停全景、盘前纪要、财经早餐、公告全量只作为市场背景，不要求用户回复。",
        "",
        "## 作战室处理原则",
            "",
            "1. 命中 `防守/推倒重做复核`：先降仓位权限，再重看主计划。",
            "2. 命中 `作战室调入/调出复核`：只改变候选权重，不直接给买入权限。",
            "3. 命中 `候选票加权复核`：必须再看连板、Top100 排名、涨停原因 6 维度和竞价。",
            "4. 用户判断与模型判断冲突时，以用户判断为准，并写入权重校准。",
            "",
        ]
    )
    return "\n".join(lines)


def render_pending(generated_at: str, top: list[Catalyst]) -> str:
    lines = [
        "【重大消息雷达待判断】",
        f"时间：{generated_at}",
        "",
        "我筛出以下高优先级消息，需要你校准“消息本身的短线价值”，不是让你一次判断整包纪要里所有股票。",
        "请优先回复：有效 / 一般 / 无效 / 反向。",
        "如果你觉得我高估/低估，也请直接说：第几条 + 高估/低估 + 原因。",
        "",
        "我后续给你的判断，必须至少带这 4 个点：",
        "1. 判断对象：这次是在判断消息，不是在判断单票。",
        "2. 当前结论：有效 / 一般 / 无效 / 反向。",
        "3. 判断理由：最多 3 条，必须说人话，方便你直接纠偏。",
        "4. 后续验证：看竞价、涨停、一字、热榜跃迁、板块扩散中的哪几个。",
        "",
    ]
    for idx, item in enumerate(top[:5], 1):
        stocks = "、".join(f"{hit.name}{hit.code}" for hit in item.stock_hits) or "-"
        catalyst_type = "风险/防守消息" if "防守" in item.action or item.risk_score > item.bullish_score else "进攻/题材催化"
        purity = "高" if len(item.stock_hits) <= 2 and item.bullish_score >= 12 else "中" if len(item.stock_hits) <= 5 else "低"
        validation = []
        if item.stock_hits:
            validation.append("关联热榜/作战室票")
        if item.score >= 70:
            validation.append("分数过阈值")
        if item.risk_score:
            validation.append("含风险词，需要排雷")
        validation_text = "、".join(validation) or "仅关键词命中，验证不足"
        uncertainty = "我不确定的是：这条消息是能带动板块扩散，还是只是泛题材/整包信息；需要你纠偏消息纯度和短线价值。"
        lines.extend(
            [
                f"{idx}. {item.title}",
                "   判断对象：消息本身，不是单票买卖。",
                f"   我的当前结论：{item.action}；消息类型：{catalyst_type}；消息纯度：{purity}",
                f"   消息分：{item.score}；动作：{item.action}",
                f"   候选关联票：{stocks}",
                f"   我的判断逻辑：{item.reason}",
                f"   市场验证依据：{validation_text}",
                f"   风险/不确定点：{uncertainty}",
                "   你要纠偏：有效 / 一般 / 无效 / 反向；也可以说“高估/低估 + 原因”。",
                "",
            ]
        )
    lines.extend(
        [
            "你也可以直接这样回：",
            "1. 一般。理由：盘前纪要太泛，映射票太多，消息纯度不够。先看竞价和涨停验证。",
            "1. 有效，但高估了。理由：消息能看，分数不该打这么高，除非出现一字或板块扩散。",
        ]
    )
    return "\n".join(lines)


def write_pending_if_needed(top: list[Catalyst], threshold: int, dry_run: bool) -> dict[str, Any]:
    state = read_json(STATE_PATH, {"notified": []})
    notified = set(state.get("notified") or [])
    urgent = [
        item for item in top
        if (
            item.score >= threshold
            or item.action in {"防守/推倒重做复核", "作战室调入/调出复核"}
        )
        and is_actionable_message(ROOT / item.path, item.title)
    ]
    fresh = [item for item in urgent if item.fingerprint not in notified]
    if not fresh:
        return {"created": False, "urgent": len(urgent), "fresh": 0}
    generated_at = now_text()
    name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-重大消息雷达待判断.md"
    if not dry_run:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        (PENDING_DIR / name).write_text(render_pending(generated_at, fresh), encoding="utf-8")
        state["notified"] = list((list(notified) + [item.fingerprint for item in fresh])[-300:])
        write_json(STATE_PATH, state)
    return {"created": not dry_run, "file": str((PENDING_DIR / name).relative_to(ROOT)), "urgent": len(urgent), "fresh": len(fresh)}


def ensure_feedback_template(date: str) -> str:
    path = WIKI_STATS / f"{date}-消息权重人工校准表.md"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    f"# {date} 消息权重人工校准表",
                    "",
                    "用途：记录用户对重大消息雷达的判断，用来修正后续权重。",
                    "",
                    "| 时间 | 消息/股票 | 模型判断 | 用户判断 | 权重修正 | 后续验证 |",
                    "|---|---|---|---|---|---|",
                    "|  |  |  | 有效/一般/无效/反向 |  |  |",
                    "",
                    "规则：用户判断优先级高于模型判断；连续误判的关键词必须降权，连续命中的关键词必须升权。",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    return str(path.relative_to(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate real-time catalyst radar and war-room delta suggestions.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--lookback-hours", type=int, default=18)
    parser.add_argument("--limit-files", type=int, default=500)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--notify-threshold", type=int, default=70)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    hot_rows = latest_hotlist_rows()
    warroom = latest_warroom_stocks()
    ranked: list[Catalyst] = []
    for path in collect_raw_files(args.lookback_hours, args.limit_files):
        item = rank_file(path, hot_rows, warroom, args.lookback_hours)
        if item:
            ranked.append(item)
    deduped: dict[str, Catalyst] = {}
    for item in ranked:
        title_key = normalize_title(item.title)
        key = title_key if "通达信热榜top100" in title_key else re.sub(r"\s+", "", f"{item.source}|{item.title}").lower()
        if key not in deduped or item.score > deduped[key].score:
            deduped[key] = item
    ranked = list(deduped.values())
    ranked.sort(key=lambda item: (item.score, item.risk_score, item.bullish_score), reverse=True)
    top = ranked[: args.top]
    generated_at = now_text()
    payload = {
        "schema": "73wiki-realtime-catalyst-radar-v1",
        "generatedAt": generated_at,
        "date": args.date,
        "lookbackHours": args.lookback_hours,
        "scannedFiles": len(collect_raw_files(args.lookback_hours, args.limit_files)),
        "ranked": len(ranked),
        "top": [catalyst_to_dict(item) for item in top],
        "thresholds": {
            "notify": args.notify_threshold,
        },
    }
    if not args.dry_run:
        write_json(OUT_DIR / "latest-catalyst-radar.json", payload)
        write_json(OUT_DIR / f"{args.date}-catalyst-radar.json", payload)
        md = render_md(args.date, generated_at, top)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "latest-catalyst-radar.md").write_text(md, encoding="utf-8")
        WIKI_ROOM.mkdir(parents=True, exist_ok=True)
        (WIKI_ROOM / f"{args.date}-盘中重大消息雷达Top10.md").write_text(md, encoding="utf-8")
    notify_result = write_pending_if_needed(top, args.notify_threshold, args.dry_run)
    feedback_path = ensure_feedback_template(args.date) if not args.dry_run else ""
    result = {
        "ok": True,
        "date": args.date,
        "scannedFiles": payload["scannedFiles"],
        "ranked": len(ranked),
        "topCount": len(top),
        "topScore": top[0].score if top else 0,
        "topAction": top[0].action if top else "",
        "notify": notify_result,
        "outputs": {
            "json": str((OUT_DIR / "latest-catalyst-radar.json").relative_to(ROOT)),
            "md": str((OUT_DIR / "latest-catalyst-radar.md").relative_to(ROOT)),
            "wiki": str((WIKI_ROOM / f"{args.date}-盘中重大消息雷达Top10.md").relative_to(ROOT)),
            "feedback": feedback_path,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
