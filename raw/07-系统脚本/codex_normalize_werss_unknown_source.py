import argparse
import re
import shutil
import time
from pathlib import Path

import codex_ingest_werss_api as werss

ROOT = Path(__file__).resolve().parents[2]


def replace_frontmatter_value(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(^ {0,0}{re.escape(key)}:\s*)(.*)$".replace(" {0,0}", ""), flags=re.M)
    if pattern.search(text):
        return pattern.sub(rf"\1{werss.yaml_quote(value)}", text, count=1)
    if text.startswith("---\n"):
        return text.replace("---\n", f"---\n{key}: {werss.yaml_quote(value)}\n", 1)
    return text


def replace_summary_line(text: str, prefix: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}.*$", flags=re.M)
    replacement = f"{prefix}{value}"
    if pattern.search(text):
        return pattern.sub(lambda _: replacement, text, count=1)
    return text


def move_bundle(old_md: Path, new_md: Path) -> None:
    old_html = old_md.with_suffix(".html")
    new_html = new_md.with_suffix(".html")
    old_assets = old_md.parent / f"{old_md.stem}_assets"
    new_assets = new_md.parent / f"{new_md.stem}_assets"

    new_md.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(5):
        try:
            if new_md.exists():
                new_md.unlink()
            shutil.move(str(old_md), str(new_md))
            break
        except PermissionError:
            time.sleep(0.6)
    else:
        raise PermissionError(f"move failed: {old_md}")

    if old_html.exists():
        for _ in range(5):
            try:
                if new_html.exists():
                    new_html.unlink()
                shutil.move(str(old_html), str(new_html))
                break
            except PermissionError:
                time.sleep(0.6)

    if old_assets.exists() and old_assets.is_dir():
        for _ in range(5):
            try:
                if new_assets.exists() and new_assets.is_dir():
                    shutil.rmtree(new_assets, ignore_errors=True)
                shutil.move(str(old_assets), str(new_assets))
                break
            except PermissionError:
                time.sleep(0.6)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--unknown-root",
        default=str(ROOT / "raw" / "05-研报新闻" / "公众号" / "游资号" / "未知来源"),
    )
    args = parser.parse_args()

    unknown_root = Path(args.unknown_root)
    if not unknown_root.exists():
        print({"moved": 0, "skipped": 0, "unresolved": 0, "reason": "unknown_root_missing"})
        return 0

    client = werss.WeRSSClient(
        base_url=werss.DEFAULT_BASE_URL,
        username=werss.DEFAULT_USERNAME,
        password=werss.DEFAULT_PASSWORD,
    )
    mps = client.fetch_all_mps(limit=100)
    articles = client.fetch_all_articles(limit=100, has_content=None)
    mp_name_by_id = {
        str(item.get("id") or ""): (item.get("mp_name") or "").strip()
        for item in mps
        if (item.get("id") or "") and (item.get("mp_name") or "").strip()
    }
    article_by_url = {
        werss.canonicalize_mp_url(item.get("url", "")): item
        for item in articles
        if werss.canonicalize_mp_url(item.get("url", ""))
    }

    moved = 0
    skipped = 0
    unresolved = 0

    for md_path in sorted(unknown_root.glob("*.md")):
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        meta, body = werss.parse_frontmatter(text)
        title = meta.get("title") or werss.infer_title(md_path, meta, body)
        created = meta.get("created") or werss.infer_created_date(md_path, meta, body)
        mp_id = (meta.get("mp_id") or "").strip().strip('"').strip("'")
        source_url = werss.canonicalize_mp_url(meta.get("source_url", "") or werss.extract_source_url(body))

        source_name = mp_name_by_id.get(mp_id, "")
        if not source_name and source_url:
            hit = article_by_url.get(source_url)
            source_name = (hit or {}).get("mp_name", "").strip()
        if not source_name or source_name == "未知来源":
            unresolved += 1
            print(f"unresolved: {md_path.name}")
            continue

        target_dir = unknown_root.parent / werss.sanitize_filename(source_name)
        target_path = target_dir / md_path.name
        target_html = target_path.with_suffix(".html")

        updated = text
        updated = replace_frontmatter_value(updated, "source", source_name)
        updated = replace_frontmatter_value(updated, "created", created)
        updated = replace_frontmatter_value(updated, "title", title)
        updated = replace_summary_line(updated, "- 来源：", source_name)
        updated = replace_summary_line(updated, "- RAW HTML：", str(target_html))

        if target_path.resolve() == md_path.resolve():
            md_path.write_text(updated, encoding="utf-8")
            skipped += 1
            continue

        md_path.write_text(updated, encoding="utf-8")
        move_bundle(md_path, target_path)
        moved += 1
        print(f"moved: {md_path.name} -> {source_name}")

    print({"moved": moved, "skipped": skipped, "unresolved": unresolved, "remaining_unknown": len(list(unknown_root.glob('*.md')))})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
