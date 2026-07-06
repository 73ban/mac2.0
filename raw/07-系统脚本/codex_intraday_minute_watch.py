#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-minute intraday watcher for holdings, warroom, hotlists and risks.

This watcher does not call paid tdx_quotes/tdx_kline. It only reads local RAW,
warroom outputs and already-synced market snapshots, then writes an auditable
minute-level decision record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
SYSTEM = ROOT / ".system"
OUT_ROOT = RAW / "11-Codex分析产物" / "盘中一分钟看盘"
WIKI_ROOM = ROOT / "wiki" / "07-作战室"
WIKI_STATS = ROOT / "wiki" / "09-统计与进化"
PENDING = SYSTEM / "feishu-notify-pending"
STATE = SYSTEM / "intraday-minute-watch-state.json"
FACTS = ROOT / "data" / "facts" / "intraday_minute_watch_alerts.jsonl"


RISK_WORDS = ("澄清", "问询", "监管", "减持", "亏损", "退潮", "补跌", "跌停", "负反馈", "炸板", "天地板", "核按钮")
STRONG_WORDS = ("涨停", "连板", "一字", "回封", "弱转强", "主线", "涨价", "订单", "量产", "并购", "重组", "英伟达", "算力", "机器人", "存储", "半导体")
OFFICIAL_RISK_SOURCE_WORDS = ("公告", "互动问答", "互动易", "公司回复", "官方确认", "官方辟谣", "问询函", "监管函", "减持公告", "澄清公告")
HARD_RISK_WORDS = ("澄清", "问询", "监管", "减持", "亏损", "跌停", "炸板", "天地板", "核按钮")
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|8\d{5})(?!\d)")


