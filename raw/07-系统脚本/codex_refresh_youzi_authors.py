import argparse
import importlib.util
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
INGEST_PATH = SCRIPT_DIR / "codex_ingest_werss_api.py"


def load_ingest_module():
    spec = importlib.util.spec_from_file_location("codex_ingest_werss_api", INGEST_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INGEST = load_ingest_module()
ROOT = INGEST.ROOT
RAW_ROOT = ROOT / "raw" / "05-研报新闻" / "公众号" / "游资号"
SYSTEM_DIR = ROOT / ".system"
DEFAULT_TARGETS = SYSTEM_DIR / "youzi-author-refresh-targets.json"
DEFAULT_AUDIT_JSON = SYSTEM_DIR / "youzi-author-refresh-audit.json"
DEFAULT_AUDIT_MD = SYSTEM_DIR / "youzi-author-refresh-audit.md"
DEFAULT_LOG = SYSTEM_DIR / "logs" / "youzi-author-refresh.log"
DEFAULT_REGISTRY = SYSTEM_DIR / "ingest-registry.jsonl"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str, log_path: Path) -> None:
    line = f"[{now_text()}] {message}"
    try:
        print(line)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe = line.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def rel_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def load_targets(path: Path, include_sources: list[str]) -> list[str]:
    targets: list[str] = []
    payload = load_json(path, {})
    if isinstance(payload, dict):
        for item in payload.get("sources", []):
            if item:
                targets.append(str(item).strip())
    targets.extend(source for source in include_sources if source)
    deduped = []
    seen = set()
    for item in targets:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def discover_source_dir(source_name: str) -> Path | None:
    path = RAW_ROOT / source_name
    if path.exists():
        return path
    for item in RAW_ROOT.iterdir():
        if item.is_dir() and item.name == source_name:
            return item
    return None


def load_source_context(source_dir: Path) -> dict:
    existing_by_url: dict[str, Path] = {}
    existing_article_ids: set[str] = set()
    mp_ids: Counter = Counter()
    current_files = sorted(source_dir.glob("*.md"))
    for path in current_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        meta, body = INGEST.parse_frontmatter(text)
        source_url = INGEST.canonicalize_mp_url(meta.get("source_url", "") or INGEST.extract_source_url(body))
        if source_url:
            existing_by_url[source_url] = path
        article_id = str(meta.get("werss_article_id", "")).strip()
        if article_id:
            existing_article_ids.add(article_id)
        mp_id = str(meta.get("mp_id", "")).strip()
        if mp_id:
            mp_ids[mp_id] += 1
    return {
        "raw_count": len(current_files),
        "existing_by_url": existing_by_url,
        "existing_source_urls": sorted(existing_by_url),
        "existing_article_ids": existing_article_ids,
        "primary_mp_id": mp_ids.most_common(1)[0][0] if mp_ids else "",
    }


def fetch_articles_by_mp(client, mp_id: str, limit: int = 100) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    total = None
    while True:
        response = client._request_json("/articles", query={"offset": offset, "limit": limit, "mp_id": mp_id})
        data = response.get("data") or {}
        batch = list(data.get("list") or [])
        rows.extend(batch)
        total = data.get("total", total)
        if not batch or (total is not None and len(rows) >= int(total)):
            break
        offset += limit
    return rows


def fetch_seed_only_details(client, article_ids: set[str]) -> list[dict]:
    rows: list[dict] = []
    for article_id in sorted(article_ids):
        try:
            detail = client.fetch_article_detail(article_id)
        except Exception:
            continue
        if detail:
            rows.append(detail)
    return rows


def fetch_articles_by_url(client, source_urls: list[str], source_name: str) -> list[dict]:
    rows: list[dict] = []
    for source_url in source_urls:
        try:
            response = client._request_json(
                "/mps/by_article",
                query={"url": source_url},
                data={},
            )
        except Exception:
            continue
        data = response.get("data") or {}
        if str(data.get("fetch_error") or "").strip():
            continue
        content = str(data.get("content") or "").strip()
        if not content:
            continue
        publish_time = data.get("publish_time") or int(datetime.now().timestamp())
        article_id = str(data.get("id") or INGEST.sha1_text(source_url)[:16]).strip()
        rows.append(
            {
                "id": article_id,
                "mp_id": str(data.get("mp_id") or "").strip(),
                "mp_name": source_name,
                "title": str(data.get("title") or source_name or "untitled").strip(),
                "url": source_url,
                "publish_time": publish_time,
                "description": str(data.get("description") or "").strip(),
                "content": content,
                "content_html": content,
            }
        )
    return rows


