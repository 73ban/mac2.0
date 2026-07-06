#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "raw/11-Codex分析产物/Watchdog自修复"


def run(cmd: list[str]) -> dict:
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=120)
        return {"cmd": " ".join(cmd), "ok": p.returncode == 0, "stdout": p.stdout[-1000:], "stderr": p.stderr[-1000:]}
    except Exception as exc:
        return {"cmd": " ".join(cmd), "ok": False, "error": str(exc)}


def main() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    actions = []
    checks = [
        (ROOT / "raw/04-市场数据/三榜热度合并" / today / "三榜热度合并.md", ["/usr/bin/python3", "raw/07-系统脚本/codex_merge_three_hotlists.py", "--date", today]),
        (ROOT / "raw/11-Codex分析产物/短线模式词典" / today / "模式词频扫描.md", ["/usr/bin/python3", "raw/07-系统脚本/codex_shortline_mode_dictionary_scan.py"]),
        (ROOT / "raw/11-Codex分析产物/交易模式质量检查" / today / "mode-page-lint.md", ["/usr/bin/python3", "raw/07-系统脚本/codex_mode_page_lint.py"]),
    ]
    for path, cmd in checks:
        if path.exists():
            actions.append({"target": str(path.relative_to(ROOT)), "status": "exists"})
            continue
        result = run(cmd)
        actions.append({"target": str(path.relative_to(ROOT)), "status": "repaired" if result.get("ok") else "failed", "result": result})
    OUT.joinpath(today).mkdir(parents=True, exist_ok=True)
    payload = {"schema": "73wiki-watchdog-self-heal-v1", "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "actions": actions}
    (OUT / today / "watchdog-self-heal.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": all(x["status"] != "failed" for x in actions), "actions": actions}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
