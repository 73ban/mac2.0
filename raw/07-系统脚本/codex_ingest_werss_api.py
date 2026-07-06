from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import shutil
import sys
import time
try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone

    UTC = timezone.utc
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
SYSTEM_DIR = ROOT / ".system"
RAW_MP_DIR = ROOT / "raw" / "05-研报新闻" / "公众号"
DEFAULT_STATE = SYSTEM_DIR / "werss-api-state.json"
DEFAULT_LOG = SYSTEM_DIR / "logs" / "werss-api-ingest.log"
DEFAULT_AUDIT_JSON = SYSTEM_DIR / "werss-api-repair-audit.json"
DEFAULT_AUDIT_MD = SYSTEM_DIR / "werss-api-repair-audit.md"
DEFAULT_REGISTRY = SYSTEM_DIR / "werss-api-registry.jsonl"
SOURCE_CLASS_CONFIG = SYSTEM_DIR / "wechat-mp-source-classes.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8002/api/v1/wx"
DEFAULT_REPAIR_ROOT = RAW_MP_DIR / "游资号"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin@123"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36 CodexWeRSSAPI/1.0"
)

DROP_QUERY_KEYS = {
    "scene",
    "subscene",
    "sessionid",
    "clicktime",
    "enterid",
    "chksm",
    "from",
    "source",
    "share",
    "sharer_shareinfo",
    "sharer_shareinfo_first",
    "mpshare",
    "mpshare1",
    "mpshare2",
    "mpshare3",
    "wx_header",
    "exportkey",
    "acctmode",
}
NOISE_PATTERNS = [
    r"继续滑动看下一个",
    r"向上滑动看下一个",
    r"阅读原文",
    r"微信扫一扫关注该公众号",
    r"微信扫一扫可打开此内容",
    r"长按识别二维码",
    r"扫码关注我们",
    r"预览时标签不可点",
    r"使用完整服务",
    r"轻点两下取消赞",
    r"轻点两下取消在看",
]
BAD_HTML_SIGNALS = (
    "window.logs",
    "<script",
    "<style",
    "<html",
    "document.write",
    "var biz",
    "var nickname",
    "msg_cdn_url",
    "js_content",
    "rich_media_content",
    "profile_meta",
    "weui-media-box",
)
NOISE_EXACT_LINES = {
    "知道了",
    "取消",
    "允许",
    "轻触",
    "修改于",
    "分析",
    "视频",
    "小程序",
    "赞",
    "在看",
    "分享",
    "留言",
    "收藏",
    "听过",
    "×",
    "：",
}
OCR_ENGINE_NAME = "rapidocr_onnxruntime"
_OCR_ENGINE = None
_OCR_AVAILABLE = None
_STD_INSPECT = None


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str, log_path: Path) -> None:
    line = f"[{now_text()}] {message}"
    try:
        print(line)
    except UnicodeEncodeError:
        safe = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8",
            errors="replace",
        )
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


def load_source_profiles() -> dict:
    config = load_json(SOURCE_CLASS_CONFIG, {})
    if not isinstance(config, dict):
        config = {}
    return {
        "default": config.get("default") or {},
        "classes": config.get("classes") or {},
        "sources": config.get("sources") or {},
    }


def source_profile(source_name: str) -> dict:
    profiles = load_source_profiles()
    defaults = profiles.get("default") or {}
    source_class = (profiles.get("sources") or {}).get(source_name) or defaults.get("source_class") or "市场情绪"
    class_profile = (profiles.get("classes") or {}).get(source_class) or {}
    profile = dict(defaults)
    profile.update(class_profile)
    profile["source_class"] = source_class
    return profile


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest().upper()


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def yaml_quote(text: str) -> str:
    return json.dumps(str(text or ""), ensure_ascii=False)


def sanitize_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*\r\n\t]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or "untitled")[:max_len]


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def normalize_title(text: str) -> str:
    text = normalize_spaces(text)
    return text.lower()


def normalize_title_loose(text: str) -> str:
    text = normalize_title(text)
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)


def normalize_source_name(text: str) -> str:
    return normalize_spaces(text).lower()


