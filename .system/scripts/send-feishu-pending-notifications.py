#!/usr/bin/env python3
"""Send pending Feishu/Lark notification markdown files if a webhook is configured."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(os.environ.get("WIKI_PROJECT_PATH", "/Users/qixinchaye/wiki/73神话"))
PENDING_DIR = ROOT / ".system/feishu-notify-pending"
SENT_DIR = ROOT / ".system/feishu-notify-sent"
LOG_PATH = ROOT / ".system/logs/feishu-notifications.log"
STATE_PATH = ROOT / ".system/feishu-notifier-state.json"
DEFAULT_ENV_PATH = Path("/Users/qixinchaye/Documents/Codex/2026-06-27/new-chat/.env")
LINT_SCRIPT = ROOT / "raw/07-系统脚本/codex_feishu_protocol_lint.py"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.open("a", encoding="utf-8").write(f"{now_text()} {message}\n")


def webhook_url() -> str | None:
    return os.environ.get("FEISHU_WEBHOOK_URL") or os.environ.get("LARK_WEBHOOK_URL")


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def app_config() -> dict[str, str]:
    env_file = read_env_file(Path(os.environ.get("FEISHU_BOT_ENV_PATH", str(DEFAULT_ENV_PATH))))
    return {
        "app_id": os.environ.get("FEISHU_APP_ID") or env_file.get("FEISHU_APP_ID", ""),
        "app_secret": os.environ.get("FEISHU_APP_SECRET") or env_file.get("FEISHU_APP_SECRET", ""),
        "domain": (os.environ.get("FEISHU_DOMAIN") or env_file.get("FEISHU_DOMAIN", "https://open.feishu.cn")).rstrip("/"),
    }


def notify_chat_id() -> str:
    explicit = os.environ.get("FEISHU_NOTIFY_CHAT_ID") or os.environ.get("LARK_NOTIFY_CHAT_ID")
    if explicit:
        return explicit
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8")).get("chat_id", "")
    except Exception:
        return ""


def post_text(url: str, text: str) -> None:
    payload = json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        body = response.read().decode("utf-8", errors="ignore")
        if response.status >= 300:
            raise RuntimeError(f"status={response.status} body={body}")


def tenant_access_token(config: dict[str, str]) -> str:
    payload = json.dumps(
        {"app_id": config["app_id"], "app_secret": config["app_secret"]},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f'{config["domain"]}/open-apis/auth/v3/tenant_access_token/internal',
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        parsed = json.loads(response.read().decode("utf-8", errors="ignore"))
    if parsed.get("code") != 0:
        raise RuntimeError(f"failed to fetch tenant_access_token: {parsed.get('msg')}")
    return parsed["tenant_access_token"]


def post_app_text(config: dict[str, str], chat_id: str, text: str) -> None:
    token = tenant_access_token(config)
    payload = json.dumps(
        {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f'{config["domain"]}/open-apis/im/v1/messages?receive_id_type=chat_id',
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        parsed = json.loads(response.read().decode("utf-8", errors="ignore"))
    if parsed.get("code") != 0:
        raise RuntimeError(f"failed to send message: {parsed.get('msg')}")


def lint_pending() -> None:
    if not LINT_SCRIPT.exists():
        return
    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT), "--quarantine", "--write"],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        log(f"FEISHU_LINT_FAILED returncode={result.returncode} stderr={result.stderr.strip()[:500]}")


def main() -> int:
    url = webhook_url()
    config = app_config()
    chat_id = notify_chat_id()
    if not PENDING_DIR.exists():
        print(json.dumps({"ok": True, "pending": 0, "sent": 0}, ensure_ascii=False))
        return 0

    lint_pending()
    files = sorted(PENDING_DIR.glob("*.md"))
    if not url and not (config["app_id"] and config["app_secret"] and chat_id):
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "missing webhook or app chat target",
                    "pending": len(files),
                    "files": [str(path.relative_to(ROOT)) for path in files],
                    "need": [
                        "FEISHU_WEBHOOK_URL/LARK_WEBHOOK_URL",
                        "or FEISHU_APP_ID + FEISHU_APP_SECRET + recorded chat_id",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2 if files else 0

    SENT_DIR.mkdir(parents=True, exist_ok=True)
    sent = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if url:
            post_text(url, text)
        else:
            post_app_text(config, chat_id, text)
        target = SENT_DIR / path.name
        path.rename(target)
        sent.append(str(target.relative_to(ROOT)))
        log(f"SENT {target.relative_to(ROOT)}")

    print(json.dumps({"ok": True, "pending": len(files), "sent": sent}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
