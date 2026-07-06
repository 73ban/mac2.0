import argparse
import importlib.util
import json
import re
import time
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
RAW_LINK_ROOT = ROOT / "raw" / "公众号"
RAW_MP_ROOT = ROOT / "raw" / "05-研报新闻" / "公众号"
SYSTEM_DIR = ROOT / ".system"
DEFAULT_BASE = "http://127.0.0.1:8002/api/v1/wx"
DEFAULT_USER = "admin"
DEFAULT_PASS = "admin@123"
DEFAULT_SEEDS = SYSTEM_DIR / "werss-private-mp-seeds.json"
DEFAULT_AUDIT = SYSTEM_DIR / "werss-private-link-import.audit.json"
DEFAULT_STATE = SYSTEM_DIR / "werss-private-link-state.json"
INGEST_SCRIPT = ROOT / "raw" / "07-系统脚本" / "codex_ingest_werss_api.py"
USER_AGENT = "CodexPrivateLinkConsumer/1.0"
MP_URL_RE = re.compile(r"https://mp\.weixin\.qq\.com/s/[A-Za-z0-9_-]+(?:\?[^\s)#\"]*)?")


def request_json(
    url: str,
    *,
    token: str = "",
    method: str = "GET",
    form: dict | None = None,
) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    payload = None
    if form is not None:
        payload = urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
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


