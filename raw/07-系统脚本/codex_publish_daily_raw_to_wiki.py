#!/usr/bin/env python3
"""Publish daily RAW trade slip/review into formal WIKI pages and audit gaps."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from codex_trading_calendar import is_trade_day


ROOT = Path(__file__).resolve().parents[2]
RAW_TRADE = ROOT / "raw/01-交割单"
RAW_REVIEW = ROOT / "raw/02-每日复盘"
WIKI_TRADE = ROOT / "wiki/06-持仓与资金管理"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
SYSTEM_DIR = ROOT / ".system"
FEISHU_PENDING = SYSTEM_DIR / "feishu-notify-pending"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_text_any_encoding(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "gb18030", "gbk", "latin1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rel(path: Path | None) -> str:
    if not path:
        return ""
    try:
        return str(path.relative_to(ROOT))
    except Exception:
        return str(path)


def is_postmarket_now() -> bool:
    current = datetime.now()
    return current.hour * 100 + current.minute >= 1530


def is_weekend(date: str) -> bool:
    return not is_trade_day(date)


def find_raw_review(date: str) -> Path | None:
    preferred = [
        RAW_REVIEW / f"{date}-复盘.md",
        RAW_REVIEW / f"{date}.md",
        RAW_REVIEW / f"{date}-盘后复盘RAW.md",
        RAW_REVIEW / f"{date}-飞书复盘RAW.md",
    ]
    for path in preferred:
        if path.exists():
            return path
    candidates = [
        path
        for path in sorted(RAW_REVIEW.glob(f"{date}*.md"))
        if ".stversions" not in path.parts
        and "午盘" not in path.name
        and "美股" not in path.name
        and "补充" not in path.name
        and "市场数据补全" not in path.name
    ]
    if candidates:
        return candidates[0]
    fallback = [path for path in sorted(RAW_REVIEW.glob(f"{date}*.md")) if ".stversions" not in path.parts]
    return fallback[0] if fallback else None


def find_raw_trade_files(date: str) -> list[Path]:
    candidates: list[Path] = []
    date_dir = RAW_TRADE / date
    if date_dir.exists():
        preferred = [
            date_dir / "交割单.md",
            date_dir / "交割单结构化.json",
            date_dir / f"{date}-交割单.md",
            date_dir / "当日委托.md",
            date_dir / "我的持仓.md",
        ]
        candidates.extend(path for path in preferred if path.exists())
        for path in sorted(date_dir.glob("*.md")):
            if path not in candidates and not path.name.startswith("."):
                candidates.append(path)
        for path in sorted(date_dir.glob("*.json")):
            if path not in candidates and not path.name.startswith("."):
                candidates.append(path)
        for pattern in ("*.xls", "*.xlsx", "*.csv", "*.tsv"):
            for path in sorted(date_dir.glob(pattern)):
                if path not in candidates and not path.name.startswith("."):
                    candidates.append(path)
    flat = [
        RAW_TRADE / f"{date}-交割单.md",
        RAW_TRADE / f"{date}-委托明细.md",
        RAW_TRADE / f"{date}-持仓.md",
    ]
    candidates.extend(path for path in flat if path.exists() and path not in candidates)
    return candidates


def first_trade_markdown(files: list[Path]) -> Path | None:
    for path in files:
        if path.suffix.lower() == ".md" and "交割单" in path.name:
            return path
    for path in files:
        if path.suffix.lower() == ".md":
            return path
    return None


def text_table_files(files: list[Path]) -> list[Path]:
    usable: list[Path] = []
    for path in files:
        if path.suffix.lower() not in {".xls", ".xlsx", ".csv", ".tsv", ".txt"}:
            continue
        try:
            text = read_text_any_encoding(path)
        except Exception:
            continue
        if "\x00" in text[:200]:
            continue
        if any(key in text[:300] for key in ("证券代码", "委托时间", "成交时间", "证券名称")):
            usable.append(path)
    return usable


def publish_review(date: str, raw_path: Path | None, dry_run: bool = False) -> dict:
    out = WIKI_STATS / f"{date}-复盘.md"
    if not raw_path:
        return {"ok": False, "missing": True, "raw": "", "wiki": rel(out), "message": "RAW 每日复盘缺失。"}
    raw = read_text(raw_path)
    body = "\n".join(
        [
            "---",
            "type: 每日复盘正式归档",
            f"trade_date: {date}",
            "source_type: raw_daily_review",
            f"source_path: {rel(raw_path)}",
            f"source_sha256: {sha256_text(raw)}",
            f"updated: {now_text()}",
            "status: WIKI正式归档",
            "---",
            "",
            f"# {date} 每日复盘",
            "",
            "本页由 RAW 每日复盘自动发布到正式 WIKI。RAW 保留原始事实，WIKI 页用于检索、统计和后续训练。",
            "",
            f"- RAW 来源：`{rel(raw_path)}`",
            f"- RAW 哈希：`{sha256_text(raw)}`",
            "",
            "## RAW 正文",
            "",
            raw.rstrip(),
            "",
        ]
    )
    if not dry_run:
        write_text(out, body)
    return {"ok": True, "missing": False, "raw": rel(raw_path), "wiki": rel(out), "sha256": sha256_text(raw)}


def publish_trade(date: str, raw_files: list[Path], dry_run: bool = False) -> dict:
    out = WIKI_TRADE / f"{date}-交割单.md"
    raw_md = first_trade_markdown(raw_files)
    if not raw_md:
        table_files = text_table_files(raw_files)
        if not table_files:
            return {
                "ok": False,
                "missing": True,
                "rawFiles": [rel(path) for path in raw_files],
                "wiki": rel(out),
                "message": "RAW 交割单 Markdown 缺失。",
            }
        raw_parts: list[str] = []
        for path in table_files:
            text = read_text_any_encoding(path).rstrip()
            raw_parts.extend(
                [
                    f"## 原始表格：{path.name}",
                    "",
                    f"- RAW 来源：`{rel(path)}`",
                    "",
                    "```text",
                    text,
                    "```",
                    "",
                ]
            )
        raw = "\n".join(raw_parts).rstrip()
        body = "\n".join(
            [
                "---",
                "type: 交割单正式归档",
                f"trade_date: {date}",
                "source_type: raw_trade_table_text_export",
                f"source_path: {rel(table_files[0])}",
                f"source_sha256: {sha256_text(raw)}",
                f"updated: {now_text()}",
                "status: WIKI正式归档",
                "---",
                "",
                f"# {date} 交割单",
                "",
                "本页由 RAW 文本型交易导出原件自动发布到正式 WIKI。买卖理由仍以用户口述和 RAW 复盘为准，不在此处编造。",
                "",
                "## 同日 RAW 原件",
                "",
                *[f"- `{rel(path)}`" for path in raw_files],
                "",
                "## RAW 正文",
                "",
                raw,
                "",
            ]
        )
        if not dry_run:
            write_text(out, body)
        return {
            "ok": True,
            "missing": False,
            "raw": rel(table_files[0]),
            "rawFiles": [rel(path) for path in raw_files],
            "wiki": rel(out),
            "sha256": sha256_text(raw),
        }
    raw = read_text(raw_md)
    extra_files = [path for path in raw_files if path != raw_md]
    body = "\n".join(
        [
            "---",
            "type: 交割单正式归档",
            f"trade_date: {date}",
            "source_type: raw_trade_slip",
            f"source_path: {rel(raw_md)}",
            f"source_sha256: {sha256_text(raw)}",
            f"updated: {now_text()}",
            "status: WIKI正式归档",
            "---",
            "",
            f"# {date} 交割单",
            "",
            "本页由 RAW 交割单自动发布到正式 WIKI。买卖理由仍以用户口述和 RAW 复盘为准，不在此处编造。",
            "",
            f"- RAW 来源：`{rel(raw_md)}`",
            f"- RAW 哈希：`{sha256_text(raw)}`",
            "",
            "## 同日附属 RAW",
            "",
            *([f"- `{rel(path)}`" for path in extra_files] or ["- 无。"]),
            "",
            "## RAW 正文",
            "",
            raw.rstrip(),
            "",
        ]
    )
    if not dry_run:
        write_text(out, body)
    return {
        "ok": True,
        "missing": False,
        "raw": rel(raw_md),
        "rawFiles": [rel(path) for path in raw_files],
        "wiki": rel(out),
        "sha256": sha256_text(raw),
    }


def render_audit(date: str, payload: dict) -> str:
    review = payload["review"]
    trade = payload["trade"]
    trade_required = payload.get("tradeRequired", True)
    lines = [
        f"# {date} 每日 RAW 入 WIKI 审计",
        "",
        f"生成时间：{payload['generatedAt']}",
        "",
        "## 结论",
        "",
        f"- 总体：{'PASS' if payload['ok'] else 'FAIL'}",
        f"- 复盘入 WIKI：{'完成' if review['ok'] else '缺失'}",
        f"- 交割单入 WIKI：{'完成' if trade['ok'] else ('缺失' if trade_required else '非交易日不要求')}",
        "",
        "## 写入结果",
        "",
        "| 项目 | RAW | WIKI | 状态 |",
        "|---|---|---|---|",
        f"| 每日复盘 | `{review.get('raw', '')}` | `{review.get('wiki', '')}` | {'完成' if review['ok'] else '缺失'} |",
        f"| 交割单 | `{trade.get('raw', '')}` | `{trade.get('wiki', '')}` | {'完成' if trade['ok'] else ('缺失' if trade_required else '非交易日不要求')} |",
        "",
        "## 缺口处理",
        "",
    ]
    gaps = []
    if not review["ok"]:
        gaps.append("- 缺 RAW 每日复盘：需要用户口述、飞书桥或 Mac 本机入口写入 `raw/02-每日复盘/YYYY-MM-DD-复盘.md`。")
    if not trade["ok"] and trade_required:
        gaps.append("- 缺 RAW 交割单 Markdown：需要用户导出、截图OCR或 Mac 本机入口写入 `raw/01-交割单/YYYY-MM-DD/交割单.md`。")
    if gaps:
        lines.extend(gaps)
    else:
        lines.append("- 无。")
    lines.extend(
        [
            "",
            "## 硬规则",
            "",
            "- RAW 是事实源，WIKI 是正式检索和训练入口。",
            "- 每个交易日的交割单和复盘都必须入 WIKI，不允许只停留在 RAW。",
            "- 买卖理由只能来自用户口述、交割单和 RAW 证据，缺失就写缺口。",
            "",
        ]
    )
    return "\n".join(lines)


def render_notify(date: str, payload: dict) -> str:
    review = payload["review"]
    trade = payload["trade"]
    trade_required = payload.get("tradeRequired", True)
    lines = [
        f"# {date} 每日 WIKI 入库缺口",
        "",
        "检测到交割单/复盘没有完整写入正式 WIKI。",
        "",
        f"- 复盘入 WIKI：{'完成' if review['ok'] else '缺失'}",
        f"- 交割单入 WIKI：{'完成' if trade['ok'] else ('缺失' if trade_required else '非交易日不要求')}",
        f"- 审计页：`wiki/09-统计与进化/{date}-每日RAW入WIKI审计.md`",
        "",
        "需要处理：",
    ]
    if not review["ok"]:
        lines.append(f"- 请补 `raw/02-每日复盘/{date}-复盘.md`。")
    if not trade["ok"] and trade_required:
        lines.append(f"- 请补并同步 `raw/01-交割单/{date}/交割单.md`。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish daily RAW trade/review into formal WIKI pages.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-before-postmarket", action="store_true")
    args = parser.parse_args()

    raw_review = find_raw_review(args.date)
    raw_trade_files = find_raw_trade_files(args.date)
    review = publish_review(args.date, raw_review, dry_run=args.dry_run)
    trade = publish_trade(args.date, raw_trade_files, dry_run=args.dry_run)
    trade_day = not is_weekend(args.date)
    required_now = bool(raw_review or raw_trade_files) or (trade_day and (args.allow_before_postmarket or is_postmarket_now()))
    trade_required = bool(raw_trade_files) or trade_day
    ok = bool(review["ok"] and (trade["ok"] or not trade_required)) if required_now else True
    payload = {
        "schema": "73wiki-daily-raw-to-wiki-publish-v1",
        "generatedAt": now_text(),
        "date": args.date,
        "requiredNow": required_now,
        "tradeRequired": trade_required,
        "ok": ok,
        "review": review,
        "trade": trade,
        "outputs": {
            "audit": f"wiki/09-统计与进化/{args.date}-每日RAW入WIKI审计.md",
            "status": ".system/daily-wiki-publish-status.json",
            "notify": f".system/feishu-notify-pending/{args.date}-每日WIKI入库缺口.md",
        },
    }
    audit = render_audit(args.date, payload)
    if not args.dry_run:
        write_text(WIKI_STATS / f"{args.date}-每日RAW入WIKI审计.md", audit)
        SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
        (SYSTEM_DIR / "daily-wiki-publish-status.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        notify_path = FEISHU_PENDING / f"{args.date}-每日WIKI入库缺口.md"
        if required_now and not ok:
            write_text(notify_path, render_notify(args.date, payload))
        elif notify_path.exists():
            notify_path.unlink()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