def canonicalize_mp_url(url: str) -> str:
    text = unescape((url or "").strip())
    if not text.startswith(("http://", "https://")):
        return text
    parts = urlsplit(text)
    path = re.sub(r"/{2,}", "/", parts.path or "/").rstrip("/") or "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in DROP_QUERY_KEYS
    ]
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def unix_to_date_text(value) -> str:
    if value in (None, ""):
        return datetime.now().strftime("%Y-%m-%d")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(int(value), UTC).astimezone().strftime("%Y-%m-%d")
    text = str(value).strip()
    for candidate in (
        text,
        text.replace("Z", "+00:00"),
        text.replace("/", "-"),
    ):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is not None:
                dt = dt.astimezone(UTC).replace(tzinfo=None)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            flush_audit()
            continue
    match = re.search(r"(\d{4})[-./](\d{2})[-./](\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return datetime.now().strftime("%Y-%m-%d")


def extract_source_url(text: str) -> str:
    match = re.search(r"https?://mp\.weixin\.qq\.com/[^\s<>)\"']+", text or "", flags=re.I)
    return canonicalize_mp_url(match.group(0)) if match else ""


def parse_frontmatter(text: str) -> tuple[dict, str]:
    raw = text.lstrip("\ufeff\r\n")
    if not raw.startswith("---"):
        return {}, raw
    lines = raw.splitlines()
    meta: dict[str, str] = {}
    end_index = None
    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == "---":
            end_index = index
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    if end_index is None:
        return {}, raw
    body = "\n".join(lines[end_index + 1 :]).lstrip()
    return meta, body


def remove_markdown_artifacts(text: str) -> str:
    text = re.sub(r"^#.*$", "", text, flags=re.M)
    text = re.sub(r"^-\s+.*$", "", text, flags=re.M)
    text = re.sub(r"`{1,3}", "", text)
    return normalize_spaces(text)


def can_enable_ocr() -> bool:
    global _OCR_AVAILABLE
    if _OCR_AVAILABLE is not None:
        return _OCR_AVAILABLE
    try:
        safe_import_rapidocr()
    except Exception:
        _OCR_AVAILABLE = False
    else:
        _OCR_AVAILABLE = True
    return _OCR_AVAILABLE


def get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    if not can_enable_ocr():
        return None
    RapidOCR = safe_import_rapidocr()

    _OCR_ENGINE = RapidOCR()
    return _OCR_ENGINE


def safe_import_rapidocr():
    global _STD_INSPECT
    cwd = str(Path.cwd())
    removed: list[tuple[int, str]] = []
    for index in range(len(sys.path) - 1, -1, -1):
        item = sys.path[index]
        normalized = str(Path(item or ".").resolve())
        if item == "" or normalized == cwd:
            removed.append((index, item))
            sys.path.pop(index)
    original_inspect = sys.modules.get("inspect")
    try:
        if _STD_INSPECT is None:
            sys.modules.pop("inspect", None)
            _STD_INSPECT = importlib.import_module("inspect")
        sys.modules["inspect"] = _STD_INSPECT
        from rapidocr_onnxruntime import RapidOCR
    finally:
        if original_inspect is not None:
            sys.modules["inspect"] = original_inspect
        elif _STD_INSPECT is not None:
            sys.modules["inspect"] = _STD_INSPECT
        for index, item in sorted(removed, key=lambda pair: pair[0]):
            sys.path.insert(index, item)
    return RapidOCR


def guess_image_extension(url: str, content_type: str = "") -> str:
    lowered = (content_type or "").lower()
    if "png" in lowered:
        return ".png"
    if "webp" in lowered:
        return ".webp"
    if "gif" in lowered:
        return ".gif"
    if "bmp" in lowered:
        return ".bmp"
    if "jpeg" in lowered or "jpg" in lowered:
        return ".jpg"
    match = re.search(r"\.([a-zA-Z0-9]{2,5})(?:$|[?#])", url or "")
    if match:
        suffix = f".{match.group(1).lower()}"
        if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
            return ".jpg" if suffix == ".jpeg" else suffix
    fmt_match = re.search(r"[?&]wx_fmt=([a-zA-Z0-9]+)", url or "")
    if fmt_match:
        suffix = f".{fmt_match.group(1).lower()}"
        if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
            return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"


def clean_ocr_text(text: str) -> str:
    lines: list[str] = []
    for raw in (text or "").replace("\r", "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in NOISE_EXACT_LINES:
            continue
        if re.fullmatch(r"[，。！？、,.!?:：;；·\-_ ]+", line):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def extract_image_placeholders(html_text: str) -> tuple[str, list[dict]]:
    assets: list[dict] = []

    def replace(match: re.Match) -> str:
        src = unescape((match.group(1) or "").strip())
        if not src or src.startswith(("data:", "javascript:")):
            return ""
        token = f"[[WERSS_IMAGE_{len(assets):03d}]]"
        assets.append(
            {
                "token": token,
                "source_url": src,
            }
        )
        return f"<p>{token}</p>"

    rewritten = re.sub(
        r"<img[^>]*?src=[\"']([^\"']+)[\"'][^>]*?>",
        replace,
        html_text or "",
        flags=re.I | re.S,
    )
    return rewritten, assets


def ensure_clean_asset_dir(asset_dir: Path) -> None:
    if asset_dir.exists() and asset_dir.name.endswith("_assets"):
        shutil.rmtree(asset_dir, ignore_errors=True)
    asset_dir.mkdir(parents=True, exist_ok=True)


def download_binary(url: str) -> tuple[bytes, str]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://mp.weixin.qq.com/",
        },
    )
    with urlopen(request, timeout=60) as response:
        return response.read(), response.headers.get("Content-Type", "")


def ocr_image_file(image_path: Path) -> str:
    engine = get_ocr_engine()
    if engine is None:
        return ""
    try:
        result, _ = engine(str(image_path))
    except Exception:
        return ""
    if not result:
        return ""
    text = "\n".join(row[1] for row in result if len(row) >= 2 and row[1])
    return clean_ocr_text(text)


