#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = ROOT / "raw/11-Codex分析产物/交易模式归因审计"
OUT_ROOT = ROOT / "raw/11-Codex分析产物/RAW交割单旁路归因"
WIKI_STATS = ROOT / "wiki/09-统计与进化"
CODE_RE = re.compile(r"(?<!\d)(?:00[0-3]\d{3}|30[0-2]\d{3}|60[0-5]\d{3}|68[89]\d{3}|8\d{5})(?!\d)")
BUY_RE = re.compile(r"(融资买入|担保品买入|证券买入|买入|加仓|建仓)")
BAD_RE = re.compile(r"(未成交|已撤|撤单|废单|失败|已报)")


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except Exception:
        return str(path)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    if data.startswith(b"PK\x03\x04"):
        return ""
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="ignore")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def latest_audit() -> Path | None:
    files = sorted(AUDIT_ROOT.glob("*/trade-mode-attribution-audit.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def sidecar_path(source: str) -> Path:
    safe = source.replace("/", "__").replace(" ", "_")
    return OUT_ROOT / datetime.now().strftime("%Y-%m-%d") / f"{safe}.json"


def infer_mode(line: str, context: str) -> tuple[str, list[str], str]:
    hay = f"{line}\n{context}"
    rules = [
        ("分歧转一致", ["弱转强", "低开转强", "分歧转一致", "超预期", "回封"]),
        ("趋势主升", ["趋势", "主升", "新高", "中军", "容量", "抱团"]),
        ("一进二回封", ["一进二", "二板", "回封", "首板次日"]),
        ("前排确认打板", ["打板", "涨停价", "排板", "封板", "板上"]),
        ("主线核心低吸", ["低吸", "核心低吸", "承接", "跌停附近", "恐慌"]),
        ("冰点恐慌修复", ["冰点", "反核", "撬板", "恐慌"]),
        ("断板反包", ["断板", "反包", "首阴", "N字"]),
        ("高低切补涨", ["高低切", "补涨", "低位"]),
        ("龙头战法", ["龙头", "总龙头", "空间板", "辨识度", "核心票"]),
    ]
    scored = []
    for mode, words in rules:
        hits = [w for w in words if w in hay]
        if hits:
            scored.append((len(hits), mode, hits))
    if not scored:
        return "待人工归因", [], "缺少明确模式词，只保留RAW旁路样本"
    scored.sort(reverse=True)
    primary = scored[0][1]
    secondary = [x[1] for x in scored[1:4]]
    evidence = "、".join(scored[0][2][:4])
    return primary, secondary, f"命中模式词：{evidence}"


def parse_file(path: Path) -> list[dict[str, Any]]:
    text = read_text(path)
    lines = text.splitlines()
    out = []
    for idx, line in enumerate(lines, 1):
        if not BUY_RE.search(line) or BAD_RE.search(line):
            continue
        m = CODE_RE.search(line)
        if not m:
            continue
        code = m.group(0)
        context = "\n".join(lines[max(0, idx - 8): min(len(lines), idx + 8)])
        mode, secondary, evidence = infer_mode(line, context)
        out.append({
            "line": idx,
            "code": code,
            "raw_line": line.strip(),
            "primary_mode": mode,
            "secondary_modes": secondary,
            "mode_source": "Codex旁路推定",
            "confidence": "medium" if mode != "待人工归因" else "low",
            "evidence": evidence,
        })
    return out


def main() -> int:
    audit_path = latest_audit()
    if not audit_path:
        print(json.dumps({"ok": False, "error": "missing audit"}, ensure_ascii=False))
        return 1
    audit = read_json(audit_path, {})
    items = audit.get("items") or []
    raw_items = [x for x in items if str(x.get("file") or "").startswith("raw/") and not x.get("has_mode_attribution")]
    updated = []
    mode_counts: defaultdict[str, int] = defaultdict(int)
    for item in raw_items:
        source = str(item.get("file") or "")
        path = ROOT / source
        rows = parse_file(path)
        if not rows:
            continue
        for row in rows:
            mode_counts[row["primary_mode"]] += 1
        payload = {
            "schema": "73wiki-raw-trade-mode-sidecar-v1",
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
            "note": "旁路归因，不改RAW原文。",
            "rows": rows,
        }
        out = sidecar_path(source)
        write_text(out, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        updated.append(rel(out))

    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# {today} RAW交割单旁路归因",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- RAW缺口文件：{len(raw_items)}",
        f"- 已生成旁路文件：{len(updated)}",
        "- 原则：RAW原文保真，不直接写回；旁路结果用于后续正式wiki回填和模式统计校准。",
        "",
        "## 模式分布",
        "",
        "| 模式 | 笔数 |",
        "|---|---:|",
    ]
    for mode, count in sorted(mode_counts.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"| {mode} | {count} |")
    lines += ["", "## 旁路文件", ""]
    for path in updated[:200]:
        lines.append(f"- `{path}`")
    md = "\n".join(lines) + "\n"
    write_text(OUT_ROOT / today / "raw-trade-mode-sidecar-summary.md", md)
    write_text(WIKI_STATS / f"{today}-RAW交割单旁路归因.md", md)
    print(json.dumps({"ok": True, "raw_missing": len(raw_items), "sidecars": len(updated), "modes": dict(mode_counts)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
