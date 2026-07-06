#!/usr/bin/env python3
"""Watch Longxia review RAW files and hand them off to Codex.

This daemon is intentionally file-driven, not time-driven:
- Longxia can write the review at any time.
- Syncthing brings the RAW file to this Mac.
- Once the file is stable and marked for Codex follow-up, this script runs one
  Codex CLI job to complete the trading-brain layer.
"""

from __future__ import annotations

import hashlib
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(os.environ.get("WIKI_PROJECT_PATH", "/Users/qixinchaye/wiki/73神话"))
RAW_REVIEW_DIR = ROOT / "raw/02-每日复盘"
STATE_PATH = ROOT / ".system/longxia-review-handoff-state.json"
CURRENT_STATUS_PATH = ROOT / ".system/longxia-review-handoff-current.json"
LOCK_PATH = ROOT / ".system/longxia-review-handoff.lock"
LOG_PATH = ROOT / ".system/logs/longxia-review-handoff.log"
CODEX_BIN = os.environ.get("CODEX_BIN", "/Users/qixinchaye/.local/bin/codex")
QUALITY_SCRIPT = ROOT / ".system/scripts/check-longxia-review-quality.py"
POLL_SECONDS = int(os.environ.get("LONGXIA_REVIEW_POLL_SECONDS", "30"))
STABLE_SECONDS = int(os.environ.get("LONGXIA_REVIEW_STABLE_SECONDS", "90"))
CODEX_TIMEOUT_SECONDS = int(os.environ.get("LONGXIA_REVIEW_CODEX_TIMEOUT_SECONDS", "1800"))
RECENT_BAD_REVIEW_NOTIFY_SECONDS = int(os.environ.get("LONGXIA_REVIEW_BAD_NOTIFY_SECONDS", str(12 * 60 * 60)))
DATE_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-复盘\.md$")


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    ensure_parent(LOG_PATH)
    line = f"{now_text()} {message}\n"
    LOG_PATH.open("a", encoding="utf-8").write(line)
    print(line, end="", flush=True)


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json(path: Path, payload) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_status(**updates) -> None:
    current = {} if updates.get("status") in {"starting", "idle"} else read_json(CURRENT_STATUS_PATH, {})
    current.update(updates)
    current["updated_at"] = now_text()
    write_json(CURRENT_STATUS_PATH, current)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_longxia_ready(path: Path) -> tuple[bool, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return False, f"read_failed:{exc}"

    if "writer: longxia" not in text and "龙虾" not in text:
        return False, "missing_longxia_marker"
    if "needs_codex_followup: true" not in text and "待 Codex 主流程" not in text:
        return False, "missing_codex_followup_marker"

    required_sections = [
        "## 一、今日一句话结论",
        "## 二、赚钱效应与市场环境",
        "## 三、盘前计划回看",
        "## 四、今日实际交易",
        "## 五、持仓与资金",
        "## 六、主线与板块",
        "## 七、连板天梯与情绪锚",
        "## 八、用户口述原文",
        "## 九、操作质量",
        "## 十、错误候选",
        "## 十一、D+验证任务",
        "## 十二、明日操盘要点",
        "## 十三、待用户补充",
    ]
    missing = [section for section in required_sections if section not in text]
    if missing:
        return False, "missing_sections:" + ",".join(missing[:3])
    return True, "ready"


def looks_like_longxia_candidate(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    markers = [
        "writer: longxia",
        "needs_codex_followup",
        "待 Codex 主流程",
        "## 十一、D+验证任务",
        "## 十三、待用户补充",
        "通达信热榜 Top100",
        "涨停原因 6 维度",
        "涨停原因六维",
    ]
    return any(marker in text for marker in markers)


def acquire_lock() -> bool:
    ensure_parent(LOCK_PATH)
    try:
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"{os.getpid()} {now_text()}\n".encode("utf-8"))
        os.close(fd)
        return True
    except FileExistsError:
        try:
            mtime = LOCK_PATH.stat().st_mtime
            if time.time() - mtime > 60 * 60:
                LOCK_PATH.unlink()
                return acquire_lock()
        except Exception:
            pass
        return False


def release_lock() -> None:
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


def find_candidates(target_date: str | None = None) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    if not RAW_REVIEW_DIR.exists():
        return out
    for path in RAW_REVIEW_DIR.iterdir():
        if not path.is_file():
            continue
        match = DATE_RE.match(path.name)
        if not match:
            continue
        trade_date = match.group("date")
        if target_date and trade_date != target_date:
            continue
        out.append((trade_date, path))
    return sorted(out, key=lambda item: item[1].stat().st_mtime)


def stable_enough(path: Path) -> bool:
    try:
        return time.time() - path.stat().st_mtime >= STABLE_SECONDS
    except FileNotFoundError:
        return False


def recently_modified(path: Path, seconds: int = RECENT_BAD_REVIEW_NOTIFY_SECONDS) -> bool:
    try:
        return time.time() - path.stat().st_mtime <= seconds
    except FileNotFoundError:
        return False


def build_prompt(trade_date: str, raw_rel: str, raw_hash: str, quality_report_rel: str | None = None) -> str:
    quality_line = f"- {quality_report_rel}\n" if quality_report_rel else ""
    return f"""你是 73神话 Trading Review Wiki 的 Codex 主流程。

任务：龙虾已经完成事实层 RAW 复盘。请立即接手，补齐交易大脑层复盘，并写入 WIKI。

交易日：{trade_date}
龙虾 RAW 复盘：{raw_rel}
RAW hash：{raw_hash}

必须先读取：
- {raw_rel}
- raw/01-交割单/{trade_date}/交割单.md（如果存在）
- raw/01-交割单/{trade_date}/交割单结构化.json（如果存在）
- raw/02-每日复盘/{trade_date}-市场数据补全.md（如果存在）
- raw/03-每日计划/{trade_date}-竞价监控清单.md（如果存在）
- wiki/07-作战室/{trade_date}-作战总控.md（如果存在）
- wiki/10-系统配置/龙虾每日复盘RAW模板与分工规则.md
- wiki/10-系统配置/短线涨停预判与每日验证进化规则.md
- wiki/10-系统配置/龙虾每日复盘RAW质量验收与偷懒识别规则.md
- wiki/10-系统配置/连板天梯与短线情绪周期规则.md
- wiki/10-系统配置/作战室生成规则.md
{quality_line}

请完成并写入：
1. wiki/09-统计与进化/{trade_date}-盘后复盘与AI训练回写.md
2. wiki/07-作战室/{trade_date}-盘后回看.md
3. wiki/09-统计与进化/{trade_date}-次日涨停候选评分表.md
4. wiki/09-统计与进化/{trade_date}-涨停预判验证与权重修正.md（如缺少次日实际数据，先写待验证骨架）
5. .system/codex-review-done-{trade_date}.json

写入要求：
- 不覆盖龙虾 RAW。
- 买卖理由、心态只引用用户口述、交割单和 RAW 证据；缺失就写待用户补充，不编。
- 明确区分“事实层结论”和“Codex 主流程判断”。
- 补作战室回看、交易归因、错误候选、模式进化候选、D+验证任务、明日作战输入。
- 必须读取通达信热榜 Top100、完整非 ST 连板天梯、涨停原因 6 维度、财联社和公众号 RAW；缺失则在数据缺口中列明。
- 必须对“哪些消息可能刺激次日涨停”打分排序，输出次日涨停候选评分表。
- 必须用连板天梯和实际涨停结果验证前一日预判；当日还没有验证数据时，建立待验证任务。
- 必须读取龙虾复盘 RAW 质量验收报告；如果 Top100、连板口径、6 维涨停原因、JSON、D+验证缺失，要写入待用户/龙虾补充项。
- 只有高置信、可复用内容才写成 WIKI 判断；低置信内容保留为候选。
- 最后更新 AI 上下文：运行 raw/07-系统脚本/codex_update_ai_context.py --date {trade_date}，如失败在 done JSON 中记录。

完成后只给简短结果，列出写入文件和待用户补充项。
"""


def run_quality_check(trade_date: str) -> dict:
    if not QUALITY_SCRIPT.exists():
        return {
            "ok": False,
            "grade": "MISSING_SCRIPT",
            "report": None,
            "json": None,
            "notify": None,
            "error": f"missing {QUALITY_SCRIPT}",
        }
    cmd = [sys.executable, str(QUALITY_SCRIPT), "--date", trade_date, "--write"]
    result = subprocess.run(
        cmd,
        text=True,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )
    parsed = {}
    try:
        parsed = json.loads(result.stdout or "{}")
    except Exception:
        parsed = {}
    report = ROOT / "wiki/09-统计与进化" / f"{trade_date}-龙虾复盘RAW质量验收.md"
    json_path = ROOT / ".system" / f"longxia-review-quality-{trade_date}.json"
    notify = ROOT / ".system/feishu-notify-pending" / f"{trade_date}-龙虾复盘质量提醒.md"
    return {
        "ok": result.returncode == 0,
        "status": result.returncode,
        "grade": parsed.get("grade"),
        "score": parsed.get("score"),
        "issues": parsed.get("issues", []),
        "warnings": parsed.get("warnings", []),
        "report": str(report.relative_to(ROOT)) if report.exists() else None,
        "json": str(json_path.relative_to(ROOT)) if json_path.exists() else None,
        "notify": str(notify.relative_to(ROOT)) if notify.exists() else None,
        "stderr": result.stderr.splitlines()[-5:],
    }


def run_codex(trade_date: str, raw_path: Path, raw_hash: str) -> dict:
    raw_rel = str(raw_path.relative_to(ROOT))
    out_dir = ROOT / ".system/logs/longxia-review-handoff"
    out_dir.mkdir(parents=True, exist_ok=True)
    final_msg = out_dir / f"{trade_date}-codex-final.md"
    quality = run_quality_check(trade_date)
    if quality.get("report"):
        log(f"QUALITY trade_date={trade_date} grade={quality.get('grade')} score={quality.get('score')} report={quality.get('report')}")
    else:
        log(f"QUALITY trade_date={trade_date} grade={quality.get('grade')} error={quality.get('error')}")
    prompt = build_prompt(trade_date, raw_rel, raw_hash, quality.get("report"))
    cmd = [
        CODEX_BIN,
        "exec",
        "--cd",
        str(ROOT),
        "--sandbox",
        "workspace-write",
        "--skip-git-repo-check",
        "--output-last-message",
        str(final_msg),
        "-",
    ]
    log(f"RUN trade_date={trade_date} raw={raw_rel}")
    write_status(
        status="processing",
        trade_date=trade_date,
        raw_review=raw_rel,
        raw_hash=raw_hash,
        started_at=now_text(),
        codex_done_path=f".system/codex-review-done-{trade_date}.json",
        expected_outputs=[
            f"wiki/09-统计与进化/{trade_date}-龙虾复盘RAW质量验收.md",
            f"wiki/09-统计与进化/{trade_date}-盘后复盘与AI训练回写.md",
            f"wiki/07-作战室/{trade_date}-盘后回看.md",
            f"wiki/09-统计与进化/{trade_date}-次日涨停候选评分表.md",
            f"wiki/09-统计与进化/{trade_date}-涨停预判验证与权重修正.md",
            f".system/codex-review-done-{trade_date}.json",
        ],
        quality_check=quality,
    )
    started = time.time()
    env = {
        **os.environ,
        "HOME": os.environ.get("HOME", "/Users/qixinchaye"),
        "CODEX_HOME": os.environ.get("CODEX_HOME", "/Users/qixinchaye/.codex"),
        "PATH": os.environ.get("PATH", "/Users/qixinchaye/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"),
    }
    result = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=CODEX_TIMEOUT_SECONDS,
    )
    duration = round(time.time() - started, 2)
    stdout_path = out_dir / f"{trade_date}-codex-stdout.log"
    stderr_path = out_dir / f"{trade_date}-codex-stderr.log"
    stdout_path.write_text(result.stdout or "", encoding="utf-8")
    stderr_path.write_text(result.stderr or "", encoding="utf-8")
    ok = result.returncode == 0
    log(f"DONE trade_date={trade_date} ok={ok} status={result.returncode} duration={duration}s")
    return {
        "ok": ok,
        "status": result.returncode,
        "duration_seconds": duration,
        "quality_check": quality,
        "stdout_log": str(stdout_path.relative_to(ROOT)),
        "stderr_log": str(stderr_path.relative_to(ROOT)),
        "final_message": str(final_msg.relative_to(ROOT)),
    }