def materialize_article_images(
    html_fragment: str,
    md_path: Path,
    *,
    download_images: bool,
    enable_ocr: bool,
    dry_run: bool,
) -> tuple[str, list[dict]]:
    rewritten_html, assets = extract_image_placeholders(html_fragment)
    if not assets:
        return rewritten_html, []
    asset_dir = md_path.parent / f"{md_path.stem}_assets"
    relative_root = asset_dir.name
    seen_hashes: set[str] = set()
    if download_images and not dry_run:
        ensure_clean_asset_dir(asset_dir)
    for index, asset in enumerate(assets, start=1):
        url = asset["source_url"]
        asset["index"] = index
        asset["downloaded"] = False
        asset["ocr_text"] = ""
        asset["error"] = ""
        asset["skip_render"] = False
        ext = ".jpg"
        try:
            if download_images:
                if dry_run:
                    ext = guess_image_extension(url)
                else:
                    payload, content_type = download_binary(url)
                    payload_hash = sha1_bytes(payload)
                    if payload_hash in seen_hashes:
                        asset["skip_render"] = True
                        continue
                    seen_hashes.add(payload_hash)
                    ext = guess_image_extension(url, content_type)
                    file_name = f"img_{index:03d}{ext}"
                    asset_path = asset_dir / file_name
                    asset_path.write_bytes(payload)
                    asset["asset_path"] = str(asset_path)
                    asset["markdown_path"] = f"{relative_root}/{file_name}".replace("\\", "/")
                    asset["downloaded"] = True
                    if enable_ocr:
                        asset["ocr_text"] = ocr_image_file(asset_path)
            if not asset.get("markdown_path"):
                if download_images:
                    file_name = f"img_{index:03d}{ext}"
                    asset["markdown_path"] = f"{relative_root}/{file_name}".replace("\\", "/")
                else:
                    asset["markdown_path"] = url
        except Exception as exc:
            asset["error"] = str(exc)
            asset["markdown_path"] = url
    return rewritten_html, assets


def render_image_block(asset: dict) -> str:
    if asset.get("skip_render"):
        return ""
    return f"![图片{asset.get('index', 0)}]({asset.get('markdown_path') or asset.get('source_url', '')})"


def render_image_ocr_section(assets: list[dict]) -> str:
    blocks: list[str] = []
    for asset in assets:
        if asset.get("skip_render"):
            continue
        ocr_text = clean_ocr_text(asset.get("ocr_text", ""))
        if not ocr_text:
            continue
        blocks.extend(
            [
                f"### 图片 {asset.get('index', 0)}",
                "",
                f"- 来源图片：{asset.get('source_url', '')}",
                f"- 本地图片：{asset.get('markdown_path', '')}",
                "",
                "OCR文本：",
                "",
                ocr_text,
                "",
            ]
        )
    if not blocks:
        return ""
    return "\n".join(["## 图片文字识别", "", *blocks]).strip()


def inject_image_blocks(markdown_body: str, assets: list[dict]) -> str:
    text = markdown_body
    for asset in assets:
        text = text.replace(asset["token"], render_image_block(asset))
    return text


def infer_content_form(fragment: str, assets: list[dict], ocr_count: int) -> str:
    plain_fragment = re.sub(r"<img[^>]*?>", "", fragment or "", flags=re.I | re.S)
    plain_text = remove_markdown_artifacts(html_to_markdown(plain_fragment))
    if not assets:
        return "text_only"
    if len(plain_text) < 120 and ocr_count > 0:
        return "image_heavy"
    if len(plain_text) < 120:
        return "image_only"
    return "mixed"


def html_to_markdown(html_text: str) -> str:
    text = html_text or ""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", "", text, flags=re.I | re.S)
    text = re.sub(
        r"<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
        lambda m: (
            re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if unescape(m.group(1)).strip().lower().startswith("javascript:")
            else f"[{re.sub(r'<[^>]+>', '', m.group(2)).strip() or unescape(m.group(1))}]({unescape(m.group(1))})"
        ),
        text,
        flags=re.I | re.S,
    )
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.I)
    text = re.sub(r"</?(div|section|article)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.I)
    text = re.sub(r"</li\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</?(ul|ol)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<blockquote[^>]*>", "\n> ", text, flags=re.I)
    text = re.sub(r"</blockquote\s*>", "\n", text, flags=re.I)
    text = re.sub(
        r"<h([1-6])[^>]*>",
        lambda m: "\n" + ("#" * int(m.group(1))) + " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"</h[1-6]\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text).replace("\r", "")
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.I)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            lines.append("")
            continue
        if line in NOISE_EXACT_LINES:
            continue
        if line.startswith("微信扫一扫可打开此内容"):
            continue
        if line.startswith("使用完整服务"):
            continue
        if line.startswith("向上滑动看下一个"):
            continue
        if re.fullmatch(r"[-_* ]{3,}", line):
            continue
        if re.fullmatch(r"(取消|允许)(\s+(取消|允许))*", line):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_html_document(title: str, fragment: str) -> str:
    body = fragment or ""
    if re.search(r"<html\b", body, flags=re.I):
        return body
    return (
        "<html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body>{body}</body></html>"
    )


def pick_article_fragment(article: dict) -> str:
    for key in ("content_html", "content", "description"):
        value = (article.get(key) or "").strip()
        if value:
            return value
    return ""


def merge_article_payload(summary: dict | None, detail: dict | None) -> dict:
    merged = dict(summary or {})
    for key, value in (detail or {}).items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


class WeRSSClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        token: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.token = token or ""
        self.timeout = timeout

    def _request_json(
        self,
        path: str,
        *,
        query: dict | None = None,
        data: dict | None = None,
        auth: bool = True,
        retry: bool = True,
    ) -> dict:
        url = f"{self.base_url}{path}"
        if query:
            encoded = urlencode({k: v for k, v in query.items() if v is not None})
            if encoded:
                url = f"{url}?{encoded}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        payload = None
        if data is not None:
            payload = urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if auth:
            if not self.token:
                self.login()
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, data=payload, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            if exc.code in (401, 403) and auth and retry:
                self.token = ""
                self.login()
                return self._request_json(path, query=query, data=data, auth=auth, retry=False)
            raise RuntimeError(f"HTTP {exc.code} {path}: {body[:300]}") from exc
        except URLError as exc:
            raise RuntimeError(f"URL error {path}: {exc}") from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"JSON decode failed {path}: {text[:300]}") from exc

    def login(self) -> str:
        response = self._request_json(
            "/auth/login",
            data={"username": self.username, "password": self.password},
            auth=False,
        )
        token = ((response.get("data") or {}).get("access_token") or "").strip()
        if not token:
            raise RuntimeError(f"login failed: {json.dumps(response, ensure_ascii=False)}")
        self.token = token
        return token

    def fetch_all_mps(self, limit: int = 100) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        total = None
        while True:
            response = self._request_json("/mps", query={"offset": offset, "limit": limit})
            data = response.get("data") or {}
            batch = list(data.get("list") or [])
            rows.extend(batch)
            total = data.get("total", total)
            if not batch or (total is not None and len(rows) >= int(total)):
                break
            offset += limit
        return rows

    def fetch_all_articles(self, limit: int = 100, has_content: bool | None = None) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        total = None
        while True:
            query = {"offset": offset, "limit": limit}
            if has_content is not None:
                query["has_content"] = "true" if has_content else "false"
            response = self._request_json("/articles", query=query)
            data = response.get("data") or {}
            batch = list(data.get("list") or [])
            rows.extend(batch)
            total = data.get("total", total)
            if not batch or (total is not None and len(rows) >= int(total)):
                break
            offset += limit
        return rows

    def fetch_article_detail(self, article_id: str) -> dict:
        safe_id = quote(article_id, safe="")
        response = self._request_json(f"/articles/{safe_id}", query={"content": "true"})
        return response.get("data") or {}


def build_article_indexes(articles: list[dict]) -> dict[str, dict]:
    by_url: dict[str, dict] = {}
    by_source_title_date: dict[tuple[str, str, str], list[dict]] = {}
    by_title_date: dict[tuple[str, str], list[dict]] = {}
    by_source_title: dict[tuple[str, str], list[dict]] = {}
    by_source_title_loose: dict[tuple[str, str], list[dict]] = {}
    for article in articles:
        url_key = canonicalize_mp_url(article.get("url", ""))
        if url_key:
            by_url[url_key] = article
        title_key = normalize_title(article.get("title", ""))
        title_loose = normalize_title_loose(article.get("title", ""))
        date_key = unix_to_date_text(article.get("publish_time") or article.get("create_time"))
        source_key = normalize_source_name(article.get("mp_name", ""))
        by_source_title_date.setdefault((source_key, title_key, date_key), []).append(article)
        by_title_date.setdefault((title_key, date_key), []).append(article)
        by_source_title.setdefault((source_key, title_key), []).append(article)
        by_source_title_loose.setdefault((source_key, title_loose), []).append(article)
    return {
        "by_url": by_url,
        "by_source_title_date": by_source_title_date,
        "by_title_date": by_title_date,
        "by_source_title": by_source_title,
        "by_source_title_loose": by_source_title_loose,
    }


def infer_created_date(path: Path, meta: dict, body: str) -> str:
    for candidate in (
        meta.get("created", ""),
        meta.get("date", ""),
        meta.get("updated", ""),
        path.stem,
        body[:120],
    ):
        match = re.search(r"(\d{4})[-./](\d{2})[-./](\d{2})", candidate or "")
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return datetime.now().strftime("%Y-%m-%d")


def infer_title(path: Path, meta: dict, body: str) -> str:
    if meta.get("title"):
        return meta["title"].strip()
    match = re.search(r"^\s*#\s+(.+)$", body, flags=re.M)
    if match:
        return match.group(1).strip()
    name = path.stem.replace("_fromRoot", "")
    name = re.sub(r"^\d{4}[-.]\d{2}[-.]\d{2}[_-]?", "", name)
    name = re.sub(r"[_-][0-9a-fA-F]{8,}$", "", name)
    return name.strip("_- ") or path.stem


def should_repair(path: Path, meta: dict, body: str) -> str:
    full_text = (body or "").lower()
    markdown_body = html_to_markdown(body) if "<" in body else body
    cleaned = remove_markdown_artifacts(markdown_body)
    tag_count = len(re.findall(r"<[a-z!/][^>]*>", body or "", flags=re.I))
    lines = [line.strip() for line in (body or "").splitlines()]
    placeholder_lines = 0
    substantive_lines = 0
    for line in lines:
        if not line or re.fullmatch(r"[-*#>_\[\]\(\)\s.!?,:;:：，。！？、]+", line):
            placeholder_lines += 1
            continue
        if re.search(r"[\u4e00-\u9fffA-Za-z0-9]", line):
            substantive_lines += 1
        else:
            placeholder_lines += 1
    if path.stem.endswith("_fromRoot"):
        return "from_root_variant"
    if any(signal in full_text for signal in BAD_HTML_SIGNALS):
        return "html_pollution"
    if "raw html" in full_text and len(cleaned) < 120:
        return "body_missing"
    if tag_count >= 25 and len(cleaned) < 400:
        return "html_residue"
    if len(lines) >= 30 and placeholder_lines / max(1, len(lines)) >= 0.72 and substantive_lines <= 12:
        return "body_structure_broken"
    if len(cleaned) < 80 and (meta.get("source_url") or extract_source_url(body)):
        return "body_too_short"
    if "![图片" in body and not meta.get("ocr_image_count"):
        return "missing_image_ocr"
    return ""


def int_meta(meta: dict, key: str) -> int:
    try:
        return int(str(meta.get(key, "0")).strip())
    except Exception:
        return 0


