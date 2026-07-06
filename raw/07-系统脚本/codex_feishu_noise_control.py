#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SYSTEM = ROOT / ".system"
PENDING = SYSTEM / "feishu-notify-pending"
OUT = ROOT / "raw/11-Codex分析产物/飞书降噪"
WIKI = ROOT / "wiki/09-统计与进化/飞书通知清晰度检查.md"
POLICY = SYSTEM / "feishu-notification-policy.json"


DEFAULT_POLICY = {
    "must_send": ["自动化任务Watchdog告警", "22:30", "动态作战室Top5", "重大消息雷达待判断", "超短知识自进化学习待校准"],
    "digest_only": ["每日重要信息Top10", "公众号三榜Top10", "作战室候选验证回看"],
    "wiki_only": ["页面质量检查", "结构补齐", "RAW旁路归因", "普通统计刷新"],
    "required_fields": ["判断对象", "当前判断", "我的判断逻辑", "不确定/需要纠偏", "回复格式"],
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def classify(name: str, text: str, policy: dict) -> str:
    hay = name + "\n" + text
    if any(k in hay for k in policy["must_send"]):
        return "必须发"
    if any(k in hay for k in policy["digest_only"]):
        return "晚间汇总"
    if any(k in hay for k in policy["wiki_only"]):
        return "只写wiki"
    return "待观察"


def main() -> int:
    write_json(POLICY, DEFAULT_POLICY)
    rows = []
    for path in sorted(PENDING.glob("*.md")) if PENDING.exists() else []:
        text = read_text(path)
        missing = [field for field in DEFAULT_POLICY["required_fields"] if field not in text]
        rows.append({
            "file": str(path.relative_to(ROOT)),
            "class": classify(path.name, text, DEFAULT_POLICY),
            "missing_fields": missing,
            "size": len(text),
        })
    today = datetime.now().strftime("%Y-%m-%d")
    report = {"schema": "73wiki-feishu-noise-control-v1", "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "rows": rows, "policy": DEFAULT_POLICY}
    OUT.joinpath(today).mkdir(parents=True, exist_ok=True)
    write_json(OUT / today / "feishu-noise-control.json", report)
    lines = [
        "# 飞书通知清晰度检查",
        "",
        f"- 生成时间：{report['generatedAt']}",
        f"- 待发通知：{len(rows)}",
        "- 原则：只把需要你校准/决策/知道故障的内容发飞书；普通统计只写wiki。",
        "",
        "| 文件 | 分级 | 缺字段 | 字数 |",
        "|---|---|---|---:|",
    ]
    for row in rows:
        lines.append(f"| `{row['file']}` | {row['class']} | {'、'.join(row['missing_fields']) or '无'} | {row['size']} |")
    if not rows:
        lines.append("| 无 | - | - | 0 |")
    lines += ["", "## 当前策略", "", "```json", json.dumps(DEFAULT_POLICY, ensure_ascii=False, indent=2), "```"]
    md = "\n".join(lines) + "\n"
    (OUT / today / "feishu-noise-control.md").write_text(md, encoding="utf-8")
    WIKI.write_text(md, encoding="utf-8")
    print(json.dumps({"ok": True, "pending": len(rows), "output": str(WIKI.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