@dataclass
class Alert:
    level: str
    category: str
    subject: str
    conclusion: str
    reasons: list[str]
    suggestion: str
    invalidation: str
    verification: list[str]
    signature: str


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


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def clean(value: Any, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().replace("|", "/")[:limit]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def latest_file(root: Path, suffixes: set[str] | None = None) -> Path | None:
    if not root.exists():
        return None
    best: Path | None = None
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        if best is None or path.stat().st_mtime > best.stat().st_mtime:
            best = path
    return best


def code_name(row: dict[str, Any]) -> str:
    return f"{row.get('name') or row.get('code')}{row.get('code') or ''}"


def signature(parts: list[str]) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def stock_text(row: dict[str, Any]) -> str:
    fields = [
        row.get("entryReason"),
        ";".join(row.get("reasons") or []),
        ";".join(row.get("riskHits") or []),
        ";".join(row.get("strongHits") or []),
        json.dumps(row.get("plan") or {}, ensure_ascii=False),
        json.dumps(row.get("companyImpactSummary") or {}, ensure_ascii=False),
    ]
    return " ".join(str(x or "") for x in fields)


def holding_risk_evidence(row: dict[str, Any]) -> dict[str, Any]:
    """Separate real risk evidence from generic risk-control templates."""
    source_fields = [
        ";".join(row.get("reasons") or []),
        ";".join(row.get("evidence") or []),
        json.dumps(row.get("companyImpacts") or [], ensure_ascii=False),
    ]
    source_text = " ".join(source_fields)
    official = any(word in source_text for word in OFFICIAL_RISK_SOURCE_WORDS)
    risks = [word for word in RISK_WORDS if word in source_text]
    hard = [word for word in risks if word in HARD_RISK_WORDS]
    weak_only = bool(risks) and not official and any(word in source_text for word in ("证据弱", "观点", "传闻", "情绪样本", "市场热度验证"))
    return {
        "risks": risks,
        "hard": hard,
        "official": official,
        "weakOnly": weak_only,
        "sourceText": source_text,
    }


def load_warroom(date: str) -> dict[str, Any]:
    return read_json(RAW / "11-Codex分析产物" / "动态作战室" / date / "dynamic-warroom-top5.json", {})


def load_important(date: str) -> dict[str, Any]:
    return read_json(RAW / "11-Codex分析产物" / "每日重要信息Top10" / date / "daily-important-info-top10.json", {})


def load_catalyst() -> dict[str, Any]:
    return read_json(ROOT / ".llm-wiki" / "catalyst-radar" / "latest-catalyst-radar.json", {})


def hotlist_status(date: str) -> list[dict[str, str]]:
    roots = [
        RAW / "04-市场数据" / "同花顺热榜" / date,
        RAW / "04-市场数据" / "热榜" / date,
        RAW / "04-市场数据" / "三榜热度合并" / date,
        RAW / "04-市场数据" / "通达信热榜TOP100" / date,
        RAW / "04-市场数据" / "通达信成交额排名" / date,
        RAW / "04-市场数据" / "午后异动" / date,
        RAW / "04-市场数据" / "早盘主线板块分析" / date,
        RAW / "04-市场数据" / "午前扫描" / date,
    ]
    rows: list[dict[str, str]] = []
    for root in roots:
        latest = latest_file(root, {".md", ".json"})
        rows.append(
            {
                "name": root.parent.name,
                "path": rel(latest) if latest else rel(root),
                "status": "ok" if latest else "missing",
                "mtime": datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if latest else "",
            }
        )
    return rows


def build_holding_alerts(warroom: dict[str, Any]) -> list[Alert]:
    alerts: list[Alert] = []
    for row in warroom.get("holdingsAnalysis") or []:
        evidence = holding_risk_evidence(row)
        risks = evidence["risks"]
        strong = [word for word in STRONG_WORDS if word in stock_text(row)]
        if risks and evidence["official"] and evidence["hard"]:
            level = "S" if any(word in evidence["hard"] for word in ("澄清", "监管", "问询", "跌停", "炸板")) else "A"
            alerts.append(
                Alert(
                    level=level,
                    category="持仓风险",
                    subject=code_name(row),
                    conclusion="持仓票需要优先防守复核",
                    reasons=[
                        f"真实风险证据：{', '.join(risks[:6])}",
                        f"证据来源：{'官方/公司/公告类' if evidence['official'] else '非官方但命中硬风险词'}",
                        clean((row.get("companyImpactSummary") or {}).get("risks"), 120),
                    ],
                    suggestion="盘中先看竞价/开盘承接、板块核心反馈和热榜是否退潮；不满足承接时优先降仓或不加仓。",
                    invalidation="风险词被官方确认解除，且板块核心回封、热榜不退、持仓票强于同题材核心。",
                    verification=["开盘承接", "分时均线", "板块核心炸板/回封", "热榜排名变化", "D+1溢价"],
                    signature=signature(["holding-risk", str(row.get("code")), ",".join(risks)]),
                )
            )
        elif risks and evidence["weakOnly"]:
            alerts.append(
                Alert(
                    level="B",
                    category="持仓弱风险",
                    subject=code_name(row),
                    conclusion="持仓票有弱风险词，但证据不足，不推送打扰",
                    reasons=[
                        f"弱风险词：{', '.join(risks[:6])}",
                        "来源偏观点/传闻/市场热度，不能当作真实利空。",
                        clean((row.get("companyImpactSummary") or {}).get("risks"), 120),
                    ],
                    suggestion="只写入盘中记录；等官方确认、热榜退潮、板块核心负反馈或盘口走弱后再升级。",
                    invalidation="官方证据缺失且盘口/板块继续强，弱风险降权。",
                    verification=["官方确认/辟谣", "热榜退潮", "板块核心反馈", "D+1溢价"],
                    signature=signature(["holding-weak-risk", str(row.get("code")), ",".join(risks)]),
                )
            )
        elif strong and row.get("isHolding"):
            alerts.append(
                Alert(
                    level="B",
                    category="持仓机会",
                    subject=code_name(row),
                    conclusion="持仓票有强势延续线索，但暂不直接提醒加仓",
                    reasons=[f"命中强势词：{', '.join(strong[:6])}", clean(row.get("entryReason"), 120)],
                    suggestion="只写入盘中记录；必须等开盘承接、板块扩散和同题材核心确认后才允许提高处理优先级。",
                    invalidation="热榜下滑、板块无扩散、冲高不能封板或核心票负反馈。",
                    verification=["热榜前排延续", "板块扩散", "涨停质量", "D+1溢价"],
                    signature=signature(["holding-opportunity", str(row.get("code")), ",".join(strong)]),
                )
            )
    return alerts


def build_top20_delta_alerts(warroom: dict[str, Any], prev_state: dict[str, Any]) -> list[Alert]:
    rows = [row for row in (warroom.get("allCandidates") or [])[:20] if isinstance(row, dict)]
    current = [str(row.get("code") or "") for row in rows if row.get("code")]
    previous = [str(x) for x in (prev_state.get("lastTop20") or [])]
    if not current or not previous:
        return []
    added = [code for code in current if code not in previous]
    removed = [code for code in previous if code not in current]
    if not added and not removed:
        return []
    by_code = {str(row.get("code")): row for row in rows}
    reasons: list[str] = []
    for code in added[:5]:
        row = by_code.get(code) or {}
        reasons.append(f"调入Top20：{code_name(row)}，{clean(row.get('entryReason'), 90)}")
    for code in removed[:5]:
        reasons.append(f"调出Top20：{code}")
    return [
        Alert(
            level="B",
            category="作战室Top20变化",
            subject="动态作战室Top20",
            conclusion="Top20池发生变化，先记录不打扰",
            reasons=reasons,
            suggestion="只写入RAW；如果调入票连续上升并叠加热榜/成交额/涨停质量，再升级为A。",
            invalidation="下一轮跌出Top20或缺少新增证据。",
            verification=["下一轮Top20持续性", "热榜跃迁", "成交额排名", "D+0强弱"],
            signature=signature(["warroom-top20", ",".join(added), ",".join(removed)]),
        )
    ]


def build_warroom_change_alerts(warroom: dict[str, Any]) -> list[Alert]:
    change = warroom.get("change") or {}
    alerts: list[Alert] = []
    added = change.get("addedDetail") or []
    removed = change.get("removedDetail") or []
    ranks = change.get("rankChanges") or []
    if added or removed:
        parts = []
        for item in added[:5]:
            parts.append(f"调入 {item.get('name') or item.get('code')}：{clean(item.get('reason'), 80)}")
        for item in removed[:5]:
            parts.append(f"调出 {item.get('name') or item.get('code')}：{clean(item.get('reason'), 80)}")
        alerts.append(
            Alert(
                level="A",
                category="作战室Top5变化",
                subject="动态作战室Top5",
                conclusion="Top5发生调入/调出，需要写明原因并进入事后验证",
                reasons=parts,
                suggestion="新调入只提高观察权重，仍需竞价、板块强度、涨停原因和热榜跃迁确认；调出要记录被谁替代、为什么替代。",
                invalidation="后续一分钟扫描显示调入票热度回落或板块不扩散，自动降回观察。",
                verification=["Top5排名持续性", "热榜跃迁", "板块扩散", "D+0收盘强弱", "D+1溢价"],
                signature=signature(["warroom-change"] + [str(x.get("code")) for x in added + removed]),
            )
        )
    elif ranks:
        alerts.append(
            Alert(
                level="B",
                category="作战室排名变化",
                subject="动态作战室Top5",
                conclusion="Top5内部排名变化，先记录不打扰",
                reasons=[clean(item.get("reason"), 100) for item in ranks[:5]],
                suggestion="只写入RAW，若连续两次上升且叠加新催化，再升级提醒。",
                invalidation="排名回落或缺少新证据。",
                verification=["下一轮排名", "新增证据", "D+0强弱"],
                signature=signature(["warroom-rank"] + [str(x.get("code")) + str(x.get("newRank")) for x in ranks]),
            )
        )
    return alerts


def build_important_alerts(date: str, important: dict[str, Any], catalyst: dict[str, Any]) -> list[Alert]:
    alerts: list[Alert] = []
    rows = important.get("top10") or important.get("items") or important.get("rows") or []
    if isinstance(rows, list):
        for item in rows[:3]:
            score = int(float(item.get("score") or item.get("分数") or 0))
            text = json.dumps(item, ensure_ascii=False)
            if score < 95:
                continue
            if "风险" in text or any(word in text for word in ("澄清", "监管", "问询", "退潮", "黑天鹅")):
                level = "A"
                conclusion = "高分信息偏风险，需要压低进攻权限"
            else:
                level = "B"
                conclusion = "高分信息进入观察，但不直接打扰"
            title = clean(item.get("title") or item.get("信息") or item.get("message") or item.get("name"), 80)
            alerts.append(
                Alert(
                    level=level,
                    category="重要信息Top10",
                    subject=title or f"{date} 高分信息",
                    conclusion=conclusion,
                    reasons=[
                        f"信息分数 {score}",
                        clean(item.get("company_impact_type") or item.get("公司影响") or item.get("type") or item.get("类型"), 80),
                        clean(item.get("shortline_view") or item.get("短线判断") or item.get("reason") or item.get("理由"), 120),
                    ],
                    suggestion="和持仓、作战室Top20、三榜热度、板块扩散交叉；没有市场确认只入库不交易。",
                    invalidation="未出现在热榜/成交额/涨停反馈，或同题材核心负反馈。",
                    verification=["竞价", "涨停质量", "热榜跃迁", "板块扩散", "D+1/D+3"],
                    signature=signature(["important", title, str(score)]),
                )
            )
    cat_rows = catalyst.get("top10") or catalyst.get("items") or []
    if isinstance(cat_rows, list):
        for item in cat_rows[:2]:
            action = clean(item.get("action") or item.get("动作"), 80)
            score = int(float(item.get("score") or item.get("分数") or 0))
            if score >= 90 and ("防守" in action or "风险" in action):
                title = clean(item.get("title") or item.get("消息"), 80)
                alerts.append(
                    Alert(
                        level="S",
                        category="重大消息雷达",
                        subject=title,
                        conclusion="重大风险消息命中，先防守再重判作战室",
                        reasons=[f"雷达分数 {score}", action, clean(item.get("reason") or item.get("理由"), 160)],
                        suggestion="暂停新开仓升级，先复核持仓、核心票和板块负反馈。",
                        invalidation="市场竞价无负反馈，核心票强回封，热榜未退潮。",
                        verification=["竞价", "跌停/补跌", "核心承接", "热榜退潮", "板块扩散"],
                        signature=signature(["catalyst-risk", title, str(score)]),
                    )
                )
    return alerts


def dedupe_for_notify(alerts: list[Alert], force: bool, state: dict[str, Any] | None = None) -> tuple[list[Alert], dict[str, Any]]:
    state = state or read_json(STATE, {})
    sent = set(state.get("sent") or [])
    pushable = [a for a in alerts if a.level in {"S", "A"}]
    fresh = [a for a in pushable if force or a.signature not in sent]
    if fresh:
        state["sent"] = list((list(sent) + [a.signature for a in fresh])[-500:])
        state["updatedAt"] = now_text()
        write_json(STATE, state)
    return fresh, state


def write_notify(date: str, alert: Alert) -> Path:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    path = PENDING / f"{ts}-{alert.signature}-盘中一分钟看盘-{alert.category}.md"
    lines = [
        f"【盘中一分钟看盘提醒：{alert.level}】",
        f"时间：{now_text()}",
        "",
        "判断对象：这是盘中机会/风险提醒，不是自动交易指令。",
        f"类别：{alert.category}",
        f"对象：{alert.subject}",
        f"当前结论：{alert.conclusion}",
        "",
        "我的判断逻辑：",
    ]
    lines.extend(f"- {reason}" for reason in alert.reasons if reason)
    lines.extend(
        [
            "",
            f"处理建议：{alert.suggestion}",
            f"失效条件：{alert.invalidation}",
            f"后续验证：{'、'.join(alert.verification)}",
            "",
            "你要校准：我是否高估/低估这条提醒，以及处理建议是否符合你的模式。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def render_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload['date']} 盘中一分钟看盘",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        "- 频率口径：盘中统一每 1 分钟检查一次持仓票、作战室Top20、热榜、成交额、异动和消息催化。",
        "- 数据边界：不调用付费 tdx_quotes / tdx_kline，只读取本机 RAW 和已同步快照。",
        "",
        "## 本轮结论",
        "",
        f"- S级提醒：{payload['summary']['S']}",
        f"- A级提醒：{payload['summary']['A']}",
        f"- B级记录：{payload['summary']['B']}",
        f"- 飞书待发：{payload['summary']['notifyCreated']}",
        "",
        "## 提醒/记录",
        "",
    ]
    if not payload["alerts"]:
        lines.append("- 本轮没有触发提醒，只记录数据新鲜度。")
    for item in payload["alerts"]:
        lines.extend(
            [
                f"### [{item['level']}] {item['category']}：{item['subject']}",
                "",
                f"- 当前结论：{item['conclusion']}",
                f"- 判断逻辑：{'；'.join(x for x in item['reasons'] if x)}",
                f"- 处理建议：{item['suggestion']}",
                f"- 失效条件：{item['invalidation']}",
                f"- 后续验证：{'、'.join(item['verification'])}",
                "",
            ]
        )
    lines.extend(["## 数据新鲜度", "", "| 数据 | 状态 | 最新时间 | 路径 |", "|---|---|---|---|"])
    for row in payload["sources"]:
        lines.append(f"| {row['name']} | {row['status']} | {row.get('mtime') or '-'} | `{row['path']}` |")
    return "\n".join(lines) + "\n"


def alert_to_dict(alert: Alert) -> dict[str, Any]:
    return {
        "level": alert.level,
        "category": alert.category,
        "subject": alert.subject,
        "conclusion": alert.conclusion,
        "reasons": alert.reasons,
        "suggestion": alert.suggestion,
        "invalidation": alert.invalidation,
        "verification": alert.verification,
        "signature": alert.signature,
    }


def build(date: str, force_notify: bool = False) -> dict[str, Any]:
    state = read_json(STATE, {})
    warroom = load_warroom(date)
    important = load_important(date)
    catalyst = load_catalyst()
    alerts: list[Alert] = []
    alerts.extend(build_holding_alerts(warroom))
    alerts.extend(build_warroom_change_alerts(warroom))
    alerts.extend(build_top20_delta_alerts(warroom, state))
    alerts.extend(build_important_alerts(date, important, catalyst))
    fresh_notify, state = dedupe_for_notify(alerts, force_notify, state)
    top20 = [str(row.get("code") or "") for row in (warroom.get("allCandidates") or [])[:20] if isinstance(row, dict) and row.get("code")]
    if top20:
        state["lastTop20"] = top20
        state["lastTop20UpdatedAt"] = now_text()
        write_json(STATE, state)
    notify_paths = [rel(write_notify(date, alert)) for alert in fresh_notify]
    for alert in alerts:
        append_jsonl(
            FACTS,
            {
                "date": date,
                "generatedAt": now_text(),
                **alert_to_dict(alert),
                "notifyEligible": alert.level in {"S", "A"},
                "verificationStatus": "pending",
            },
        )
    payload = {
        "schema": "73wiki-intraday-minute-watch-v1",
        "date": date,
        "generatedAt": now_text(),
        "frequencySeconds": 60,
        "dataBoundary": "no paid tdx_quotes/tdx_kline",
        "alerts": [alert_to_dict(alert) for alert in alerts],
        "notifyPaths": notify_paths,
        "sources": hotlist_status(date),
        "summary": {
            "S": sum(1 for a in alerts if a.level == "S"),
            "A": sum(1 for a in alerts if a.level == "A"),
            "B": sum(1 for a in alerts if a.level == "B"),
            "notifyCreated": len(notify_paths),
        },
    }
    return payload


def write_outputs(payload: dict[str, Any], apply_wiki: bool) -> None:
    out = OUT_ROOT / payload["date"]
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "intraday-minute-watch.json", payload)
    md = render_md(payload)
    (out / "intraday-minute-watch.md").write_text(md, encoding="utf-8")
    if apply_wiki:
        (WIKI_STATS / f"{payload['date']}-盘中一分钟看盘.md").write_text(md, encoding="utf-8")
        (WIKI_ROOM / "当前盘中一分钟看盘.md").write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="盘中一分钟自动看盘")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--apply-wiki", action="store_true")
    parser.add_argument("--force-notify", action="store_true")
    args = parser.parse_args()
    payload = build(args.date, args.force_notify)
    if args.write:
        write_outputs(payload, args.apply_wiki)
    print(json.dumps({"ok": True, "date": args.date, "summary": payload["summary"], "notifyPaths": payload["notifyPaths"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
