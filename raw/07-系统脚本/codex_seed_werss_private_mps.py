import argparse
import json
import time
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE = "http://127.0.0.1:8002/api/v1/wx"
DEFAULT_USER = "admin"
DEFAULT_PASS = "admin@123"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / ".system" / "werss-private-mp-seeds.json"
DEFAULT_OUTPUT = ROOT / ".system" / "werss-private-mp-seeds.audit.json"
USER_AGENT = "CodexWeRSSPrivateSeed/1.0"


def request_json(
    url: str,
    *,
    token: str = "",
    method: str = "GET",
    form: dict | None = None,
    json_body: dict | None = None,
) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    payload = None
    if form is not None:
        payload = urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_body is not None:
        payload = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, data=payload, headers=headers, method=method)
    with urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8", errors="ignore"))


def login(base_url: str, username: str, password: str) -> str:
    response = request_json(
        f"{base_url.rstrip('/')}/auth/login",
        method="POST",
        form={"username": username, "password": password},
    )
    return response["data"]["access_token"]


def load_config(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        items = raw.get("items") or []
        return [item for item in items if isinstance(item, dict)]
    return []


def poll_article_total(base_url: str, token: str, mp_id: str, *, seconds: int, interval: int) -> int:
    deadline = time.time() + max(0, seconds)
    total = 0
    while True:
        response = request_json(
            f"{base_url.rstrip('/')}/articles?offset=0&limit=1&mp_id={quote(mp_id, safe='')}",
            token=token,
        )
        total = int((response.get("data") or {}).get("total") or 0)
        if total > 0 or time.time() >= deadline:
            return total
        time.sleep(max(1, interval))


def seed_one(base_url: str, token: str, item: dict, *, poll_seconds: int, poll_interval: int) -> dict:
    article_url = str(item.get("article_url") or "").strip()
    if not article_url:
        raise ValueError("missing article_url")

    by_article = request_json(
        f"{base_url.rstrip('/')}/mps/by_article?url={quote(article_url, safe='')}",
        token=token,
        method="POST",
    )["data"]
    mp_info = by_article.get("mp_info") or {}
    mp_name = str(item.get("mp_name") or mp_info.get("mp_name") or "").strip()
    mp_intro = str(item.get("mp_intro") or "seeded_by_article").strip()
    biz = str(mp_info.get("biz") or "").strip()
    avatar = str(mp_info.get("logo") or by_article.get("topic_image") or "").strip()
    if not mp_name or not biz:
        raise ValueError("missing mp_name or biz from by_article")

    add_resp = request_json(
        f"{base_url.rstrip('/')}/mps",
        token=token,
        method="POST",
        json_body={
            "mp_name": mp_name,
            "mp_id": biz,
            "avatar": avatar,
            "mp_intro": mp_intro,
        },
    )["data"]
    mp_id = str(add_resp.get("id") or by_article.get("mp_id") or "").strip()
    if not mp_id:
        raise ValueError("missing mp_id after add/update")

    status_resp = request_json(
        f"{base_url.rstrip('/')}/mps/{quote(mp_id, safe='')}",
        token=token,
        method="PUT",
        json_body={"status": 1},
    )["data"]
    update_resp = request_json(
        f"{base_url.rstrip('/')}/mps/update/{quote(mp_id, safe='')}?start_page=0&end_page={int(item.get('end_page') or 5)}",
        token=token,
    )["data"]
    article_total = poll_article_total(
        base_url,
        token,
        mp_id,
        seconds=poll_seconds,
        interval=poll_interval,
    )
    return {
        "article_url": article_url,
        "mp_name": mp_name,
        "mp_id": mp_id,
        "biz": biz,
        "status": status_resp.get("status"),
        "update_total": int(update_resp.get("total") or 0),
        "article_total": article_total,
        "category": item.get("category", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--username", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASS)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--poll-seconds", type=int, default=25)
    parser.add_argument("--poll-interval", type=int, default=5)
    args = parser.parse_args()

    config_path = Path(args.config)
    output_path = Path(args.output)
    items = load_config(config_path)
    token = login(args.base_url, args.username, args.password)

    seeded = []
    failed = []
    for item in items:
        try:
            seeded.append(
                seed_one(
                    args.base_url,
                    token,
                    item,
                    poll_seconds=args.poll_seconds,
                    poll_interval=args.poll_interval,
                )
            )
        except Exception as exc:
            failed.append(
                {
                    "article_url": item.get("article_url", ""),
                    "mp_name": item.get("mp_name", ""),
                    "error": str(exc),
                }
            )

    result = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "config": str(config_path),
        "seeded": seeded,
        "failed": failed,
        "summary": {
            "items": len(items),
            "seeded": len(seeded),
            "failed": len(failed),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
