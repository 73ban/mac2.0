import argparse
import hashlib
import json
import re
import sys
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
SYSTEM_DIR = ROOT / ".system"
RAW_NEWS_DIR = ROOT / "raw" / "05-研报新闻" / "公众号"
DEFAULT_CONFIG = SYSTEM_DIR / "werss-feeds.json"
DEFAULT_STATE = SYSTEM_DIR / "werss-feed-state.json"
DEFAULT_LOG = SYSTEM_DIR / "logs" / "werss-ingest.log"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36 CodexWeRSS/1.0"
)

NOISE_PATTERNS = [
    r"微信扫一扫关注该公众号",
    r"继续滑动看下一个",
    r"阅读原文",
    r"喜欢此内容的人还喜欢",
    r"人划线",
    r"点击蓝字关注",
    r"扫码关注我们",
    r"长按识别二维码",
    r"预览时标签不可点",
]


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str, log_path: Path) -> None:
    text = f"[{now_text()}] {message}"
    print(text)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")


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


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest().upper()


def sanitize_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r"[<>:\"/\\|?*\r\n\t]", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or "untitled")[:max_len]


def fetch_text(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        data = resp.read()
    try:
        return data.decode(charset, errors="ignore")
    except Exception:
        return data.decode("utf-8", errors="ignore")


def strip_cdata(text: str) -> str:
    text = text or ""
    if text.startswith("<![CDATA[") and text.endswith("]]>"):
        return text[9:-3]
    return text


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def first_child_text(node: ET.Element, names: set[str]) -> str:
    for child in list(node):
        if local_name(child.tag) in names:
            return strip_cdata(child.text or "").strip()
    return ""


def find_atom_link(node: ET.Element) -> str:
    for child in list(node):
        if local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        if href:
            return href
        text = strip_cdata(child.text or "").strip()
        if text:
            return text
    return ""


def parse_feed_items(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items: list[dict] = []
    item_nodes = root.findall(".//item")
    if not item_nodes:
        item_nodes = root.findall(".//{*}entry")
    for node in item_nodes:
        title = first_child_text(node, {"title"})
        guid = first_child_text(node, {"guid", "id"})
        link = first_child_text(node, {"link"})
        if not link:
            link = find_atom_link(node)
        pub_date = first_child_text(node, {"pubDate", "published", "updated", "date"})
        description = first_child_text(node, {"description", "summary"})
        content_html = first_child_text(node, {"encoded", "content"})
        author = first_child_text(node, {"author", "creator"})
        items.append(
            {
                "title": title,
                "guid": guid or link or title,
                "link": link,
                "pub_date": pub_date,
                "description": description,
                "content_html": content_html,
                "author": author,
            }
        )
    return items


def parse_publish_date(text: str) -> datetime:
    text = (text or "").strip()
    if not text:
        return datetime.now()
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is not None:
            return dt.astimezone().replace(tzinfo=None)
        return dt
    except Exception:
        pass
    for candidate in (
        text.replace("Z", "+00:00"),
        text.replace("/", "-"),
    ):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is not None:
                return dt.astimezone(UTC).replace(tzinfo=None)
            return dt
        except Exception:
            continue
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        return datetime.fromisoformat(match.group(1))
    return datetime.now()


def extract_first_mp_link(text: str) -> str:
    match = re.search(r"https?://mp\.weixin\.qq\.com/[^\s\"'<>]+", text or "", flags=re.I)
    return match.group(0) if match else ""


def find_start_tag(html: str, matcher: str) -> tuple[int, int, str] | None:
    pattern = re.compile(matcher, flags=re.I)
    match = pattern.search(html)
    if not match:
        return None
    tag_match = re.match(r"<([a-z0-9]+)\b", match.group(0), flags=re.I)
    if not tag_match:
        return None
    return match.start(), match.end(), tag_match.group(1).lower()


def extract_balanced_element(html: str, start: int, tag_name: str) -> str:
    token = re.compile(rf"</?{tag_name}\b[^>]*>", flags=re.I)
    depth = 0
    started = False
    for match in token.finditer(html, pos=start):
        token_text = match.group(0)
        is_close = token_text.startswith("</")
        is_self_close = token_text.endswith("/>")
        if not started:
            started = True
            depth = 1
            continue
        if is_close:
            depth -= 1
            if depth == 0:
                return html[start : match.end()]
        elif not is_self_close:
            depth += 1
    return html[start:]


def extract_wechat_body(html: str) -> str:
    for matcher in (
        r"<div[^>]+id=[\"']js_content[\"'][^>]*>",
        r"<div[^>]+class=[\"'][^\"']*rich_media_content[^\"']*[\"'][^>]*>",
        r"<section[^>]+class=[\"'][^\"']*rich_media_content[^\"']*[\"'][^>]*>",
    ):
        found = find_start_tag(html, matcher)
        if not found:
            continue
        start, _, tag_name = found
        return extract_balanced_element(html, start, tag_name)
    return ""


def html_to_markdown(html: str) -> str:
    text = html or ""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", "", text, flags=re.I | re.S)
    text = re.sub(r"<mp-common-[^>]+>.*?</mp-common-[^>]+>", "", text, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.I)
    text = re.sub(r"</div\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<div[^>]*>", "", text, flags=re.I)
    text = re.sub(r"</section\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<section[^>]*>", "", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
    text = re.sub(r"</li\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</?(ul|ol)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<h([1-6])[^>]*>", lambda m: "\n" + ("#" * int(m.group(1))) + " ", text, flags=re.I)
    text = re.sub(r"</h[1-6]\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<blockquote[^>]*>", "\n> ", text, flags=re.I)
    text = re.sub(r"</blockquote\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<img[^>]*?>", "\n[图片]\n", text, flags=re.I)
    text = re.sub(
        r"<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        lambda m: f"{re.sub(r'<[^>]+>', '', m.group(2)).strip()} ({m.group(1)})".strip(),
        text,
        flags=re.I | re.S,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.I)
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def pick_source_url(item: dict) -> str:
    content = "\n".join([item.get("content_html", ""), item.get("description", "")])
    mp_link = extract_first_mp_link(content)
    if mp_link:
        return mp_link
    return item.get("link", "").strip()


def build_fallback_html(title: str, body_html: str) -> str:
    return (
        "<html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body>{body_html}</body></html>"
    )


def classify_target_dir(feed: dict) -> Path:
    category = feed.get("category", "游资号").strip() or "游资号"
    source_dir = feed.get("subdir", feed.get("name", "未命名来源")).strip() or "未命名来源"
    return RAW_NEWS_DIR / category / source_dir


def raw_html_dir(feed: dict) -> Path:
    source_dir = feed.get("subdir", feed.get("name", "未命名来源")).strip() or "未命名来源"
    return RAW_NEWS_DIR / source_dir


def write_article(feed: dict, item: dict, state: dict, log_path: Path, dry_run: bool = False) -> bool:
    source_url = pick_source_url(item)
    unique_seed = "||".join(
        [
            feed.get("name", ""),
            item.get("guid", ""),
            source_url,
            item.get("title", ""),
            item.get("pub_date", ""),
        ]
    )
    unique_id = sha1_text(unique_seed)
    if unique_id in state["processed"]:
        return False

    published = parse_publish_date(item.get("pub_date", ""))
    date_text = published.strftime("%Y-%m-%d")
    title = sanitize_filename(item.get("title") or f"{feed.get('name', '未命名来源')}-{date_text}")
    source_hash = sha1_text(source_url or unique_id)[:12]
    source_name = feed.get("name", "未命名来源").strip() or "未命名来源"
    feed_url = feed.get("rss_url", "")

    article_html = ""
    article_body = ""
    if source_url.startswith("http"):
        try:
            article_html = fetch_text(source_url, timeout=40)
            article_body = extract_wechat_body(article_html)
        except (HTTPError, URLError, TimeoutError) as exc:
            log(f"{source_name} 抓取原文失败: {source_url} | {exc}", log_path)
        except Exception as exc:
            log(f"{source_name} 抓取原文异常: {source_url} | {exc}", log_path)

    content_html = article_body or item.get("content_html", "") or item.get("description", "")
    if not content_html.strip():
        content_html = f"<p>{item.get('description', '')}</p>"
    markdown_body = html_to_markdown(content_html)
    if len(markdown_body) < 30 and article_html:
        markdown_body = html_to_markdown(article_html)
    if len(markdown_body) < 20:
        markdown_body = (item.get("description", "") or item.get("title", "")).strip()

    html_payload = article_html or build_fallback_html(title, content_html)
    html_dir = raw_html_dir(feed)
    md_dir = classify_target_dir(feed)
    html_path = html_dir / f"{date_text}_{source_hash}.html"
    md_path = md_dir / f"{date_text}_{title}_{source_hash}.md"

    frontmatter = [
        "---",
        f"title: {title}",
        f"created: {date_text}",
        f"updated: {datetime.now().strftime('%Y-%m-%d')}",
        "type: 公众号原文",
        f"source: {source_name}",
        f"source_url: {source_url}",
        f"feed_url: {feed_url}",
        f"source_hash: {sha1_text(html_payload)}",
        "preferred_ingestor: codex",
        "ingested_by: codex",
        "capture_pipeline: werss_rss",
        "---",
        "",
        f"# {title}",
        "",
        f"- 来源：{source_name}",
        f"- 原链接：{source_url}",
        f"- 订阅源：{feed_url}",
        f"- RAW HTML：{html_path}",
        f"- 内容hash：{sha1_text(html_payload)}",
        f"- 分类：{feed.get('category', '游资号')}",
        "",
        "---",
        "",
        markdown_body.strip(),
        "",
    ]
    md_text = "\n".join(frontmatter)

    if not dry_run:
        html_dir.mkdir(parents=True, exist_ok=True)
        md_dir.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html_payload, encoding="utf-8")
        md_path.write_text(md_text, encoding="utf-8")

        append_jsonl(
            SYSTEM_DIR / "werss-ingest-registry.jsonl",
            {
                "captured_at": now_text(),
                "source": source_name,
                "source_url": source_url,
                "feed_url": feed_url,
                "title": title,
                "md_path": str(md_path),
                "html_path": str(html_path),
                "capture_pipeline": "werss_rss",
            },
        )

    state["processed"][unique_id] = {
        "source": source_name,
        "source_url": source_url,
        "title": title,
        "published_at": date_text,
        "md_path": str(md_path),
        "captured_at": now_text(),
    }
    log(f"{source_name} 入库: {title}", log_path)
    return True


def normalize_config(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("feeds"), list):
        return data["feeds"]
    return []


def run_once(config_path: Path, state_path: Path, log_path: Path, feed_name: str | None, dry_run: bool) -> int:
    config = normalize_config(load_json(config_path, []))
    if not config:
        log(f"未找到可用订阅配置: {config_path}", log_path)
        return 0

    state = load_json(state_path, {"processed": {}})
    state.setdefault("processed", {})
    total_new = 0

    for feed in config:
        if not isinstance(feed, dict):
            continue
        name = (feed.get("name") or "").strip()
        rss_url = (feed.get("rss_url") or "").strip()
        enabled = feed.get("enabled", True)
        if not enabled or not name or not rss_url:
            continue
        if feed_name and name != feed_name:
            continue
        try:
            xml_text = fetch_text(rss_url, timeout=30)
            items = parse_feed_items(xml_text)
            if not items:
                log(f"{name} RSS 无文章: {rss_url}", log_path)
                continue
            feed_new = 0
            for item in reversed(items):
                if write_article(feed, item, state, log_path, dry_run=dry_run):
                    feed_new += 1
                    total_new += 1
            log(f"{name} 扫描完成, 新增 {feed_new} 篇", log_path)
        except ET.ParseError as exc:
            log(f"{name} RSS 解析失败: {exc}", log_path)
        except (HTTPError, URLError, TimeoutError) as exc:
            log(f"{name} RSS 抓取失败: {rss_url} | {exc}", log_path)
        except Exception as exc:
            log(f"{name} 扫描异常: {rss_url} | {exc}", log_path)

    if not dry_run:
        save_json(state_path, state)
    return total_new


def self_test() -> int:
    sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <item>
      <title>测试文章</title>
      <link>https://mp.weixin.qq.com/s/test</link>
      <guid>abc</guid>
      <pubDate>Sat, 20 Jun 2026 10:00:00 +0800</pubDate>
      <description><![CDATA[<p>摘要</p>]]></description>
      <content:encoded><![CDATA[<div id="js_content"><p>第一段</p><p>第二段</p></div>]]></content:encoded>
    </item>
  </channel>
</rss>
"""
    items = parse_feed_items(sample_rss)
    assert len(items) == 1
    assert items[0]["title"] == "测试文章"
    body = extract_wechat_body("<div id='js_content'><p>正文</p><div><p>更多</p></div></div>")
    assert "正文" in body and "更多" in body
    md = html_to_markdown("<div id='js_content'><h2>标题</h2><p>正文</p><ul><li>A</li></ul></div>")
    assert "## 标题" in md and "- A" in md
    print("self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--feed")
    parser.add_argument("--seconds", type=int, default=900)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    config_path = Path(args.config)
    state_path = Path(args.state)
    log_path = Path(args.log)
    seconds = max(60, args.seconds)

    if args.once:
        total_new = run_once(config_path, state_path, log_path, args.feed, args.dry_run)
        print(json.dumps({"new_articles": total_new}, ensure_ascii=False))
        return 0

    while True:
        try:
            run_once(config_path, state_path, log_path, args.feed, args.dry_run)
        except Exception as exc:
            log(f"主循环异常: {exc}", log_path)
        time.sleep(seconds)


if __name__ == "__main__":
    sys.exit(main())