def process_once(target_date: str | None = None) -> None:
    state = read_json(STATE_PATH, {"processed": {}, "seen": {}})
    state.setdefault("processed", {})
    state.setdefault("seen", {})
    found = False
    ignored = 0
    waiting = False

    for trade_date, path in find_candidates(target_date):
        found = True
        raw_rel = str(path.relative_to(ROOT))
        if not stable_enough(path):
            waiting = True
            write_status(
                status="waiting_for_stable_file",
                trade_date=trade_date,
                raw_review=raw_rel,
                stable_after_seconds=STABLE_SECONDS,
            )
            continue
        ready, reason = is_longxia_ready(path)
        if not ready:
            state["seen"][raw_rel] = {"at": now_text(), "ready": False, "reason": reason}
            if reason in {"missing_longxia_marker", "missing_codex_followup_marker"} and not target_date:
                if recently_modified(path) and looks_like_longxia_candidate(path):
                    quality = run_quality_check(trade_date)
                    log(f"QUALITY_NOT_READY trade_date={trade_date} reason={reason} grade={quality.get('grade')} score={quality.get('score')}")
                ignored += 1
                write_json(STATE_PATH, state)
                continue
            waiting = True
            write_status(
                status="waiting_for_ready_raw",
                trade_date=trade_date,
                raw_review=raw_rel,
                reason=reason,
            )
            write_json(STATE_PATH, state)
            continue
        raw_hash = sha256_file(path)
        processed = state["processed"].get(raw_rel)
        if processed and processed.get("raw_hash") == raw_hash and processed.get("ok"):
            write_status(
                status="already_done",
                trade_date=trade_date,
                raw_review=raw_rel,
                raw_hash=raw_hash,
                last_result=processed,
            )
            continue
        if not acquire_lock():
            log(f"SKIP locked raw={raw_rel}")
            write_status(status="locked", trade_date=trade_date, raw_review=raw_rel)
            return
        try:
            result = run_codex(trade_date, path, raw_hash)
            state["processed"][raw_rel] = {
                "trade_date": trade_date,
                "raw_hash": raw_hash,
                "at": now_text(),
                **result,
            }
            write_json(STATE_PATH, state)
            write_status(
                status="done" if result.get("ok") else "codex_failed",
                trade_date=trade_date,
                raw_review=raw_rel,
                raw_hash=raw_hash,
                result=result,
                finished_at=now_text(),
            )
        except subprocess.TimeoutExpired:
            log(f"TIMEOUT trade_date={trade_date} raw={raw_rel}")
            state["processed"][raw_rel] = {
                "trade_date": trade_date,
                "raw_hash": raw_hash,
                "at": now_text(),
                "ok": False,
                "error": "codex_timeout",
            }
            write_json(STATE_PATH, state)
            write_status(
                status="codex_timeout",
                trade_date=trade_date,
                raw_review=raw_rel,
                raw_hash=raw_hash,
                finished_at=now_text(),
            )
        except Exception as exc:
            log(f"ERROR trade_date={trade_date} raw={raw_rel} error={exc}")
            state["processed"][raw_rel] = {
                "trade_date": trade_date,
                "raw_hash": raw_hash,
                "at": now_text(),
                "ok": False,
                "error": str(exc),
            }
            write_json(STATE_PATH, state)
            write_status(
                status="error",
                trade_date=trade_date,
                raw_review=raw_rel,
                raw_hash=raw_hash if "raw_hash" in locals() else "",
                error=str(exc),
                finished_at=now_text(),
            )
        finally:
            release_lock()
    if not found or (ignored and not waiting):
        write_status(
            status="idle",
            target_date=target_date,
            watching=str(RAW_REVIEW_DIR.relative_to(ROOT)),
            expected_pattern="YYYY-MM-DD-复盘.md",
            ignored_non_longxia_files=ignored,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--date", help="Only process one trade date, formatted YYYY-MM-DD.")
    args = parser.parse_args()
    log(f"START once={args.once} date={args.date or '*'} root={ROOT}")
    write_status(
        status="starting",
        mode="once" if args.once else "daemon",
        target_date=args.date,
        root=str(ROOT),
        watching=str(RAW_REVIEW_DIR.relative_to(ROOT)),
    )
    while True:
        process_once(args.date)
        if args.once:
            return 0
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