def load_ingest_helpers(script_path: Path):
    spec = importlib.util.spec_from_file_location("codex_ingest_werss_api", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load ingest helpers: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_seed_config(path: Path) -> dict:
    if not path.exists():
        return {"items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"items": []}
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data
    if isinstance(data, list):
        return {"items": data}
    return {"items": []}


def save_seed_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"processed": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"processed": []}
    processed = data.get("processed") if isinstance(data, dict) else None
    if isinstance(processed, list):
        return {"processed": [item for item in processed if isinstance(item, dict)]}
    return {"processed": []}


def save_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def processed_urls(state: dict) -> set[str]:
    urls: set[str] = set()
    for item in state.get("processed") or []:
        url = str(item.get("article_url") or "").strip()
        if url:
            urls.add(url)
    return urls


def extract_urls(text: str) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for match in MP_URL_RE.finditer(text or ""):
        url = match.group(0).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append(url)
    return rows


def scan_link_files(root: Path) -> list[dict]:
    rows: list[dict] = []
    seen_urls: set[str] = set()
    if not root.exists():
        return rows
    for mp_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        link_files = sorted(
            [path for pattern in ("*.md", "*.txt") for path in mp_dir.glob(pattern)],
            key=lambda item: (item.stat().st_mtime, str(item)),
        )
        for path in link_files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for url in extract_urls(text):
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                rows.append(
                    {
                        "mp_name": mp_dir.name,
                        "path": path,
                        "article_url": url,
                    }
                )
    return rows


def upsert_seed_items(config: dict, rows: list[dict]) -> dict:
    items = list(config.get("items") or [])
    by_name = {str(item.get("mp_name") or ""): item for item in items if isinstance(item, dict)}
    for row in rows:
        name = row["mp_name"]
        current = by_name.get(name, {})
        current["mp_name"] = name
        current["category"] = str(current.get("category") or "游资号")
        current["article_url"] = row["article_url"]
        current["end_page"] = int(current.get("end_page") or 8)
        by_name[name] = current
    return {"items": sorted(by_name.values(), key=lambda item: item.get("mp_name", ""))}


def import_one(
    *,
    base_url: str,
    token: str,
    row: dict,
    ingest,
    dry_run: bool,
    download_images: bool,
    enable_ocr: bool,
) -> dict:
    article_url = row["article_url"]
    source_name = row["mp_name"]
    response = request_json(
        f"{base_url.rstrip('/')}/mps/by_article?url={quote(article_url, safe='')}",
        token=token,
        method="POST",
    )
    data = response.get("data") or {}
    fetch_error = str(data.get("fetch_error") or "").strip()
    content = str(data.get("content") or "").strip()
    if fetch_error:
        raise ValueError(f"by_article fetch failed: {fetch_error}")
    if not content:
        raise ValueError("by_article returned empty content")
    article_id = str(data.get("id") or ingest.sha1_text(article_url)[:16]).strip()
    publish_time = data.get("publish_time") or int(time.time())
    title = str(data.get("title") or source_name or "untitled").strip()
    payload = {
        "id": article_id,
        "mp_id": str(data.get("mp_id") or "").strip(),
        "mp_name": source_name,
        "title": title,
        "url": article_url,
        "publish_time": publish_time,
        "description": str(data.get("description") or "").strip(),
        "content": content,
        "content_html": content,
    }
    date_text = ingest.unix_to_date_text(publish_time)
    short_hash = ingest.sha1_text(article_id or article_url or title)[:12]
    md_path = RAW_MP_ROOT / "游资号" / ingest.sanitize_filename(source_name) / f"{date_text}_{short_hash}.md"
    written_md, written_html = ingest.write_article_files(
        md_path,
        payload,
        source_name=source_name,
        download_images=download_images,
        enable_ocr=enable_ocr,
        dry_run=dry_run,
    )
    return {
        "mp_name": source_name,
        "article_url": article_url,
        "title": title,
        "mp_id": payload["mp_id"],
        "md_path": str(written_md),
        "html_path": str(written_html),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--username", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASS)
    parser.add_argument("--links-root", default=str(RAW_LINK_ROOT))
    parser.add_argument("--seeds-config", default=str(DEFAULT_SEEDS))
    parser.add_argument("--audit-output", default=str(DEFAULT_AUDIT))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-image-download", action="store_true")
    parser.add_argument("--skip-ocr", action="store_true")
    args = parser.parse_args()

    ingest = load_ingest_helpers(INGEST_SCRIPT)
    enable_ocr = (not args.skip_ocr) and bool(ingest.can_enable_ocr())
    download_images = not args.skip_image_download
    token = login(args.base_url, args.username, args.password)
    link_rows = scan_link_files(Path(args.links_root))
    state_path = Path(args.state)
    state = load_state(state_path)
    processed = processed_urls(state)
    pending_rows = [row for row in link_rows if row["article_url"] not in processed]

    seeds_path = Path(args.seeds_config)
    config = upsert_seed_items(load_seed_config(seeds_path), link_rows)
    if not args.dry_run:
        save_seed_config(seeds_path, config)

    imported = []
    failed = []
    for row in pending_rows:
        try:
            result = import_one(
                    base_url=args.base_url,
                    token=token,
                    row=row,
                    ingest=ingest,
                    dry_run=args.dry_run,
                    download_images=download_images,
                    enable_ocr=enable_ocr,
                )
            imported.append(result)
            if not args.dry_run:
                state["processed"] = [
                    item
                    for item in state.get("processed") or []
                    if str(item.get("article_url") or "").strip() != row["article_url"]
                ]
                state["processed"].append(
                    {
                        "article_url": row["article_url"],
                        "mp_name": row["mp_name"],
                        "link_path": str(row["path"]),
                        "title": result["title"],
                        "mp_id": result["mp_id"],
                        "md_path": result["md_path"],
                        "html_path": result["html_path"],
                        "imported_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                    }
                )
        except Exception as exc:
            failed.append(
                {
                    "mp_name": row["mp_name"],
                    "link_path": str(row["path"]),
                    "article_url": row["article_url"],
                    "error": str(exc),
                }
            )
    if not args.dry_run:
        save_state(state_path, state)

    result = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "links_root": str(Path(args.links_root)),
        "seeds_config": str(seeds_path),
        "state_path": str(state_path),
        "imported": imported,
        "failed": failed,
        "summary": {
            "links": len(link_rows),
            "pending": len(pending_rows),
            "skipped_processed": len(link_rows) - len(pending_rows),
            "imported": len(imported),
            "failed": len(failed),
        },
    }
    audit_path = Path(args.audit_output)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
