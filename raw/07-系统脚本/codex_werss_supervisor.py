import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


# LEGACY: do not use for the current 15-minute cloud data connector chain.
# Current chain: LaunchAgent com.73wiki.cloud-data-connectors ->
# .system/scripts/run-cloud-data-connectors.mjs -> WeRSS/API/URL RAW capture.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
SYSTEM_DIR = PROJECT_ROOT / ".system"
LOG_DIR = SYSTEM_DIR / "logs"

DEFAULT_STATE = SYSTEM_DIR / "werss-api-state.json"
DEFAULT_AUDIT_JSON = SYSTEM_DIR / "werss-api-repair-audit.json"
DEFAULT_AUDIT_MD = SYSTEM_DIR / "werss-api-repair-audit.md"
DEFAULT_HEALTH_JSON = SYSTEM_DIR / "werss-health.json"
DEFAULT_INGEST_LOG = LOG_DIR / "werss-api-ingest.log"
DEFAULT_SUPERVISOR_LOG = LOG_DIR / "werss-supervisor.log"
DEFAULT_PRIVATE_SEEDS_CONFIG = SYSTEM_DIR / "werss-private-mp-seeds.json"
DEFAULT_PRIVATE_SEEDS_AUDIT = SYSTEM_DIR / "werss-private-mp-seeds.audit.json"
DEFAULT_PRIVATE_LINKS_AUDIT = SYSTEM_DIR / "werss-private-link-import.audit.json"
DEFAULT_PRIVATE_LINKS_STATE = SYSTEM_DIR / "werss-private-link-state.json"
DEFAULT_YOUZI_STATE = SYSTEM_DIR / "youzi-learning-state.json"
DEFAULT_YOUZI_REPORT_JSON = SYSTEM_DIR / "youzi-learning-report.json"
DEFAULT_YOUZI_REPORT_MD = SYSTEM_DIR / "youzi-learning-report.md"
DEFAULT_YOUZI_LOG = LOG_DIR / "youzi-learning.log"
DEFAULT_YOUZI_QUALITY_JSON = SYSTEM_DIR / "youzi-quality-audit.json"
DEFAULT_YOUZI_QUALITY_MD = SYSTEM_DIR / "youzi-quality-audit.md"
DEFAULT_YOUZI_AUTHOR_TARGETS = SYSTEM_DIR / "youzi-author-refresh-targets.json"
DEFAULT_YOUZI_AUTHOR_AUDIT_JSON = SYSTEM_DIR / "youzi-author-refresh-audit.json"
DEFAULT_YOUZI_AUTHOR_AUDIT_MD = SYSTEM_DIR / "youzi-author-refresh-audit.md"
DEFAULT_YOUZI_AUTHOR_LOG = LOG_DIR / "youzi-author-refresh.log"
DEFAULT_REPAIR_ROOT = PROJECT_ROOT / "raw" / "05-研报新闻" / "公众号" / "游资号"
DEFAULT_SUPERVISOR_LOCK = SYSTEM_DIR / "locks" / "werss-supervisor.lock"
DEFAULT_WECHAT_SEED_SCRIPT = SYSTEM_DIR / "scripts" / "fetch-wechat-mp-seeds.mjs"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{now_text()}] {message}\n")


def run_command(args: list[str], *, log_path: Path) -> subprocess.CompletedProcess[str]:
    append_log(log_path, f"RUN {' '.join(args)}")
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    if proc.stdout.strip():
        append_log(log_path, f"STDOUT {proc.stdout.strip()}")
    if proc.stderr.strip():
        append_log(log_path, f"STDERR {proc.stderr.strip()}")
    append_log(log_path, f"EXIT {proc.returncode}")
    return proc


def run_healthcheck(
    *,
    python_exe: str,
    health_script: Path,
    output_path: Path,
    max_stale_minutes: int,
    log_path: Path,
) -> dict:
    args = [
        python_exe,
        str(health_script),
        "--output",
        str(output_path),
        "--run-url-seeds",
        "--probe-wx-cache",
    ]
    proc = run_command(args, log_path=log_path)
    if proc.returncode != 0:
        raise RuntimeError("healthcheck failed")
    return json.loads(output_path.read_text(encoding="utf-8"))


