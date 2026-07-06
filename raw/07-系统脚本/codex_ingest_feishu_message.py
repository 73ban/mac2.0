#!/usr/bin/env python3
"""Ingest one Feishu message into RAW with a conservative review protocol.

This script is intentionally rule-based. It preserves the user's original words
first, then writes only low-risk structured hints and ambiguity flags.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RAW_REVIEW = ROOT / "raw/02-每日复盘"
RAW_CHAT = ROOT / "raw/10-飞书交易沟通"
SYSTEM_DIR = ROOT / ".system"
PENDING_DIR = SYSTEM_DIR / "feishu-notify-pending"
STATE_PATH = SYSTEM_DIR / "feishu-oral-review-state.json"
EVENTS_PATH = SYSTEM_DIR / "feishu-oral-review-events.jsonl"
CALIBRATION_EVENTS = ROOT / "data/facts/feishu_calibration_events.jsonl"
CALIBRATION_QUEUE = ROOT / "wiki/09-统计与进化/消息权重人工校准待验证队列.md"
MEMORY_LOG = ROOT / "wiki/10-系统配置/记忆进化日志.md"
ITEM_REPLY_RE = re.compile(
    r"(?:第\s*)?(\d{1,2})\s*(?:条|[\.、:：])?\s*"
    r"(有效|一般|无效|反向|高估|低估)"
    r"(?:[，,。:：\s]*(.*?))?"
    r"(?=(?:\n\s*(?:第\s*)?\d{1,2}\s*(?:条|[\.、:：])?\s*(?:有效|一般|无效|反向|高估|低估))|\Z)",
    re.S,
)


def now() -> datetime:
    return datetime.now()


def now_text() -> str:
    return now().strftime("%Y-%m-%d %H:%M:%S")


def now_stamp() -> str:
    return now().strftime("%Y%m%d%H%M%S")


def today() -> str:
    return now().strftime("%Y-%m-%d")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def append_jsonl(path: Path, item: dict) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"active": False, "trade_date": ""}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"active": False, "trade_date": ""}


def save_state(state: dict) -> None:
    SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_item_calibration_replies(text: str) -> list[dict]:
    replies = []
    for match in ITEM_REPLY_RE.finditer(text.strip()):
        raw_reason = re.sub(r"\s+", " ", match.group(3) or "").strip()
        raw_reason = re.sub(r"^(因为|原因是|原因|理由是|理由)\s*[:：，,]?\s*", "", raw_reason)
        verdict = match.group(2)
        if verdict == "有效":
            action = "up"
            weight_change = 1
            needs_validation = True
        elif verdict == "一般":
            action = "hold"
            weight_change = 0
            needs_validation = False
        elif verdict == "无效":
            action = "down"
            weight_change = -1
            needs_validation = False
        elif verdict == "反向":
            action = "reverse"
            weight_change = -2
            needs_validation = True
        elif verdict == "高估":
            action = "down"
            weight_change = -1
            needs_validation = True
        else:
            action = "up"
            weight_change = 1
            needs_validation = True
        replies.append(
            {
                "item_index": int(match.group(1)),
                "user_judgement": verdict,
                "reason": raw_reason,
                "action": action,
                "weight_change": weight_change,
                "needs_validation": needs_validation,
            }
        )
    return replies


def latest_prompt_file() -> str:
    candidates = []
    for directory in (PENDING_DIR, SYSTEM_DIR / "feishu-notify-sent"):
        if directory.exists():
            candidates.extend(directory.glob("*.md"))
    if not candidates:
        return ""
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return rel(candidates[0])


def normalize_date(value: str | None, text: str) -> str:
    if value:
        value = value.strip()
        if re.fullmatch(r"\d{8}", value):
            return f"{value[:4]}-{value[4:6]}-{value[6:]}"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value
    match = re.search(r"(20\d{2})[-/.年]?(\d{1,2})[-/.月]?(\d{1,2})日?", text)
    if match:
        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    match = re.search(r"\b(20\d{6})\b", text)
    if match:
        compact = match.group(1)
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
    return today()


def command_from_text(text: str) -> str:
    cleaned = text.strip()
    if re.search(r"(开始|进入).{0,4}复盘", cleaned):
        return "start_review"
    if re.search(r"(完成|结束).{0,4}复盘|今天复盘就这么多|复盘就这么多|写入\s*wiki|写入WIKI", cleaned, re.I):
        return "finish_review"
    return ""


def classify(text: str, explicit_type: str, state: dict) -> str:
    if explicit_type != "auto":
        return explicit_type
    if state.get("active"):
        return "review"
    cmd = command_from_text(text)
    if cmd in {"start_review", "finish_review"}:
        return "review"
    if re.search(r"买入|卖出|割肉|止损|止盈|仓位|持仓|交割单|委托|撤单|打板|半路|复盘|亏损|盈利|回撤", text):
        return "review"
    if parse_item_calibration_replies(text):
        return "calibration"
    if re.search(r"降权|升权|写成规则|以后遇到|明天验证|这条没用|这条有效|只给我结论|展开第二点", text):
        return "calibration"
    if re.search(r"重不重要|算什么|能不能刺激涨停|是不是重大消息|消息", text):
        return "message_judgement"
    return "chat"


def extract_hints(text: str) -> dict:
    stock_codes = sorted(set(re.findall(r"(?<!\d)(?:[036]\d{5}|8\d{5})(?!\d)", text)))
    actions = []
    for key in ("买入", "卖出", "撤单", "未成交", "持仓", "止损", "止盈", "打板", "半路", "低吸", "加仓", "减仓", "清仓"):
        if key in text:
            actions.append(key)
    topics = []
    for key in ("机器人", "半导体", "芯片", "CPO", "贵金属", "稀土", "电力", "创新药", "消费", "军工", "光刻胶", "六氟化钨", "退潮", "修复", "冰点"):
        if key.lower() in text.lower():
            topics.append(key)
    amounts = re.findall(r"[-+]?\d+(?:\.\d+)?\s*(?:万|元|块|亿)", text)
    sentiment_score = ""
    match = re.search(r"情绪(?:分|打分)?\s*([0-9](?:\.\d+)?)\s*分?", text)
    if match:
        sentiment_score = match.group(1)
    ambiguities = []
    if re.search(r"这个|那个|它|他|她|这条|那条|刚才", text) and not stock_codes and len(text) < 120:
        ambiguities.append("存在指代词，但未明确股票、消息或截图对象。")
    if any(word in text for word in ("买", "卖", "加仓", "减仓", "清仓")) and not stock_codes:
        ambiguities.append("出现买卖动作，但未识别到明确股票代码。")
    if any(word in text for word in ("可能", "感觉", "好像", "应该", "估计")):
        ambiguities.append("包含主观不确定词，正式复盘只能作为用户当时感受，不能当事实结论。")
    if "为什么" in text and not any(word in text for word in ("因为", "理由", "原因")):
        ambiguities.append("用户在提问原因，不能直接当作买卖理由。")
    return {
        "股票代码": stock_codes,
        "动作词": actions,
        "题材词": topics,
        "金额词": amounts,
        "情绪分": sentiment_score,
        "歧义点": ambiguities,
    }


def review_md_path(trade_date: str) -> Path:
    return RAW_REVIEW / f"{trade_date}-飞书复盘RAW.md"


def review_jsonl_path(trade_date: str) -> Path:
    return RAW_REVIEW / f"{trade_date}-飞书复盘RAW.jsonl"


def append_review_raw(trade_date: str, text: str, sender: str, source: str, hints: dict, command: str) -> Path:
    path = review_md_path(trade_date)
    if not path.exists():
        write_text(
            path,
            "\n".join(
                [
                    f"# {trade_date} 飞书复盘RAW",
                    "",
                    "## 基本信息",
                    "",
                    "```yaml",
                    f"trade_date: {trade_date}",
                    "source_type: feishu_oral_review",
                    "status: RAW 原文，未写正式 WIKI",
                    "rule: 原话先入库；Codex 理解字段只作提示，有歧义先待确认",
                    "```",
                    "",
                    "## 飞书原文时间线",
                    "",
                ]
            ),
        )
    block = [
        f"### {now_text()} {sender}",
        "",
        f"- source: {source}",
        f"- command: {command or 'none'}",
        f"- content_sha256: {sha256_text(text)}",
        "",
        "#### 原话",
        "",
        "```text",
        text.rstrip(),
        "```",
        "",
        "#### 低风险识别",
        "",
        f"- 股票代码：{', '.join(hints['股票代码']) if hints['股票代码'] else '未识别'}",
        f"- 动作词：{', '.join(hints['动作词']) if hints['动作词'] else '未识别'}",
        f"- 题材词：{', '.join(hints['题材词']) if hints['题材词'] else '未识别'}",
        f"- 金额词：{', '.join(hints['金额词']) if hints['金额词'] else '未识别'}",
        f"- 情绪分：{hints['情绪分'] or '未识别'}",
        "",
        "#### 歧义点",
        "",
    ]
    if hints["歧义点"]:
        block.extend([f"- {item}" for item in hints["歧义点"]])
    else:
        block.append("- 暂无明显歧义。")
    block.append("")
    append_text(path, "\n".join(block))
    return path


def write_chat_raw(text: str, sender: str, source: str, message_type: str, hints: dict) -> Path:
    day = now()
    path = RAW_CHAT / day.strftime("%Y/%m/%d") / f"{now_stamp()}-{message_type}.md"
    body = "\n".join(
        [
            f"# 飞书交易沟通-{now_text()}",
            "",
            "```yaml",
            f"message_type: {message_type}",
            f"sender: {sender}",
            f"source: {source}",
            f"content_sha256: {sha256_text(text)}",
            "status: RAW 原文，未提炼为稳定规则",
            "```",
            "",
            "## 原文",
            "",
            "```text",
            text.rstrip(),
            "```",
            "",
            "## 低风险识别",
            "",
            f"- 股票代码：{', '.join(hints['股票代码']) if hints['股票代码'] else '未识别'}",
            f"- 动作词：{', '.join(hints['动作词']) if hints['动作词'] else '未识别'}",
            f"- 题材词：{', '.join(hints['题材词']) if hints['题材词'] else '未识别'}",
            f"- 歧义点：{'; '.join(hints['歧义点']) if hints['歧义点'] else '暂无明显歧义'}",
            "",
        ]
    )
    write_text(path, body)
    return path


def maybe_write_calibration(text: str, message_type: str, trade_date: str, hints: dict, chat_path: Path) -> None:
    if message_type not in {"calibration", "message_judgement"}:
        return
    item_replies = parse_item_calibration_replies(text)
    if item_replies:
        prompt_file = latest_prompt_file()
        table = ROOT / "wiki/09-统计与进化" / f"{trade_date}-飞书条目校准表.md"
        if not table.exists():
            write_text(
                table,
                "\n".join(
                    [
                        f"# {trade_date} 飞书条目校准表",
                        "",
                        "| 时间 | 条目 | 判断 | 权重 | 原因 | 后续动作 | 来源提示 |",
                        "|---|---:|---|---:|---|---|---|",
                    ]
                )
                + "\n",
            )
        for reply in item_replies:
            event = {
                "schema": "feishu_item_calibration_reply_v1",
                "created_at": now_text(),
                "trade_date": trade_date,
                "source_path": rel(chat_path),
                "source_prompt": prompt_file,
                "item_index": reply["item_index"],
                "target": f"Feishu prompt item #{reply['item_index']}",
                "message_text": text,
                "user_judgement": reply["user_judgement"],
                "reason": reply["reason"],
                "action": reply["action"],
                "weight_change": reply["weight_change"],
                "needs_validation": reply["needs_validation"],
                "status": "pending_validation" if reply["needs_validation"] else "recorded",
                "validation_task": "按条目类型回看D+1/D+3/D+5、热榜跃迁、涨停质量、板块扩散和后续复盘命中率。",
            }
            append_jsonl(CALIBRATION_EVENTS, event)
            append_text(
                table,
                f"| {event['created_at']} | {reply['item_index']} | {reply['user_judgement']} | {reply['weight_change']:+d} | {(reply['reason'] or '-').replace('|', '/')} | {event['validation_task']} | `{prompt_file or '-'}` |\n",
            )
            if reply["needs_validation"]:
                if not CALIBRATION_QUEUE.exists():
                    write_text(
                        CALIBRATION_QUEUE,
                        "# 消息权重人工校准待验证队列\n\n| 入队日 | 原话 | 权重变化 | 验证任务 | 状态 |\n|---|---|---:|---|---|\n",
                    )
                append_text(
                    CALIBRATION_QUEUE,
                    f"| {trade_date} | 条目{reply['item_index']}：{reply['user_judgement']}，{(reply['reason'] or '-').replace('|', '/')} | {reply['weight_change']:+d} | {event['validation_task']} | active |\n",
                )
        append_text(
            MEMORY_LOG,
            f"\n## {now_text()} 飞书条目校准已结构化\n\n- 用户回复：{text}\n- 解析条数：{len(item_replies)}\n- 来源提示：`{prompt_file or '-'}`\n- 状态：按条目进入校准事件，后续由 D+验证和权重脚本吸收。\n",
        )
        return
    weight_change = 0
    rule_fix = "待Codex根据上下文归因"
    if re.search(r"降权|没用|无效|不重要", text):
        weight_change = -1
        rule_fix = "类似消息先降权，除非出现涨停、热榜跃迁、板块扩散或连板晋级验证。"
    elif re.search(r"升权|有效|重要", text):
        weight_change = 1
        rule_fix = "类似消息先升权观察，但必须用资金反馈验证，不能只凭文本利好。"
    elif re.search(r"情绪票", text):
        rule_fix = "归类为情绪信号，不能按基本面长期逻辑加权。"
    elif re.search(r"反向", text):
        weight_change = -2
        rule_fix = "归类为反向/风险信号，次日优先观察负反馈。"
    event = {
        "schema": "feishu_calibration_event_v1",
        "created_at": now_text(),
        "trade_date": trade_date,
        "message_type": message_type,
        "source_path": rel(chat_path),
        "user_text": text,
        "股票代码": hints["股票代码"],
        "题材词": hints["题材词"],
        "rule_fix": rule_fix,
        "weight_change": weight_change,
        "validation_task": "看次日涨停、热榜跃迁、板块扩散、连板晋级、竞价强度是否验证用户校准。",
        "status": "待Codex判断或待市场验证",
    }
    append_jsonl(CALIBRATION_EVENTS, event)
    table = ROOT / "wiki/09-统计与进化" / f"{trade_date}-消息权重人工校准表.md"
    if not table.exists():
        write_text(
            table,
            "\n".join(
                [
                    f"# {trade_date} 消息权重人工校准表",
                    "",
                    "| 时间 | 原话 | 股票 | 题材 | 权重变化 | 规则修正 | 后续验证 | 来源 |",
                    "|---|---|---|---|---:|---|---|---|",
                ]
            )
            + "\n",
        )
    append_text(
        table,
        f"| {event['created_at']} | {text.replace('|', '/')} | {', '.join(hints['股票代码']) or '-'} | {', '.join(hints['题材词']) or '-'} | {weight_change:+d} | {rule_fix} | {event['validation_task']} | `{rel(chat_path)}` |\n",
    )
    if "验证" in text or weight_change != 0 or message_type == "message_judgement":
        if not CALIBRATION_QUEUE.exists():
            write_text(
                CALIBRATION_QUEUE,
                "# 消息权重人工校准待验证队列\n\n| 入队日 | 原话 | 权重变化 | 验证任务 | 状态 |\n|---|---|---:|---|---|\n",
            )
        append_text(CALIBRATION_QUEUE, f"| {trade_date} | {text.replace('|', '/')} | {weight_change:+d} | {event['validation_task']} | active |\n")
    if "写成规则" in text or "以后遇到" in text or weight_change != 0:
        append_text(
            MEMORY_LOG,
            f"\n## {now_text()} 飞书校准待验证\n\n- 原话：{text}\n- 规则修正：{rule_fix}\n- 权重变化：{weight_change:+d}\n- 状态：待市场验证，不直接升级稳定记忆。\n",
        )


def render_ack(message_type: str, trade_date: str, raw_path: Path, hints: dict, command: str) -> str:
    title = "已按原话写入 RAW。"
    if command == "start_review":
        title = f"已进入 {trade_date} 复盘口述模式。"
    elif command == "finish_review":
        title = f"已结束 {trade_date} 复盘口述记录，下一步生成复盘送审稿。"
    elif message_type in {"calibration", "message_judgement"}:
        title = "已记录为飞书校准/消息判断样本。"
    lines = [
        title,
        f"落点：`{rel(raw_path)}`",
    ]
    if hints["股票代码"] or hints["动作词"] or hints["情绪分"]:
        picked = []
        if hints["股票代码"]:
            picked.append(f"股票：{', '.join(hints['股票代码'])}")
        if hints["动作词"]:
            picked.append(f"动作：{', '.join(hints['动作词'])}")
        if hints["情绪分"]:
            picked.append(f"情绪分：{hints['情绪分']}")
        lines.append("识别：" + "；".join(picked))
    if hints["歧义点"]:
        lines.append("待确认：" + "；".join(hints["歧义点"][:2]))
    lines.append("我不会把待确认内容写成你的正式买卖理由。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest one Feishu message into RAW.")
    parser.add_argument("--date", default="")
    parser.add_argument("--type", default="auto", choices=["auto", "review", "calibration", "message_judgement", "chat"])
    parser.add_argument("--sender", default="user")
    parser.add_argument("--source", default="feishu")
    parser.add_argument("--text", default="")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--no-notify", action="store_true")
    args = parser.parse_args()

    text = sys.stdin.read() if args.stdin or not args.text else args.text
    text = text.strip()
    if not text:
        print(json.dumps({"ok": False, "reason": "empty text"}, ensure_ascii=False))
        return 2

    state = load_state()
    command = command_from_text(text)
    trade_date = normalize_date(args.date or state.get("trade_date"), text)
    if command == "start_review":
        state = {"active": True, "trade_date": trade_date, "started_at": now_text(), "updated_at": now_text()}
        save_state(state)
    elif command == "finish_review":
        if state.get("trade_date"):
            trade_date = state["trade_date"]
        state["active"] = False
        state["updated_at"] = now_text()
        save_state(state)

    message_type = classify(text, args.type, state)
    hints = extract_hints(text)
    chat_path = write_chat_raw(text, args.sender, args.source, message_type, hints)

    review_path = None
    if message_type == "review":
        review_path = append_review_raw(trade_date, text, args.sender, args.source, hints, command)
        append_jsonl(
            review_jsonl_path(trade_date),
            {
                "schema": "feishu_oral_review_event_v1",
                "created_at": now_text(),
                "trade_date": trade_date,
                "sender": args.sender,
                "source": args.source,
                "command": command,
                "text": text,
                "hints": hints,
                "chat_raw": rel(chat_path),
            },
        )
    maybe_write_calibration(text, message_type, trade_date, hints, chat_path)

    event = {
        "schema": "feishu_message_ingest_v1",
        "created_at": now_text(),
        "trade_date": trade_date,
        "message_type": message_type,
        "command": command,
        "chat_raw": rel(chat_path),
        "review_raw": rel(review_path) if review_path else "",
        "hints": hints,
    }
    append_jsonl(EVENTS_PATH, event)

    raw_path = review_path or chat_path
    ack = render_ack(message_type, trade_date, raw_path, hints, command)
    notify_path = ""
    if not args.no_notify:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        notify = PENDING_DIR / f"{now_stamp()}-飞书口述回执.md"
        write_text(notify, ack)
        notify_path = rel(notify)

    print(
        json.dumps(
            {
                "ok": True,
                "trade_date": trade_date,
                "message_type": message_type,
                "command": command,
                "chat_raw": rel(chat_path),
                "review_raw": rel(review_path) if review_path else "",
                "notify": notify_path,
                "hints": hints,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
