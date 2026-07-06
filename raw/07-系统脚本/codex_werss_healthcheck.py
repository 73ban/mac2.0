import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / ".system" / "werss-health.json"
DEFAULT_SEED_SCRIPT = ROOT / ".system" / "scripts" / "fetch-wechat-mp-seeds.mjs"
DEFAULT_SEEDS = ROOT / ".system" / "wechat-mp-url-seeds.json"
DEFAULT_STATE = ROOT / ".system" / "wechat-mp-url-seeds-state.json"
DEFAULT_WX_DAEMON_LOG = Path.home() / ".wx-cli" / "daemon.log"


def tail(path: Path, size: int = 4000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text[-size:]


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def run_cmd(args: list[str], timeout: int = 20) -> dict:
    try:
        proc = subprocess.run(
            args,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "status": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }
    except Exception as exc:
        return {"ok": False, "status": None, "stdout": "", "stderr": str(exc)}


def latest_raw_files(limit: int = 5) -> list[dict]:
    raw_dir = ROOT / "raw" / "05-研报新闻" / "公众号"
    files = []
    if raw_dir.exists():
        for path in raw_dir.rglob("*.md"):
            try:
                files.append((path.stat().st_mtime, path))
            except Exception:
                pass
    out = []
    for mtime, path in sorted(files, reverse=True)[:limit]:
        out.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "mtime": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--run-url-seeds", action="store_true")
    parser.add_argument("--probe-wx-cache", action="store_true")
    args = parser.parse_args()

    seeds = load_json(DEFAULT_SEEDS, [])
    state = load_json(DEFAULT_STATE, {"seen": {}, "runs": []})
    url_seed_result = None
    if args.run_url_seeds:
        url_seed_result = run_cmd(["node", str(DEFAULT_SEED_SCRIPT)], timeout=90)

    wx_status = run_cmd(["wx", "daemon", "status"], timeout=10)
    wx_articles = None
    if args.probe_wx_cache:
        wx_articles = run_cmd(["wx", "biz-articles", "--json", "--limit", "20"], timeout=20)

    result = {
        "schema": "73wiki-local-wechat-ingest-health-v1",
        "checked_at": datetime.now().astimezone().isoformat(),
        "source_mode": "local-direct",
        "legacy_werss_api": "disabled",
        "url_seed_capture": {
            "enabled": True,
            "script": str(DEFAULT_SEED_SCRIPT),
            "seeds_path": str(DEFAULT_SEEDS),
            "seed_count": len(seeds) if isinstance(seeds, list) else None,
            "seen_count": len(state.get("seen", {})) if isinstance(state, dict) else None,
            "last_run": (state.get("runs") or [{}])[-1].get("at", "") if isinstance(state, dict) else "",
            "run_result": url_seed_result,
        },
        "wx_cli_cache": {
            "enabled": True,
            "daemon_status": wx_status,
            "biz_articles_probe": wx_articles,
            "daemon_log": str(DEFAULT_WX_DAEMON_LOG),
            "daemon_log_tail": tail(DEFAULT_WX_DAEMON_LOG),
        },
        "latest_raw_files": latest_raw_files(),
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