def run_ingest(
    *,
    python_exe: str,
    ingest_script: Path,
    state_path: Path,
    audit_json_path: Path,
    audit_md_path: Path,
    ingest_log_path: Path,
    supervisor_log_path: Path,
) -> None:
    node_args = ["node", str(DEFAULT_WECHAT_SEED_SCRIPT)]
    node_proc = run_command(node_args, log_path=supervisor_log_path)
    if node_proc.returncode != 0:
        append_log(supervisor_log_path, "WARN local wechat URL seed capture failed; continuing to RAW scan")

    raw_watch_script = SCRIPT_DIR / "codex_raw_watch.py"
    raw_proc = run_command(
        [
            python_exe,
            str(raw_watch_script),
            "--root",
            str(PROJECT_ROOT),
            "--once",
            "--lookback-hours",
            "240",
        ],
        log_path=supervisor_log_path,
    )
    if raw_proc.returncode != 0:
        raise RuntimeError("local raw watch failed")

    batch_script = SCRIPT_DIR / "codex_batch_ingest_queue.py"
    args = [
        python_exe,
        str(batch_script),
    ]
    proc = run_command(args, log_path=supervisor_log_path)
    if proc.returncode != 0:
        raise RuntimeError("local batch ingest failed")


def run_repair(
    *,
    python_exe: str,
    ingest_script: Path,
    repair_roots: list[Path],
    audit_json_path: Path,
    audit_md_path: Path,
    ingest_log_path: Path,
    supervisor_log_path: Path,
) -> None:
    args = [
        python_exe,
        str(ingest_script),
        "--mode",
        "repair",
        "--once",
        "--repair-if-missing-ocr",
        "--audit-json",
        str(audit_json_path),
        "--audit-md",
        str(audit_md_path),
        "--log",
        str(ingest_log_path),
    ]
    for root in repair_roots:
        args.extend(["--repair-root", str(root)])
    proc = run_command(args, log_path=supervisor_log_path)
    if proc.returncode != 0:
        raise RuntimeError("repair failed")


def run_private_seeds(
    *,
    python_exe: str,
    seed_script: Path,
    config_path: Path,
    output_path: Path,
    supervisor_log_path: Path,
 ) -> bool:
    if not config_path.exists():
        append_log(supervisor_log_path, f"SEED skip missing config: {config_path}")
        return
    args = [
        python_exe,
        str(seed_script),
        "--config",
        str(config_path),
        "--output",
        str(output_path),
    ]
    proc = run_command(args, log_path=supervisor_log_path)
    if proc.returncode != 0:
        append_log(supervisor_log_path, "WARN private seed failed; continuing")
        return False
    return True


def run_private_link_import(
    *,
    python_exe: str,
    import_script: Path,
    output_path: Path,
    state_path: Path,
    supervisor_log_path: Path,
) -> bool:
    args = [
        python_exe,
        str(import_script),
        "--audit-output",
        str(output_path),
        "--state",
        str(state_path),
    ]
    proc = run_command(args, log_path=supervisor_log_path)
    if proc.returncode != 0:
        append_log(supervisor_log_path, "WARN private link import failed; continuing")
        return False
    return True


def run_youzi_learning(
    *,
    python_exe: str,
    script_path: Path,
    state_path: Path,
    report_json_path: Path,
    report_md_path: Path,
    youzi_log_path: Path,
    supervisor_log_path: Path,
) -> None:
    args = [
        python_exe,
        str(script_path),
        "--state",
        str(state_path),
        "--report-json",
        str(report_json_path),
        "--report-md",
        str(report_md_path),
        "--log",
        str(youzi_log_path),
    ]
    proc = run_command(args, log_path=supervisor_log_path)
    if proc.returncode != 0:
        raise RuntimeError("youzi learning failed")


def run_youzi_quality_audit(
    *,
    python_exe: str,
    script_path: Path,
    state_path: Path,
    audit_json_path: Path,
    audit_md_path: Path,
    supervisor_log_path: Path,
) -> None:
    args = [
        python_exe,
        str(script_path),
        "--state",
        str(state_path),
        "--audit-json",
        str(audit_json_path),
        "--audit-md",
        str(audit_md_path),
    ]
    proc = run_command(args, log_path=supervisor_log_path)
    if proc.returncode != 0:
        raise RuntimeError("youzi quality audit failed")