def needs_policy_ocr(meta: dict, body: str = "") -> bool:
    policy = str(meta.get("ocr_policy", "")).strip()
    if not policy:
        policy = str(source_profile(str(meta.get("source", ""))).get("ocr_policy", "")).strip()
    if policy != "full":
        return False
    image_count = int_meta(meta, "image_count") or (body or "").count("![图片")
    ocr_count = int_meta(meta, "ocr_image_count")
    if image_count > 0 and ocr_count < image_count:
        return True
    if image_count > 0 and str(meta.get("ocr_policy_active", "")).strip().lower() != "true":
        return True
    return False


def match_article(path: Path, meta: dict, body: str, indexes: dict[str, dict]) -> tuple[dict | None, str]:
    source_url = canonicalize_mp_url(meta.get("source_url", "") or extract_source_url(body))
    if source_url:
        hit = indexes["by_url"].get(source_url)
        if hit:
            return hit, "source_url"

    title = infer_title(path, meta, body)
    created = infer_created_date(path, meta, body)
    source_name = meta.get("source", "") or path.parent.name
    source_key = normalize_source_name(source_name)
    title_key = normalize_title(title)
    title_loose = normalize_title_loose(title)

    candidates = indexes["by_source_title_date"].get((source_key, title_key, created), [])
    if len(candidates) == 1:
        return candidates[0], "source_title_date"

    candidates = indexes["by_title_date"].get((title_key, created), [])
    if len(candidates) == 1:
        return candidates[0], "title_date"

    candidates = indexes["by_source_title"].get((source_key, title_key), [])
    if len(candidates) == 1:
        return candidates[0], "source_title"

    candidates = indexes["by_source_title_loose"].get((source_key, title_loose), [])
    if len(candidates) == 1:
        return candidates[0], "source_title_loose"

    return None, ""


def render_markdown(
    article: dict,
    md_path: Path,
    html_path: Path,
    *,
    source_name: str | None = None,
    download_images: bool = False,
    enable_ocr: bool = False,
    dry_run: bool = False,
) -> tuple[str, str]:
    title = (article.get("title") or "未命名文章").strip()
    source_url = canonicalize_mp_url(article.get("url", ""))
    publish_date = unix_to_date_text(article.get("publish_time") or article.get("create_time"))
    source_name = (source_name or article.get("mp_name") or "未知来源").strip()
    profile = source_profile(source_name)
    ocr_policy = str(profile.get("ocr_policy", "text_first") or "text_first")
    ocr_policy_full = ocr_policy == "full"
    effective_download_images = bool(download_images and ocr_policy_full)
    effective_enable_ocr = bool(enable_ocr and effective_download_images and can_enable_ocr())
    fragment = pick_article_fragment(article)
    html_payload = build_html_document(title, fragment)
    localized_fragment, assets = materialize_article_images(
        fragment,
        md_path,
        download_images=effective_download_images,
        enable_ocr=effective_enable_ocr,
        dry_run=dry_run,
    )
    body = inject_image_blocks(html_to_markdown(localized_fragment), assets)
    ocr_section = render_image_ocr_section(assets)
    if ocr_section:
        body = f"{body.strip()}\n\n{ocr_section}"
    if len(remove_markdown_artifacts(body)) < 40:
        body = remove_markdown_artifacts(article.get("description", "") or article.get("title", ""))
    rendered_assets = [asset for asset in assets if not asset.get("skip_render")]
    image_count = len(rendered_assets)
    downloaded_count = sum(1 for asset in rendered_assets if asset.get("downloaded"))
    ocr_count = sum(1 for asset in rendered_assets if asset.get("ocr_text"))
    content_form = infer_content_form(fragment, assets, ocr_count)
    image_heavy = content_form in {"image_heavy", "image_only"}
    content_hash = sha256_text(html_payload)
    md_lines = [
        "---",
        f"title: {yaml_quote(title)}",
        f"created: {publish_date}",
        f"updated: {datetime.now().strftime('%Y-%m-%d')}",
        "type: 公众号原文",
        f"source: {yaml_quote(source_name)}",
        f"source_url: {yaml_quote(source_url)}",
        f"source_hash: {content_hash}",
        f"content_hash: {content_hash}",
        "preferred_ingestor: codex",
        "ingested_by: codex",
        "capture_pipeline: werss_api",
        f"source_class: {yaml_quote(profile.get('source_class', '市场情绪'))}",
        f"truth_grade: {profile.get('truth_grade', 'S3')}",
        f"use_grade: {profile.get('use_grade', 'reference')}",
        f"trade_impact: {profile.get('trade_impact', 'medium')}",
        f"ocr_policy: {ocr_policy}",
        f"ocr_policy_active: {'true' if effective_enable_ocr else 'false'}",
        f"images_localized: {'true' if downloaded_count == image_count and image_count > 0 else 'false'}",
        f"image_count: {image_count}",
        f"ocr_image_count: {ocr_count}",
        f"image_heavy: {'true' if image_heavy else 'false'}",
        f"content_form: {yaml_quote(content_form)}",
        f"ocr_engine: {yaml_quote(OCR_ENGINE_NAME if effective_enable_ocr else '')}",
        "deepseek_action: skip",
        f"werss_article_id: {yaml_quote(article.get('id', ''))}",
        f"mp_id: {yaml_quote(article.get('mp_id', ''))}",
        "---",
        "",
        f"# {title}",
        "",
        f"- 来源：{source_name}",
        f"- 原链接：{source_url}",
        f"- 来源分层：{profile.get('source_class', '市场情绪')}",
        f"- 使用等级：{profile.get('use_grade', 'reference')}",
        f"- 交易影响：{profile.get('trade_impact', 'medium')}",
        f"- OCR策略：{ocr_policy}",
        f"- OCR实际启用：{'是' if effective_enable_ocr else '否'}",
        f"- WeRSS 文章ID：{article.get('id', '')}",
        f"- 公众号ID：{article.get('mp_id', '')}",
        f"- RAW HTML：{html_path}",
        f"- 内容 hash：{content_hash}",
        f"- 图片数量：{image_count}",
        f"- OCR 图片数：{ocr_count}",
        f"- 内容形态：{content_form}",
        "- 修复来源：WeRSS API",
        "",
        "---",
        "",
        body.strip(),
        "",
    ]
    return "\n".join(md_lines), html_payload


