#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


payload = json.loads(sys.stdin.read())
path = Path("/Users/qixinchaye/Documents/Codex/2026-06-27/new-chat/.env")
lines = path.read_text(encoding="utf-8", errors="ignore").splitlines() if path.exists() else []
updates = {
    "FEISHU_APP_ID": payload["app_id"],
    "FEISHU_APP_SECRET": payload["app_secret"],
    "FEISHU_VERIFICATION_TOKEN": payload["verification_token"],
    "FEISHU_DOMAIN": "https://open.feishu.cn",
    "FEISHU_NOTIFY_STATE_PATH": "/Users/qixinchaye/wiki/73神话/.system/feishu-notifier-state.json",
}

seen: set[str] = set()
out: list[str] = []
for line in lines:
    if line.strip() and not line.lstrip().startswith("#") and "=" in line:
        key = line.split("=", 1)[0]
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    else:
        out.append(line)

for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")

path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
path.chmod(0o600)
print(json.dumps({"ok": True, "updated_keys": list(updates.keys())}, ensure_ascii=False))