def run_youzi_author_refresh(
    *,
    python_exe: str,
    script_path: Path,
    targets_config_path: Path,
    audit_json_path: Path,
    audit_md_path: Path,
    author_log_path: Path,
    supervisor_log_path: Path,
) -> None:
    args = [
        python_exe,
        str(script_path),
        "--targets-config",
        str(targets_config_path),
        "--audit-json",
        str(audit_json_path),
        "--audit-md",
        str(audit_md_path),
        "--log",
        str(author_log_path),
    ]
    proc = run_command(args, log_path=supervisor_log_path)
    if proc.returncode != 0:
        raise RuntimeError("youzi author refresh failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--max-stale-minutes", type=int, default=120)
    parser.add_argument("--repair-every", type=int, default=0)
    parser.add_argument("--author-refresh-every", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--audit-json", default=str(DEFAULT_AUDIT_JSON))
    parser.add_argument("--audit-md", default=str(DEFAULT_AUDIT_MD))
    parser.add_argument("--health-output", default=str(DEFAULT_HEALTH_JSON))
    parser.add_argument("--ingest-log", default=str(DEFAULT_INGEST_LOG))
    parser.add_argument("--supervisor-log", default=str(DEFAULT_SUPERVISOR_LOG))
    parser.add_argument("--lock-file", default=str(DEFAULT_SUPERVISOR_LOCK))
    parser.add_argument("--private-seeds-config", default=str(DEFAULT_PRIVATE_SEEDS_CONFIG))
    parser.add_argument("--private-seeds-output", default=str(DEFAULT_PRIVATE_SEEDS_AUDIT))
    parser.add_argument("--private-seeds-every", type=int, default=0)
    parser.add_argument("--private-links-output", default=str(DEFAULT_PRIVATE_LINKS_AUDIT))
    parser.add_argument("--private-links-state", default=str(DEFAULT_PRIVATE_LINKS_STATE))
    parser.add_argument("--youzi-state", default=str(DEFAULT_YOUZI_STATE))
    parser.add_argument("--youzi-report-json", default=str(DEFAULT_YOUZI_REPORT_JSON))
    parser.add_argument("--youzi-report-md", default=str(DEFAULT_YOUZI_REPORT_MD))
    parser.add_argument("--youzi-log", default=str(DEFAULT_YOUZI_LOG))
    parser.add_argument("--youzi-quality-json", default=str(DEFAULT_YOUZI_QUALITY_JSON))
    parser.add_argument("--youzi-quality-md", default=str(DEFAULT_YOUZI_QUALITY_MD))
    parser.add_argument("--author-refresh-targets", default=str(DEFAULT_YOUZI_AUTHOR_TARGETS))
    parser.add_argument("--author-refresh-audit-json", default=str(DEFAULT_YOUZI_AUTHOR_AUDIT_JSON))
    parser.add_argument("--author-refresh-audit-md", default=str(DEFAULT_YOUZI_AUTHOR_AUDIT_MD))
    parser.add_argument("--author-refresh-log", default=str(DEFAULT_YOUZI_AUTHOR_LOG))
    parser.add_argument("--repair-root", action="append")
    args = parser.parse_args()

    health_script = SCRIPT_DIR / "codex_werss_healthcheck.py"
    ingest_script = SCRIPT_DIR / "codex_ingest_werss_api.py"
    seed_script = SCRIPT_DIR / "codex_seed_werss_private_mps.py"
    private_link_import_script = SCRIPT_DIR / "codex_consume_private_mp_links.py"
    youzi_learning_script = SCRIPT_DIR / "codex_youzi_learning_pipeline.py"
    youzi_quality_script = SCRIPT_DIR / "codex_youzi_quality_audit.py"
    youzi_author_refresh_script = SCRIPT_DIR / "codex_refresh_youzi_authors.py"
    state_path = Path(args.state)
    audit_json_path = Path(args.audit_json)
    audit_md_path = Path(args.audit_md)
    health_output_path = Path(args.health_output)
    ingest_log_path = Path(args.ingest_log)
    supervisor_log_path = Path(args.supervisor_log)
    lock_path = Path(args.lock_file)
    private_seeds_config_path = Path(args.private_seeds_config)
    private_seeds_output_path = Path(args.private_seeds_output)
    private_links_output_path = Path(args.private_links_output)
    private_links_state_path = Path(args.private_links_state)
    youzi_state_path = Path(args.youzi_state)
    youzi_report_json_path = Path(args.youzi_report_json)
    youzi_report_md_path = Path(args.youzi_report_md)
    youzi_log_path = Path(args.youzi_log)
    youzi_quality_json_path = Path(args.youzi_quality_json)
    youzi_quality_md_path = Path(args.youzi_quality_md)
    author_refresh_targets_path = Path(args.author_refresh_targets)
    author_refresh_audit_json_path = Path(args.author_refresh_audit_json)
    author_refresh_audit_md_path = Path(args.author_refresh_audit_md)
    author_refresh_log_path = Path(args.author_refresh_log)
    repair_roots = [Path(item) for item in args.repair_root] if args.repair_root else [DEFAULT_REPAIR_ROOT]

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            pid = int(lock_path.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            pid = 0
        if pid > 0:
            try:
                os.kill(pid, 0)
            except OSError:
                pass
            else:
                append_log(supervisor_log_path, f"LOCK another supervisor is active: pid={pid}")
                return 0
    lock_path.write_text(str(os.getpid()), encoding="utf-8")

    try:
        cycle = 0
        while True:
            cycle += 1
            try:
                health = run_healthcheck(
                    python_exe=args.python,
                    health_script=health_script,
                    output_path=health_output_path,
                    max_stale_minutes=args.max_stale_minutes,
                    log_path=supervisor_log_path,
                )
                append_log(
                    supervisor_log_path,
                    f"HEALTH mode={health.get('source_mode')} seeds={health.get('url_seed_capture', {}).get('seed_count')} wx_ok={health.get('wx_cli_cache', {}).get('daemon_status', {}).get('ok')}",
                )
                if args.private_seeds_every > 0 and cycle % args.private_seeds_every == 0:
                    run_private_seeds(
                        python_exe=args.python,
                        seed_script=seed_script,
                        config_path=private_seeds_config_path,
                        output_path=private_seeds_output_path,
                        supervisor_log_path=supervisor_log_path,
                    )
                    run_private_link_import(
                        python_exe=args.python,
                        import_script=private_link_import_script,
                        output_path=private_links_output_path,
                        state_path=private_links_state_path,
                        supervisor_log_path=supervisor_log_path,
                    )

                run_ingest(
                    python_exe=args.python,
                    ingest_script=ingest_script,
                    state_path=state_path,
                    audit_json_path=audit_json_path,
                    audit_md_path=audit_md_path,
                    ingest_log_path=ingest_log_path,
                    supervisor_log_path=supervisor_log_path,
                )

                run_youzi_learning(
                    python_exe=args.python,
                    script_path=youzi_learning_script,
                    state_path=youzi_state_path,
                    report_json_path=youzi_report_json_path,
                    report_md_path=youzi_report_md_path,
                    youzi_log_path=youzi_log_path,
                    supervisor_log_path=supervisor_log_path,
                )
                run_youzi_quality_audit(
                    python_exe=args.python,
                    script_path=youzi_quality_script,
                    state_path=youzi_state_path,
                    audit_json_path=youzi_quality_json_path,
                    audit_md_path=youzi_quality_md_path,
                    supervisor_log_path=supervisor_log_path,
                )

                if args.repair_every > 0 and cycle % args.repair_every == 0:
                    run_repair(
                        python_exe=args.python,
                        ingest_script=ingest_script,
                        repair_roots=repair_roots,
                        audit_json_path=audit_json_path,
                        audit_md_path=audit_md_path,
                        ingest_log_path=ingest_log_path,
                        supervisor_log_path=supervisor_log_path,
                    )
                    run_youzi_learning(
                        python_exe=args.python,
                        script_path=youzi_learning_script,
                        state_path=youzi_state_path,
                        report_json_path=youzi_report_json_path,
                        report_md_path=youzi_report_md_path,
                        youzi_log_path=youzi_log_path,
                        supervisor_log_path=supervisor_log_path,
                    )
                    run_youzi_quality_audit(
                        python_exe=args.python,
                        script_path=youzi_quality_script,
                        state_path=youzi_state_path,
                        audit_json_path=youzi_quality_json_path,
                        audit_md_path=youzi_quality_md_path,
                        supervisor_log_path=supervisor_log_path,
                    )

                if args.author_refresh_every > 0 and cycle % args.author_refresh_every == 0:
                    run_youzi_author_refresh(
                        python_exe=args.python,
                        script_path=youzi_author_refresh_script,
                        targets_config_path=author_refresh_targets_path,
                        audit_json_path=author_refresh_audit_json_path,
                        audit_md_path=author_refresh_audit_md_path,
                        author_log_path=author_refresh_log_path,
                        supervisor_log_path=supervisor_log_path,
                    )
                    run_youzi_learning(
                        python_exe=args.python,
                        script_path=youzi_learning_script,
                        state_path=youzi_state_path,
                        report_json_path=youzi_report_json_path,
                        report_md_path=youzi_report_md_path,
                        youzi_log_path=youzi_log_path,
                        supervisor_log_path=supervisor_log_path,
                    )
                    run_youzi_quality_audit(
                        python_exe=args.python,
                        script_path=youzi_quality_script,
                        state_path=youzi_state_path,
                        audit_json_path=youzi_quality_json_path,
                        audit_md_path=youzi_quality_md_path,
                        supervisor_log_path=supervisor_log_path,
                    )
            except Exception as exc:
                append_log(supervisor_log_path, f"ERROR {exc}")

            if args.once:
                return 0
            time.sleep(max(60, args.interval_seconds))
    finally:
        try:
            if lock_path.exists() and lock_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                lock_path.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