def write_article_files(
    md_path: Path,
    article: dict,
    *,
    source_name: str | None = None,
    download_images: bool = True,
    enable_ocr: bool = True,
    dry_run: bool = False,
) -> tuple[Path, Path]:
    html_path = md_path.with_suffix(".html")
    md_text, html_payload = render_markdown(
        article,
        md_path,
        html_path,
        source_name=source_name,
        download_images=download_images,
        enable_ocr=enable_ocr,
        dry_run=dry_run,
    )
    if not dry_run:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_text, encoding="utf-8")
        html_path.write_text(html_payload, encoding="utf-8")
    return md_path, html_path


def build_ingest_path(article: dict) -> Path:
    date_text = unix_to_date_text(article.get("publish_time") or article.get("create_time"))
    source_name = article.get("mp_name") or "未知来源"
    source_dir = sanitize_filename(source_name)
    source_class = source_profile(source_name).get("source_class", "")
    bucket = "游资号" if source_class == "游资心得" else "媒体号"
    short_hash = sha1_text(article.get("id") or article.get("url") or article.get("title") or date_text)[:12]
    return RAW_MP_DIR / bucket / source_dir / f"{date_text}_{short_hash}.md"


def load_known_source_urls(raw_root: Path) -> set[str]:
    urls: set[str] = set()
    for path in raw_root.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        meta, body = parse_frontmatter(text)
        url = canonicalize_mp_url(meta.get("source_url", "") or extract_source_url(body))
        if url:
            urls.add(url)
    return urls


def should_relocate_unknown_source(path: Path, article: dict) -> bool:
    if path.parent.name != "未知来源":
        return False
    target_parent = build_ingest_path(article).parent
    return target_parent.name != path.parent.name


def cleanup_old_article_bundle(path: Path) -> None:
    html_path = path.with_suffix(".html")
    asset_dir = path.parent / f"{path.stem}_assets"
    if path.exists():
        path.unlink()
    if html_path.exists():
        html_path.unlink()
    if asset_dir.exists() and asset_dir.is_dir():
        shutil.rmtree(asset_dir, ignore_errors=True)


def ensure_state(state_path: Path) -> dict:
    state = load_json(state_path, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("articles", {})
    return state


def saved_article_needs_ocr(saved: dict | None) -> bool:
    if not saved or not saved.get("md_path"):
        return False
    path = Path(str(saved.get("md_path")))
    if not path.exists():
        return False
    try:
        meta, _body = parse_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return False
    return needs_policy_ocr(meta, _body)


def run_ingest(
    client: WeRSSClient,
    *,
    state_path: Path,
    log_path: Path,
    registry_path: Path,
    download_images: bool = False,
    enable_ocr: bool = False,
    dry_run: bool = False,
) -> dict:
    state = ensure_state(state_path)
    known_urls = load_known_source_urls(RAW_MP_DIR)
    articles = client.fetch_all_articles(limit=100, has_content=True)
    articles = sorted(articles, key=lambda row: int(row.get("publish_time") or 0))
    new_count = 0
    skipped_existing = 0
    for article in articles:
        article_id = str(article.get("id") or "").strip()
        if not article_id:
            continue
        updated_at = str(article.get("updated_at_millis") or article.get("updated_at") or "")
        saved = state["articles"].get(article_id)
        if saved and saved.get("updated_at") == updated_at and not (download_images and enable_ocr and saved_article_needs_ocr(saved)):
            continue
        source_url = canonicalize_mp_url(article.get("url", ""))
        if source_url and source_url in known_urls and not saved:
            state["articles"][article_id] = {
                "updated_at": updated_at,
                "source_url": source_url,
                "md_path": "",
                "captured_at": now_text(),
                "bootstrapped": True,
            }
            skipped_existing += 1
            continue
        detail = client.fetch_article_detail(article_id)
        payload = merge_article_payload(article, detail)
        md_path = build_ingest_path(payload)
        written_md, written_html = write_article_files(
            md_path,
            payload,
            download_images=download_images,
            enable_ocr=enable_ocr,
            dry_run=dry_run,
        )
        state["articles"][article_id] = {
            "updated_at": updated_at,
            "source_url": source_url,
            "md_path": str(written_md),
            "html_path": str(written_html),
            "captured_at": now_text(),
        }
        if source_url:
            known_urls.add(source_url)
        append_jsonl(
            registry_path,
            {
                "captured_at": now_text(),
                "action": "ingest",
                "article_id": article_id,
                "source": payload.get("mp_name") or article.get("mp_name"),
                "source_url": source_url,
                "md_path": str(written_md),
                "html_path": str(written_html),
                "capture_pipeline": "werss_api",
            },
        )
        new_count += 1
        log(f"新增入库: {payload.get('title') or article.get('title')}", log_path)
    if not dry_run:
        save_json(state_path, state)
    return {
        "new_articles": new_count,
        "bootstrapped_existing": skipped_existing,
        "fetched_articles": len(articles),
    }


def scan_markdown_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("*.md")))
    return files


