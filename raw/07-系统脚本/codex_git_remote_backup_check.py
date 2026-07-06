#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "wiki/10-系统配置/Git远程备份说明.md"


def run(args: list[str]) -> str:
    try:
        p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=10)
        return (p.stdout + p.stderr).strip()
    except Exception as exc:
        return str(exc)


def main() -> int:
    remotes = run(["git", "remote", "-v"])
    branch = run(["git", "branch", "--show-current"])
    last = run(["git", "log", "--oneline", "-3"])
    status = "未配置远程仓库" if not remotes.strip() else "已配置远程仓库"
    lines = [
        "# Git远程备份说明",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 当前状态：{status}",
        f"- 当前分支：`{branch or 'unknown'}`",
        "",
        "## 当前远程",
        "",
        "```text",
        remotes or "(none)",
        "```",
        "",
        "## 最近提交",
        "",
        "```text",
        last,
        "```",
        "",
        "## 如果要备份到私有仓库",
        "",
        "1. 在 GitHub / Gitee / GitLab 建一个私有仓库。",
        "2. 在本机执行：",
        "",
        "```bash",
        "git remote add origin <你的私有仓库地址>",
        "git push -u origin main",
        "```",
        "",
        "## 边界",
        "",
        "- 现在所有提交都在 Mac 本地 `.git`。",
        "- 没有远程地址和凭据前，我不会把内容上传到任何网站。",
        "- raw大体量数据已被 `.gitignore` 排除，只跟踪核心wiki、脚本和小型事实层。",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "status": status, "output": str(OUT.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
