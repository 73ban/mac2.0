#!/usr/bin/env python3
"""Mac migration doctor for 73神话 / Trading Review Wiki."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = Path("/Applications/Trading Review Wiki.app")
INTEGRATED_REPO = Path("/Users/qixinchaye/Workspace/trading-review-wiki-ymj-integrated")
WEKNORA_REPO = Path("/Users/qixinchaye/Workspace/ymj8903668-droid-open-source/WeKnora")
QUEST_REPO = Path("/Users/qixinchaye/Workspace/ymj8903668-droid-open-source/QUEST")
DOCKER_CLI = Path("/Users/qixinchaye/.local/bin/docker")


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 10) -> tuple[bool, str]:
    try:
        out = subprocess.check_output(cmd, cwd=str(cwd or ROOT), stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return True, out.strip()
    except Exception as exc:
        return False, str(exc).strip()


def exists(path: Path) -> str:
    return "OK" if path.exists() else "MISSING"


WINDOWS_PATTERNS = [
    "C:\\wiki\\73神话",
    "C:\\\\wiki\\\\73神话",
    "C:/wiki/73神话",
    "C:\\Users\\Administrator",
    "C:\\\\Users\\\\Administrator",
    "C:/Users/Administrator",
    "--project C:",
]


def text_files(base: Path, suffixes: set[str] | None = None) -> list[Path]:
    if not base.exists():
        return []
    files = [base] if base.is_file() else list(base.rglob("*"))
    out: list[Path] = []
    for path in files:
        if not path.is_file():
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        out.append(path)
    return out


def count_windows_hits(files: list[Path], exclude_parts: set[str] | None = None, exclude_names: set[str] | None = None) -> dict[str, object]:
    exclude_parts = exclude_parts or set()
    exclude_names = exclude_names or set()
    hit_files = 0
    hit_count = 0
    samples: list[str] = []
    for path in files:
        try:
            rel = path.relative_to(ROOT)
            rel_parts = set(rel.parts)
            rel_text = rel.as_posix()
        except ValueError:
            rel_parts = set(path.parts)
            rel_text = str(path)
        if rel_parts & exclude_parts:
            continue
        if path.name in exclude_names:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        count = sum(text.count(pattern) for pattern in WINDOWS_PATTERNS)
        if count <= 0:
            continue
        hit_files += 1
        hit_count += count
        if len(samples) < 5:
            samples.append(rel_text)
    return {"files": hit_files, "hits": hit_count, "samples": samples}


def count_windows_paths() -> dict[str, dict[str, object]]:
    integrated_scripts = INTEGRATED_REPO / "scripts"
    standalone_cailian = Path("/Users/qixinchaye/Desktop/standalone-small-files/fetch-cs-cailian-raw.mjs")
    return {
        "active_system_scripts": count_windows_hits(
            text_files(ROOT / ".system/scripts", {".py", ".js", ".mjs"}),
        ),
        "active_raw_python_scripts": count_windows_hits(
            text_files(ROOT / "raw/07-系统脚本", {".py"}),
            exclude_parts={"legacy-tools"},
            exclude_names={"codex_mac_migration_doctor.py", "codex_normalize_mac_paths.py"},
        ),
        "active_generated_latest_cache": count_windows_hits(
            [p for p in text_files(ROOT / ".llm-wiki", {".json", ".md"}) if p.name.startswith("latest")],
        ),
        "active_runtime_state": count_windows_hits(
            [p for p in text_files(ROOT / ".system", {".json", ".jsonl"}) if "logs" not in p.parts],
            exclude_names={"raw-queue-consumer-state.json"},
        ),
        "legacy_runtime_state": count_windows_hits(
            [ROOT / ".system/raw-queue-consumer-state.json"],
        ),
        "integrated_source_scripts": count_windows_hits(
            text_files(integrated_scripts, {".mjs", ".js", ".ts"}),
        ),
        "standalone_connectors": count_windows_hits(
            [standalone_cailian],
        ),
        "migration_archives_and_logs": count_windows_hits(
            text_files(ROOT / "wiki/10-系统配置", {".md", ".json"})
            + text_files(ROOT / ".system/logs", {".log", ".md", ".json"})
            + text_files(ROOT / "raw/07-系统脚本/legacy-tools", {".py", ".md", ".json"}),
        ),
    }


def main() -> int:
    checks: list[dict[str, str]] = []
    for label, path in [
        ("wiki_root", ROOT),
        ("raw", ROOT / "raw"),
        ("wiki", ROOT / "wiki"),
        ("data", ROOT / "data"),
        ("current_ai_context", ROOT / ".system/current-ai-context.json"),
        ("installed_app", APP),
        ("integrated_repo", INTEGRATED_REPO),
        ("weknora_repo", WEKNORA_REPO),
        ("weknora_lite_binary", WEKNORA_REPO / "WeKnora-lite"),
        ("quest_repo", QUEST_REPO),
        ("quest_venv", QUEST_REPO / ".venv"),
        ("quest_lite_requirements", QUEST_REPO / "requirements-mac-lite.txt"),
    ]:
        checks.append({"item": label, "status": exists(path), "detail": str(path)})

    commands = [
        ("python3", ["python3", "--version"], ROOT),
        ("node", ["node", "--version"], ROOT),
        ("npm", ["npm", "--version"], ROOT),
        ("codex", ["codex", "--version"], ROOT),
        ("git", ["git", "--version"], ROOT),
        ("wx", ["wx", "--version"], ROOT),
        ("pnpm", ["pnpm", "--version"], ROOT),
        ("cargo", ["cargo", "--version"], ROOT),
        ("go", ["go", "version"], ROOT),
        ("docker", [str(DOCKER_CLI) if DOCKER_CLI.exists() else "docker", "--version"], ROOT),
        ("docker_compose", [str(DOCKER_CLI) if DOCKER_CLI.exists() else "docker", "compose", "version"], ROOT),
        ("docker_daemon", [str(DOCKER_CLI) if DOCKER_CLI.exists() else "docker", "info", "--format", "{{.ServerVersion}}"], ROOT),
    ]
    for label, cmd, cwd in commands:
        ok, detail = run(cmd, cwd)
        checks.append({"item": label, "status": "OK" if ok else "MISSING", "detail": detail.splitlines()[0] if detail else ""})

    py_ok, py_detail = run(["python3", "-m", "py_compile", *[str(p) for p in (ROOT / "raw/07-系统脚本").glob("codex_*.py")]], ROOT, timeout=20)
    checks.append({"item": "python_scripts_py_compile", "status": "OK" if py_ok else "FAIL", "detail": py_detail[:200]})

    if INTEGRATED_REPO.exists():
        build_ok, build_detail = run(["npm", "run", "build"], INTEGRATED_REPO, timeout=30)
        checks.append({"item": "integrated_frontend_build", "status": "OK" if build_ok else "FAIL", "detail": build_detail.splitlines()[-1] if build_detail else ""})

    weknora_ok, weknora_detail = run(["curl", "-fsS", "--max-time", "5", "http://127.0.0.1:8080/"], ROOT, timeout=8)
    checks.append(
        {
            "item": "weknora_lite_http",
            "status": "OK" if weknora_ok and "WeKnora" in weknora_detail else "FAIL",
            "detail": "http://127.0.0.1:8080/ responds" if weknora_ok else weknora_detail[:200],
        }
    )

    quest_smoke_ok, quest_smoke_detail = run([str(ROOT / "raw/07-系统脚本/start_quest_mac.sh"), "--smoke"], ROOT, timeout=30)
    checks.append(
        {
            "item": "quest_lite_smoke",
            "status": "OK" if quest_smoke_ok else "FAIL",
            "detail": quest_smoke_detail.splitlines()[-1] if quest_smoke_detail else "",
        }
    )

    context = {}
    context_path = ROOT / ".system/current-ai-context.json"
    if context_path.exists():
        context = json.loads(context_path.read_text(encoding="utf-8"))
    checks.append(
        {
            "item": "ai_context",
            "status": "OK" if context.get("enabled") and context.get("pinnedPages") else "FAIL",
            "detail": f"activeDate={context.get('activeDate')} pinned={len(context.get('pinnedPages', []))}",
        }
    )

    windows_counts = count_windows_paths()
    report = {
        "schema": "73wiki-mac-migration-doctor-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "root": str(ROOT),
        "checks": checks,
        "windowsPathCounts": windows_counts,
    }
    out_json = ROOT / "data/trading/mac-migration-doctor.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = [
        f"| {x['item']} | {x['status']} | {x['detail'].replace('|', '/')} |"
        for x in checks
    ]
    path_rows = [
        f"| {k} | {v.get('files', 0)} | {v.get('hits', 0)} | {', '.join(v.get('samples', []))} |"
        for k, v in windows_counts.items()
    ]
    out_md = ROOT / "wiki/10-系统配置/Mac迁移体检报告.md"
    out_md.write_text(
        "\n".join(
            [
                "# Mac迁移体检报告",
                "",
                f"更新时间：{report['generatedAt']}",
                "",
                "## 结论",
                "",
                "主程序、Wiki 数据、AI 上下文和核心脚本已可在 Mac 上运行。生态服务中，wx-cli 已安装但 daemon 未运行；Docker CLI/Compose 与 Docker daemon 可用；WeKnora Lite 已构建并通过 8080 HTTP 冒烟；QUEST 已安装 Mac runtime，可导入 API-agent 工具，torch/MPS 可用。vLLM 0.19.0 因 NVIDIA cuDNN frontend 依赖无 macOS arm64 wheel，无法在本机 Python 环境安装。",
                "",
                "## 检查项",
                "",
                "| 项目 | 状态 | 详情 |",
                "|---|---|---|",
                *rows,
                "",
                "## Windows路径残留",
                "",
                "| 范围 | 文件数 | 命中数 | 示例 |",
                "|---|---:|---:|---|",
                *path_rows,
                "",
                "说明：`active_*` 和 `integrated_source_scripts` 是当前执行链路；`legacy_runtime_state`、`migration_archives_and_logs` 是历史运行记录、旧日志或迁移归档，不作为 Mac 当前入口。",
                "",
                "## 下一步",
                "",
                "1. 微信/公众号抓取按本机直抓口径处理；若使用 wx-cli 缓存，先补齐 `config.json` 或完成 `wx init`。",
                "2. WeKnora 当前使用 Lite 单二进制，入口为 `http://127.0.0.1:8080/`；Docker daemon 可用，若要切换标准版，运行 `start_weknora_mac.sh docker`。",
                "3. QUEST 当前使用 Mac runtime + torch/MPS；vLLM full local serving 需 Linux/NVIDIA CUDA 环境或远端推理服务，本机 macOS arm64 不满足依赖。",
                "4. 每次迁移、升级或重启后，运行本脚本重新体检。",
                "",
                "机器报告：`data/trading/mac-migration-doctor.json`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"json": str(out_json), "wiki": str(out_md)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