def write_audit_markdown(audit_path: Path, audit: dict) -> None:
    summary = audit.get("summary") or {}
    repaired = audit.get("repaired") or []
    unmatched = audit.get("unmatched") or []
    lines = [
        "# WeRSS 重抓审计",
        "",
        f"- 生成时间：{audit.get('generated_at', '')}",
        f"- 扫描文件：{summary.get('scanned', 0)}",
        f"- 待修复候选：{summary.get('candidates', 0)}",
        f"- 已修复：{summary.get('repaired', 0)}",
        f"- 未命中：{summary.get('unmatched', 0)}",
        "",
        "## 已修复",
        "",
    ]
    if not repaired:
        lines.append("无")
    else:
        lines.extend(["| 文件 | 命中方式 | WeRSS文章ID | 原链接 |", "|---|---|---|---|"])
        for item in repaired:
            lines.append(
                f"| {item['path']} | {item['match_strategy']} | {item['article_id']} | {item['source_url']} |"
            )
    lines.extend(["", "## 未命中", ""])
    if not unmatched:
        lines.append("无")
    else:
        lines.extend(["| 文件 | 触发原因 | 标题 | 来源 |", "|---|---|---|---|"])
        for item in unmatched:
            lines.append(
                f"| {item['path']} | {item['reason']} | {item['title']} | {item['source']} |"
            )
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_audit_markdown(audit_path: Path, audit: dict) -> None:
    summary = audit.get("summary") or {}
    repaired = audit.get("repaired") or []
    manual_review = audit.get("manual_review") or []
    unmatched = audit.get("unmatched") or []
    lines = [
        "# WeRSS Repair Audit",
        "",
        f"- Generated: {audit.get('generated_at', '')}",
        f"- Scanned files: {summary.get('scanned', 0)}",
        f"- Repair candidates: {summary.get('candidates', 0)}",
        f"- Repaired: {summary.get('repaired', 0)}",
        f"- Manual review: {summary.get('manual_review', 0)}",
        f"- Unmatched: {summary.get('unmatched', 0)}",
        "",
        "## Repaired",
        "",
    ]
    if not repaired:
        lines.append("None")
    else:
        lines.extend(["| File | Match strategy | WeRSS article ID | Source URL |", "|---|---|---|---|"])
        for item in repaired:
            lines.append(
                f"| {item['path']} | {item['match_strategy']} | {item['article_id']} | {item['source_url']} |"
            )
    lines.extend(["", "## Manual Review", ""])
    if not manual_review:
        lines.append("None")
    else:
        lines.extend(["| File | Trigger | Title | Source | Note |", "|---|---|---|---|---|"])
        for item in manual_review:
            lines.append(
                f"| {item['path']} | {item['reason']} | {item['title']} | {item['source']} | {item['note']} |"
            )
    lines.extend(["", "## Unmatched", ""])
    if not unmatched:
        lines.append("None")
    else:
        lines.extend(["| File | Trigger | Title | Source |", "|---|---|---|---|"])
        for item in unmatched:
            lines.append(
                f"| {item['path']} | {item['reason']} | {item['title']} | {item['source']} |"
            )
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_repair(
    client: WeRSSClient,
    *,
    repair_roots: list[Path],
    audit_json_path: Path,
    audit_md_path: Path,
    registry_path: Path,
    log_path: Path,
    force_missing_pipeline: bool = False,
    force_missing_ocr: bool = False,
    relocate_unknown_source: bool = False,
    download_images: bool = True,
    enable_ocr: bool = True,
    dry_run: bool = False,
) -> dict:
    files = scan_markdown_files(repair_roots)
    articles = client.fetch_all_articles(limit=100, has_content=None)
    indexes = build_article_indexes(articles)
    repaired: list[dict] = []
    manual_review: list[dict] = []
    unmatched: list[dict] = []
    candidates = 0

    def build_audit() -> dict:
        return {
            "generated_at": now_text(),
            "roots": [str(root) for root in repair_roots],
            "summary": {
                "scanned": len(files),
                "candidates": candidates,
                "repaired": len(repaired),
                "manual_review": len(manual_review),
                "unmatched": len(unmatched),
            },
            "repaired": repaired,
            "manual_review": manual_review,
            "unmatched": unmatched,
        }

    def flush_audit() -> None:
        if dry_run:
            return
        audit = build_audit()
        save_json(audit_json_path, audit)
        write_audit_markdown(audit_md_path, audit)

    flush_audit()
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        meta, body = parse_frontmatter(text)
        cleaned_body = remove_markdown_artifacts(html_to_markdown(body) if "<" in body else body)
        reason = ""
        if force_missing_pipeline and "capture_pipeline: werss_api" not in text:
            reason = "missing_werss_pipeline"
        if not reason and force_missing_ocr and needs_policy_ocr(meta, body):
            reason = "missing_image_ocr"
        if not reason and relocate_unknown_source and path.parent.name == "未知来源":
            reason = "unknown_source_bucket"
        if not reason:
            reason = should_repair(path, meta, body)
        if not reason:
            continue
        candidates += 1
        article, strategy = match_article(path, meta, body, indexes)
        title = infer_title(path, meta, body)
        source_name = meta.get("source", "") or path.parent.name
        source_url = canonicalize_mp_url(meta.get("source_url", "") or extract_source_url(body))
        if not article:
            if reason in {"missing_image_ocr", "missing_werss_pipeline"} and source_url and len(cleaned_body) >= 1000:
                manual_review.append(
                    {
                        "path": str(path),
                        "reason": reason,
                        "title": title,
                        "source": source_name,
                        "source_url": source_url,
                        "note": "body_present_but_werss_missing",
                    }
                )
                log(f"manual review required: {path}", log_path)
                flush_audit()
                continue
            unmatched.append(
                {
                    "path": str(path),
                    "reason": reason,
                    "title": title,
                    "source": source_name,
                    "source_url": source_url,
                }
            )
            log(f"未命中 WeRSS: {path}", log_path)
            flush_audit()
            continue
        detail = client.fetch_article_detail(article["id"])
        payload = merge_article_payload(article, detail)
        target_path = build_ingest_path(payload) if should_relocate_unknown_source(path, payload) else path
        write_article_files(
            target_path,
            payload,
            source_name=source_name,
            download_images=download_images,
            enable_ocr=enable_ocr,
            dry_run=dry_run,
        )
        if target_path != path and not dry_run:
            cleanup_old_article_bundle(path)
        row = {
            "path": str(target_path),
            "reason": reason,
            "match_strategy": strategy,
            "article_id": article.get("id", ""),
            "source_url": canonicalize_mp_url(payload.get("url", "")),
            "title": payload.get("title", ""),
            "source": payload.get("mp_name", "") or source_name,
        }
        repaired.append(row)
        append_jsonl(
            registry_path,
            {
                "captured_at": now_text(),
                "action": "repair",
                "article_id": article.get("id", ""),
                "source": payload.get("mp_name", "") or source_name,
                "source_url": row["source_url"],
                "md_path": str(target_path),
                "html_path": str(target_path.with_suffix(".html")),
                "capture_pipeline": "werss_api",
                "repair_reason": reason,
                "match_strategy": strategy,
            },
        )
        flush_audit()
        if target_path != path:
            log(f"修复并迁移: {path.name} -> {target_path.parent.name} <- {row['title']}", log_path)
        else:
            log(f"修复完成: {path.name} <- {row['title']}", log_path)
    audit = build_audit()
    flush_audit()
    return audit