def build_target_path(source_dir: Path, article: dict) -> Path:
    date_text = INGEST.unix_to_date_text(article.get("publish_time") or article.get("create_time"))
    short_hash = INGEST.sha1_text(article.get("id") or article.get("url") or article.get("title") or date_text)[:12]
    return source_dir / f"{date_text}_{short_hash}.md"


def write_audit_markdown(path: Path, audit: dict) -> None:
    lines = [
        "# Youzi Author Refresh Audit",
        "",
        f"- Generated: {audit['generated_at']}",
        f"- Sources: {audit['summary']['sources']}",
        f"- Articles touched: {audit['summary']['touched']}",
        f"- Rewritten existing: {audit['summary']['rewritten_existing']}",
        f"- Created new: {audit['summary']['created_new']}",
        f"- No WeRSS history: {audit['summary']['no_werss_history']}",
        "",
        "## Per Source",
        "",
        "| Source | mp_id | RAW before | WeRSS total | Rewritten | Created | Fallback | Status |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in audit["sources"]:
        lines.append(
            f"| {item['source']} | {item['mp_id'] or '-'} | {item['raw_before']} | {item['werss_total']} | "
            f"{item['rewritten_existing']} | {item['created_new']} | {item['fallback_refreshed']} | {item['status']} |"
        )
    lines += [
        "",
        "## Missing WeRSS History",
        "",
    ]
    missing = [item for item in audit["sources"] if item["status"] in {"no_werss_history", "missing_mp_id"}]
    if not missing:
        lines.append("None")
    else:
        lines.extend(["| Source | mp_id | Note |", "|---|---|---|"])
        for item in missing:
            lines.append(f"| {item['source']} | {item['mp_id'] or '-'} | {item['note']} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def refresh_source(
    client,
    source_dir: Path,
    *,
    registry_path: Path,
    log_path: Path,
    download_images: bool = False,
    enable_ocr: bool = False,
    dry_run: bool,
) -> dict:
    source_name = source_dir.name
    context = load_source_context(source_dir)
    mp_id = context["primary_mp_id"]
    rows = fetch_articles_by_mp(client, mp_id) if mp_id else []
    seed_rows = []
    url_rows = []
    status = "ok"
    note = ""
    if not mp_id:
        status = "missing_mp_id"
        note = "no mp_id found in existing RAW"
    elif not rows:
        seed_rows = fetch_seed_only_details(client, context["existing_article_ids"])
        if seed_rows:
            status = "seed_only"
            note = "mp_id has no article list, refreshed only existing seeded articles"
        else:
            url_rows = fetch_articles_by_url(client, context["existing_source_urls"], source_name)
            if url_rows:
                status = "source_url_only"
                note = "mp_id has no article list, refreshed existing source_url articles via by_article"
            else:
                status = "no_werss_history"
                note = "mp_id exists but WeRSS articles list is empty"

    candidates = rows or seed_rows or url_rows
    rewritten_existing = 0
    created_new = 0
    touched_rows: list[dict] = []
    matched_urls: set[str] = set()
    fallback_refreshed = len(seed_rows) + len(url_rows)

    for summary in sorted(candidates, key=lambda item: item.get("publish_time") or item.get("create_time") or 0):
        article = INGEST.merge_article_payload(summary, client.fetch_article_detail(summary["id"])) if rows else summary
        source_url = INGEST.canonicalize_mp_url(article.get("url", ""))
        target_path = context["existing_by_url"].get(source_url) if source_url else None
        if target_path is None:
            target_path = build_target_path(source_dir, article)
        existed = target_path.exists()
        INGEST.write_article_files(
            target_path,
            article,
            source_name=source_name,
            download_images=download_images,
            enable_ocr=enable_ocr,
            dry_run=dry_run,
        )
        if existed:
            rewritten_existing += 1
        else:
            created_new += 1
        if source_url:
            matched_urls.add(source_url)
        touched_rows.append(
            {
                "path": str(target_path),
                "title": article.get("title", ""),
                "source_url": source_url,
                "article_id": article.get("id", ""),
                "action": "rewrite_existing" if existed else "create_new",
            }
        )
        if not dry_run:
            INGEST.append_jsonl(
                registry_path,
                {
                    "captured_at": now_text(),
                    "action": "author_refresh",
                    "source": source_name,
                    "source_url": source_url,
                    "article_id": article.get("id", ""),
                    "md_path": str(target_path),
                    "html_path": str(target_path.with_suffix(".html")),
                    "capture_pipeline": "werss_api",
                },
            )
    stale_raw = []
    for source_url, path in sorted(context["existing_by_url"].items()):
        if matched_urls and source_url not in matched_urls:
            stale_raw.append(str(path))
    log(
        f"author refresh {source_name}: werss_total={len(rows)} rewritten={rewritten_existing} created={created_new} fallback={fallback_refreshed} status={status}",
        log_path,
    )
    return {
        "source": source_name,
        "mp_id": mp_id,
        "raw_before": context["raw_count"],
        "werss_total": len(rows),
        "rewritten_existing": rewritten_existing,
        "created_new": created_new,
        "fallback_refreshed": fallback_refreshed,
        "status": status,
        "note": note,
        "stale_raw": stale_raw,
        "touched_rows": touched_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets-config", default=str(DEFAULT_TARGETS))
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--audit-json", default=str(DEFAULT_AUDIT_JSON))
    parser.add_argument("--audit-md", default=str(DEFAULT_AUDIT_MD))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--with-image-download", action="store_true")
    parser.add_argument("--with-ocr", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    targets = load_targets(Path(args.targets_config), args.source)
    if not targets:
        raise SystemExit("no target sources configured")

    client = INGEST.WeRSSClient(
        base_url=INGEST.DEFAULT_BASE_URL,
        username=INGEST.DEFAULT_USERNAME,
        password=INGEST.DEFAULT_PASSWORD,
    )
    download_images = bool(args.with_image_download)
    enable_ocr = bool(args.with_ocr) and INGEST.can_enable_ocr()
    log_path = Path(args.log)
    registry_path = Path(args.registry)
    source_rows: list[dict] = []

    for target in targets:
        source_dir = discover_source_dir(target)
        if source_dir is None:
            row = {
                "source": target,
                "mp_id": "",
                "raw_before": 0,
                "werss_total": 0,
                "rewritten_existing": 0,
                "created_new": 0,
                "fallback_refreshed": 0,
                "status": "source_dir_missing",
                "note": "source directory not found under raw/05-研报新闻/公众号/游资号",
                "stale_raw": [],
                "touched_rows": [],
            }
            source_rows.append(row)
            log(f"author refresh skip missing dir: {target}", log_path)
            continue
        source_rows.append(
            refresh_source(
                client,
                source_dir,
                registry_path=registry_path,
                log_path=log_path,
                download_images=download_images,
                enable_ocr=enable_ocr,
                dry_run=args.dry_run,
            )
        )

    audit = {
        "generated_at": now_text(),
        "summary": {
            "sources": len(source_rows),
            "touched": sum(len(item["touched_rows"]) for item in source_rows),
            "rewritten_existing": sum(item["rewritten_existing"] for item in source_rows),
            "created_new": sum(item["created_new"] for item in source_rows),
            "no_werss_history": sum(1 for item in source_rows if item["status"] in {"no_werss_history", "missing_mp_id"}),
        },
        "sources": source_rows,
    }
    if not args.dry_run:
        save_json(Path(args.audit_json), audit)
        write_audit_markdown(Path(args.audit_md), audit)
    payload = json.dumps(audit, ensure_ascii=False, indent=2)
    try:
        print(payload)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe = payload.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
