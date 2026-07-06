import argparse
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Union
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "raw" / "04-市场数据" / "东方财富"
EASTMONEY_BASE = "https://push2.eastmoney.com/api"


def now_cn() -> str:
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S +08:00")


def fetch_json(url: str, timeout: int, retries: int = 2) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) 73WIKI/1.0",
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "close",
        },
    )
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
            break
        except HTTPError as exc:
            last_error = exc
            if attempt >= retries:
                raise RuntimeError(f"HTTP {exc.code}: {url}") from exc
        except (URLError, ConnectionError) as exc:
            last_error = exc
            if attempt >= retries:
                raise RuntimeError(f"Network error: {url}; {exc}") from exc
        time.sleep(1 + attempt)
    else:
        raise RuntimeError(f"Network error: {url}; {last_error}")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from {url}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Unexpected JSON root from {url}")
    return parsed


def clist_url(**overrides: Union[str, int]) -> str:
    params = {
        "pn": 1,
        "pz": 100,
        "po": 1,
        "np": 1,
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fields": "f12,f14,f2,f3,f4,f5,f6,f7,f15,f16,f17,f18,f20,f21",
    }
    params.update(overrides)
    return f"{EASTMONEY_BASE}/qt/clist/get?{urlencode(params)}"


def fetch_clist_all(fs: str, pz: int, timeout: int) -> dict:
    first_url = clist_url(pn=1, pz=pz, fs=fs)
    first = fetch_json(first_url, timeout)
    data = first.get("data")
    if not isinstance(data, dict):
      return first
    total = data.get("total")
    try:
        total_count = int(total)
    except (TypeError, ValueError):
        total_count = len(data.get("diff") or [])

    all_diff = list(data.get("diff") or [])
    pages = max(1, (total_count + pz - 1) // pz)
    for page in range(2, pages + 1):
        next_url = clist_url(pn=page, pz=pz, fs=fs)
        next_page = fetch_json(next_url, timeout)
        next_data = next_page.get("data")
        if isinstance(next_data, dict) and isinstance(next_data.get("diff"), list):
            all_diff.extend(next_data["diff"])

    data["diff"] = all_diff
    data["total"] = total_count
    return first


def indices_url() -> str:
    params = {
        "fltt": 2,
        "invt": 2,
        "fields": "f12,f14,f2,f3,f4,f6",
        "secids": "1.000001,0.399001,0.399006,1.000688",
    }
    return f"{EASTMONEY_BASE}/qt/ulist.np/get?{urlencode(params)}"


def fetch_snapshot(timeout: int) -> dict:
    urls = {
        "indices": indices_url(),
        "industries": clist_url(pz=500, fs="m:90+t:2"),
        "stocks": clist_url(pz=200, fs="m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"),
    }
    return {
        "fetched_at": now_cn(),
        "source": "东方财富 push2.eastmoney.com",
        "urls": urls,
        "indices": fetch_json(urls["indices"], timeout),
        "industries": fetch_clist_all("m:90+t:2", 500, timeout),
        "stocks": fetch_clist_all("m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23", 200, timeout),
    }


def count_rows(section: object) -> int:
    if not isinstance(section, dict):
        return 0
    data = section.get("data")
    if not isinstance(data, dict):
        return 0
    diff = data.get("diff")
    return len(diff) if isinstance(diff, list) else 0


def write_snapshot(market_date: str, snapshot: dict, force: bool, dry_run: bool) -> Path:
    out_dir = OUTPUT_ROOT / market_date
    out_path = out_dir / "market-snapshot.json"
    if out_path.exists() and not force:
        raise FileExistsError(f"exists: {out_path}; use --force to overwrite")
    if dry_run:
        return out_path
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Eastmoney market snapshot into RAW for candidate D+ backfill.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Market date YYYY-MM-DD.")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing snapshot.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and validate, but do not write.")
    args = parser.parse_args()

    snapshot = fetch_snapshot(args.timeout)
    out_path = write_snapshot(args.date, snapshot, args.force, args.dry_run)
    print(f"output={'dry-run' if args.dry_run else 'written'} {out_path}")
    print(f"indices={count_rows(snapshot.get('indices'))}")
    print(f"industries={count_rows(snapshot.get('industries'))}")
    print(f"stocks={count_rows(snapshot.get('stocks'))}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