def self_test() -> int:
    sample = """
---
title: 测试标题
source_url: https://mp.weixin.qq.com/s/abc?scene=1&from=timeline
---

# 测试标题

<div id="js_content"><p>第一段</p><p>第二段</p></div>
"""
    meta, body = parse_frontmatter(sample)
    assert meta["title"] == "测试标题"
    assert canonicalize_mp_url(meta["source_url"]) == "https://mp.weixin.qq.com/s/abc"
    md = html_to_markdown(body)
    assert "第一段" in md and "第二段" in md
    localized_html, assets = extract_image_placeholders('<p>a</p><img src="https://a/b.jpg"><p>b</p>')
    assert assets and assets[0]["source_url"] == "https://a/b.jpg"
    assert "[[WERSS_IMAGE_000]]" in localized_html
    assert should_repair(Path("bad_fromRoot.md"), meta, body) == "from_root_variant"
    print("self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["ingest", "repair", "both"], default="both")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--token")
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--audit-json", default=str(DEFAULT_AUDIT_JSON))
    parser.add_argument("--audit-md", default=str(DEFAULT_AUDIT_MD))
    parser.add_argument("--seconds", type=int, default=900)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--repair-root", action="append")
    parser.add_argument("--repair-if-missing-pipeline", action="store_true")
    parser.add_argument("--repair-if-missing-ocr", action="store_true")
    parser.add_argument("--relocate-unknown-source", action="store_true")
    parser.add_argument("--with-image-download", action="store_true")
    parser.add_argument("--with-ocr", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    state_path = Path(args.state)
    log_path = Path(args.log)
    audit_json_path = Path(args.audit_json)
    audit_md_path = Path(args.audit_md)
    registry_path = DEFAULT_REGISTRY
    repair_roots = [Path(item) for item in args.repair_root] if args.repair_root else [DEFAULT_REPAIR_ROOT]
    download_images = bool(args.with_image_download)
    enable_ocr = bool(args.with_ocr) and can_enable_ocr()

    client = WeRSSClient(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        token=args.token,
    )

    def run_once() -> dict:
        result: dict[str, dict] = {}
        if args.mode in {"ingest", "both"}:
            result["ingest"] = run_ingest(
                client,
                state_path=state_path,
                log_path=log_path,
                registry_path=registry_path,
                download_images=download_images,
                enable_ocr=enable_ocr,
                dry_run=args.dry_run,
            )
        if args.mode in {"repair", "both"}:
            result["repair"] = run_repair(
                client,
                repair_roots=repair_roots,
                audit_json_path=audit_json_path,
                audit_md_path=audit_md_path,
                registry_path=registry_path,
                log_path=log_path,
                force_missing_pipeline=args.repair_if_missing_pipeline,
                force_missing_ocr=args.repair_if_missing_ocr,
                relocate_unknown_source=args.relocate_unknown_source,
                download_images=download_images,
                enable_ocr=enable_ocr,
                dry_run=args.dry_run,
            )
        return result

    if args.once:
        print(json.dumps(run_once(), ensure_ascii=False, indent=2))
        return 0

    while True:
        try:
            run_once()
        except Exception as exc:
            log(f"主循环异常: {exc}", log_path)
        time.sleep(max(60, args.seconds))


if __name__ == "__main__":
    sys.exit(main())
