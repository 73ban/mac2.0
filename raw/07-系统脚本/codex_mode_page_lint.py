#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODE_DIR = ROOT / "wiki/04-L4交易模式与执行/游资交易模式卡片库"
OUT_RAW = ROOT / f"raw/11-Codex分析产物/交易模式质量检查/{date.today().isoformat()}"
OUT_WIKI = ROOT / f"wiki/09-统计与进化/{date.today().isoformat()}-交易模式页面质量检查.md"

REQUIRED_SECTIONS = [
    "## 别名",
    "## 模式定义",
    "## 适用环境",
    "## 行情分层胜率",
    "## 有效条件",
    "## 失效条件",
    "## 买点",
    "## 卖点",
    "## 仓位权限",
    "## 统计字段",
    "## 修正记录",
    "## 当前等级",
]


def is_mode_page(path: Path) -> bool:
    name = path.name
    if not name.endswith(".md"):
        return False
    if "索引" in name:
        return False
    return True


def lint_page(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    missing = [section for section in REQUIRED_SECTIONS if section not in text]
    warnings: list[str] = []
    if "待统计" not in text and "胜率" in text and "## 行情分层胜率" in text:
        warnings.append("有分层胜率章节，但没有待统计或样本占位，需确认是否已有真实统计")
    if "Codex推定" not in text and "## 复盘归因规则" in text:
        warnings.append("有复盘归因规则但未出现Codex推定字段")
    return {
        "file": path.relative_to(ROOT).as_posix(),
        "title": path.stem,
        "ok": not missing,
        "missing": missing,
        "warnings": warnings,
    }


def render_md(items: list[dict]) -> str:
    total = len(items)
    ok = sum(1 for item in items if item["ok"])
    bad = total - ok
    lines = [
        f"# {date.today().isoformat()} 交易模式页面质量检查",
        "",
        "## 结论",
        "",
        f"- 模式页总数：{total}",
        f"- 结构完整：{ok}",
        f"- 需要补齐：{bad}",
        "",
        "检查项：别名、定义、适用环境、行情分层胜率、有效/失效条件、买卖点、仓位、统计字段、修正记录、当前等级。",
        "",
        "## 需要补齐的模式页",
        "",
        "| 模式页 | 缺失项 | 文件 |",
        "|---|---|---|",
    ]
    for item in items:
        if item["ok"]:
            continue
        missing = "、".join(x.replace("## ", "") for x in item["missing"])
        lines.append(f"| {item['title']} | {missing} | `{item['file']}` |")
    if bad == 0:
        lines.append("| 无 | 无 | 无 |")

    warned = [item for item in items if item["warnings"]]
    lines += ["", "## 软提醒", "", "| 模式页 | 提醒 | 文件 |", "|---|---|---|"]
    if warned:
        for item in warned:
            lines.append(f"| {item['title']} | {'；'.join(item['warnings'])} | `{item['file']}` |")
    else:
        lines.append("| 无 | 无 | 无 |")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_RAW.mkdir(parents=True, exist_ok=True)
    items = [lint_page(path) for path in sorted(MODE_DIR.glob("*.md")) if is_mode_page(path)]
    payload = {
        "schema": "73wiki-mode-page-lint-v1",
        "date": date.today().isoformat(),
        "total": len(items),
        "ok": sum(1 for item in items if item["ok"]),
        "needs_fix": sum(1 for item in items if not item["ok"]),
        "items": items,
    }
    (OUT_RAW / "mode-page-lint.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = render_md(items)
    (OUT_RAW / "mode-page-lint.md").write_text(md, encoding="utf-8")
    OUT_WIKI.write_text(md, encoding="utf-8")
    print(json.dumps({"ok": True, "total": payload["total"], "needs_fix": payload["needs_fix"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
