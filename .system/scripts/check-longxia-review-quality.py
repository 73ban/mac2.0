#!/usr/bin/env python3
"""Quality gate for Longxia daily review RAW files."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(os.environ.get("WIKI_PROJECT_PATH", "/Users/qixinchaye/wiki/73神话"))
RAW_REVIEW_DIR = ROOT / "raw/02-每日复盘"
SYSTEM_DIR = ROOT / ".system"
REPORT_DIR = ROOT / "wiki/09-统计与进化"
FEISHU_PENDING_DIR = SYSTEM_DIR / "feishu-notify-pending"
NOTIFIED_STATE_PATH = SYSTEM_DIR / "longxia-review-quality-notified.json"
QUALITY_ISSUE_QUEUE = SYSTEM_DIR / "longxia-review-quality-issues.jsonl"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def section(text: str, start_heading: str, next_heading_prefix: str = "\n## ") -> str:
    start = text.find(start_heading)
    if start < 0:
        return ""
    nxt = text.find(next_heading_prefix, start + len(start_heading))
    return text[start:] if nxt < 0 else text[start:nxt]


def unique_stock_codes(text: str) -> set[str]:
    return set(re.findall(r"(?<!\d)(?:00|30|60|68|83|87|92)\d{4}(?!\d)", text))


def table_row_count(text: str) -> int:
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        if re.search(r"(?<!\d)(?:00|30|60|68|83|87|92)\d{4}(?!\d)", stripped):
            count += 1
    return count


def market_prefix_counts(codes: set[str]) -> dict[str, int]:
    return {
        "mainboard_10cm": sum(1 for code in codes if code.startswith(("00", "60"))),
        "gem_20cm": sum(1 for code in codes if code.startswith("30")),
        "star_20cm": sum(1 for code in codes if code.startswith("68")),
        "bse_30cm": sum(1 for code in codes if code.startswith(("83", "87", "92"))),
    }


def has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def find_json_files(trade_date: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {
        "top100_json": [],
        "ladder_json": [],
        "reason_6d_json": [],
        "first_board_json": [],
        "first_board_md": [],
        "panorama_json": [],
        "panorama_md": [],
        "board_strength_json": [],
        "board_strength_md": [],
    }
    patterns = {
        "top100_json": ["*top100*.json", "*Top100*.json", "*TOP100*.json", "*热榜*.json"],
        "ladder_json": ["*ladder*.json", "*连板天梯*.json"],
        "reason_6d_json": ["*reason*.json", "*涨停原因六维*.json", "*涨停原因6维*.json", "*6维*.json", "*热榜六维*.json"],
        "first_board_json": ["*first-board*.json", "*首板*.json", "*涨停催化*.json"],
        "first_board_md": ["*first-board*.md", "*首板*.md", "*涨停催化*.md"],
        "panorama_json": ["*panorama*.json", "*全景*.json", "*涨停总表*.json"],
        "panorama_md": ["*panorama*.md", "*全景*.md", "*涨停总表*.md"],
        "board_strength_json": ["*board-strength*.json", "*板块强度*.json"],
        "board_strength_md": ["*board-strength*.md", "*板块强度*.md"],
    }
    base_dirs = [ROOT / "raw/04-市场数据"]
    for base_dir in base_dirs:
        standard_roots = {
            "top100_json": base_dir / f"通达信热榜/{trade_date}",
            "ladder_json": base_dir / f"通达信连板天梯/{trade_date}",
            "reason_6d_json": base_dir / f"通达信涨停原因/{trade_date}",
            "first_board_json": base_dir / f"首板涨停催化/{trade_date}",
            "first_board_md": base_dir / f"首板涨停催化/{trade_date}",
            "panorama_json": base_dir / f"每日涨停全景/{trade_date}",
            "panorama_md": base_dir / f"每日涨停全景/{trade_date}",
            "board_strength_json": base_dir / f"板块强度/{trade_date}",
            "board_strength_md": base_dir / f"板块强度/{trade_date}",
        }
        for key, root in standard_roots.items():
            if root.exists():
                for pattern in patterns[key]:
                    out[key].extend(str(p.relative_to(ROOT)) for p in root.glob(pattern))

        # Longxia sometimes writes related TDX files into the hot-list folder first.
        hot_root = base_dir / f"通达信热榜/{trade_date}"
        if hot_root.exists():
            out["top100_json"].extend(str(p.relative_to(ROOT)) for p in hot_root.glob("*top100*.json"))
            out["ladder_json"].extend(str(p.relative_to(ROOT)) for p in hot_root.glob("*ladder*.json"))
            out["reason_6d_json"].extend(str(p.relative_to(ROOT)) for p in hot_root.glob("*reason*.json"))

        if base_dir.exists():
            out["ladder_json"].extend(str(p.relative_to(ROOT)) for p in base_dir.glob(f"{trade_date}-连板天梯.json"))
            out["reason_6d_json"].extend(str(p.relative_to(ROOT)) for p in base_dir.glob(f"{trade_date}-涨停原因六维.json"))
            out["reason_6d_json"].extend(str(p.relative_to(ROOT)) for p in base_dir.glob(f"{trade_date}-热榜六维.json"))
            out["first_board_json"].extend(str(p.relative_to(ROOT)) for p in base_dir.glob(f"{trade_date}-涨停催化日报.json"))
            out["first_board_md"].extend(str(p.relative_to(ROOT)) for p in base_dir.glob(f"{trade_date}-涨停催化日报.md"))
            out["panorama_json"].extend(str(p.relative_to(ROOT)) for p in base_dir.glob(f"{trade_date}-涨停全景.json"))
            out["panorama_md"].extend(str(p.relative_to(ROOT)) for p in base_dir.glob(f"{trade_date}-涨停全景.md"))
            out["board_strength_json"].extend(str(p.relative_to(ROOT)) for p in base_dir.glob(f"{trade_date}-板块强度.json"))
            out["board_strength_md"].extend(str(p.relative_to(ROOT)) for p in base_dir.glob(f"{trade_date}-板块强度.md"))
    for key in out:
        unique_paths = sorted(set(out[key]))
        if len(unique_paths) > 1:
            if key == "top100_json":
                row_counts = {path: len(load_json_items(path)) for path in unique_paths if (ROOT / path).exists()}
                max_rows = max(row_counts.values() or [0])
                unique_paths = [path for path in unique_paths if row_counts.get(path) == max_rows]
            else:
                newest_mtime = max((ROOT / path).stat().st_mtime for path in unique_paths if (ROOT / path).exists())
                # 同一类文件可能同时存在旧 tdx-* 版本和新版中文版本；验收以最新交付为准。
                unique_paths = [
                    path
                    for path in unique_paths
                    if (ROOT / path).exists() and newest_mtime - (ROOT / path).stat().st_mtime <= 300
                ]
        out[key] = unique_paths
    return out


def load_json_items(rel_path: str) -> list[dict]:
    try:
        data = json.loads((ROOT / rel_path).read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in (
            "data",
            "stocks",
            "items",
            "rows",
            "list",
            "boards",
            "records",
            "数据",
            "股票列表",
            "明细",
            "列表",
            "板块列表",
            "记录",
            "热榜",
            "热榜明细",
            "首板明细",
            "非ST首板明细",
            "非ST连板明细(≥2板)",
            "6维明细",
            "连板天梯",
        ):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def load_json_payload(rel_path: str):
    try:
        return json.loads((ROOT / rel_path).read_text(encoding="utf-8"))
    except Exception:
        return None


def iter_ladder_items(payload) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    all_items = []
    for value in payload.values():
        if isinstance(value, list):
            all_items.extend(item for item in value if isinstance(item, dict))
    return all_items


def stock_code_from_item(item: dict) -> str:
    for key in ("code", "股票代码", "证券代码", "stock_code", "symbol", "代码"):
        value = str(item.get(key, ""))
        match = re.search(r"(?<!\d)(?:00|30|60|68|83|87|92)\d{4}(?!\d)", value)
        if match:
            return match.group(0)
    match = re.search(
        r"(?<!\d)(?:00|30|60|68|83|87|92)\d{4}(?!\d)",
        json.dumps(item, ensure_ascii=False),
    )
    return match.group(0) if match else ""


def board_count_from_item(item: dict) -> int | None:
    for key in (
        "board_count",
        "limit_board_count",
        "continuous_boards",
        "连板数",
        "连板高度",
        "高度",
        "板数",
        "height",
    ):
        value = item.get(key)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            if "首板" in value or "first_board" in value.lower():
                return 1
            match = re.search(r"(\d+)\s*(?:连板|板)", value)
            if match:
                return int(match.group(1))
    joined = json.dumps(item, ensure_ascii=False)
    if "首板" in joined or "first_board" in joined.lower():
        return 1
    match = re.search(r"(\d+)\s*(?:连板|板)", joined)
    return int(match.group(1)) if match else None


def is_first_board_item(item: dict) -> bool:
    count = board_count_from_item(item)
    if count == 1:
        return True
    joined = json.dumps(item, ensure_ascii=False).lower()
    return "首板" in joined or "first_board" in joined or "first board" in joined


def item_has_6d(item: dict) -> bool:
    cn_fields = {"题材归属", "事件催化", "产业逻辑", "个股地位", "盘口质量", "明日验证点"}
    en_fields = {"theme", "catalyst", "industry_logic", "position", "tape_quality", "tomorrow_check"}
    d_fields = {"D1", "D2", "D3", "D4", "D5", "D6"}
    keys = set(str(key) for key in item.keys())
    if cn_fields.issubset(keys) or en_fields.issubset(keys) or d_fields.issubset(keys):
        return True
    for value in item.values():
        if isinstance(value, dict):
            nested_keys = set(str(key) for key in value.keys())
            if cn_fields.issubset(nested_keys) or en_fields.issubset(nested_keys) or d_fields.issubset(nested_keys):
                return True
    joined = json.dumps(item, ensure_ascii=False)
    return sum(1 for field in cn_fields if field in joined) >= 6


def item_has_reason_source_fields(item: dict) -> bool:
    joined = json.dumps(item, ensure_ascii=False)
    keys = set(str(key) for key in item.keys())
    reason_keys = {"涨停原因", "原因", "原始涨停原因", "reason", "limit_up_reason", "reason_raw"}
    tape_terms = {"板型", "封单", "封单金额", "开板", "开板次数", "成交额", "换手", "换手率", "首次封板", "最终封板"}
    source_terms = {"来源", "数据来源", "source", "sourceName"}
    has_reason = bool(keys & reason_keys) or any(term in joined for term in reason_keys)
    tape_hits = sum(1 for term in tape_terms if term in keys or term in joined)
    has_source = bool(keys & source_terms) or any(term in joined for term in source_terms)
    return has_reason and (tape_hits >= 2 or has_source)


def item_has_board_fields(item: dict) -> bool:
    joined = json.dumps(item, ensure_ascii=False)
    theme_name = str(item.get("交易题材") or item.get("themeName") or "").strip()
    board_primary = str(item.get("主板块") or item.get("boardPrimary") or item.get("板块") or "").strip()
    board_source = str(item.get("板块来源") or item.get("boardSource") or "").strip()
    concept_tags = item.get("概念标签") or item.get("题材标签") or item.get("conceptTags")
    board_evidence = str(item.get("板块归属证据") or item.get("板块证据") or item.get("归属证据") or item.get("boardEvidence") or "").strip()
    if theme_name and board_primary and board_source and concept_tags and board_evidence:
        return True
    required_terms = ["交易题材", "主板块", "板块来源", "概念标签", "板块归属证据"]
    legacy_terms = ["themeName", "boardPrimary", "boardSource", "conceptTags", "boardEvidence"]
    return all(term in joined for term in required_terms) or all(term in joined for term in legacy_terms)


def board_field_metrics(json_files: dict[str, list[str]]) -> dict:
    target_keys = ["panorama_json", "first_board_json", "ladder_json", "reason_6d_json", "top100_json"]
    seen_codes: set[str] = set()
    covered_codes: set[str] = set()
    first_missing_path: dict[str, str] = {}
    missing_preview: list[str] = []
    for key in target_keys:
        for rel_path in json_files.get(key, []):
            for item in load_json_items(rel_path):
                code = stock_code_from_item(item)
                if not code:
                    continue
                seen_codes.add(code)
                if item_has_board_fields(item):
                    covered_codes.add(code)
                else:
                    first_missing_path.setdefault(code, rel_path)
    for code in sorted(seen_codes - covered_codes):
        if len(missing_preview) >= 20:
            break
        missing_preview.append(f"{code}@{first_missing_path.get(code, '')}")
    board_strength_rows = 0
    for rel_path in json_files.get("board_strength_json", []):
        board_strength_rows = max(board_strength_rows, len(load_json_items(rel_path)))
    return {
        "checked_stock_items": len(seen_codes),
        "board_fields_covered": len(covered_codes),
        "board_fields_missing": max(0, len(seen_codes - covered_codes)),
        "board_fields_missing_preview": missing_preview,
        "board_strength_rows": board_strength_rows,
    }


def st_detail_metrics(json_files: dict[str, list[str]]) -> dict:
    hits: list[str] = []
    for rel_path in json_files.get("panorama_json", []) + json_files.get("first_board_json", []) + json_files.get("ladder_json", []):
        payload = load_json_payload(rel_path)
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            key_text = str(key)
            if ("非ST" in key_text or "剔除ST" in key_text):
                continue
            if "ST" in key_text and isinstance(value, list) and value:
                hits.append(f"{rel_path}#{key}:{len(value)}")
    return {"st_detail_count": len(hits), "st_detail_preview": hits[:10]}


def ladder_board_metrics(json_files: dict[str, list[str]]) -> dict:
    eligible: dict[str, dict] = {}
    first_board_codes: set[str] = set()
    direct_6d: set[str] = set()
    reason_6d: set[str] = set()
    direct_source: set[str] = set()
    reason_source: set[str] = set()

    for rel_path in json_files.get("reason_6d_json", []) + json_files.get("top100_json", []):
        for item in load_json_items(rel_path):
            code = stock_code_from_item(item)
            if code and item_has_6d(item):
                reason_6d.add(code)
            if code and item_has_reason_source_fields(item):
                reason_source.add(code)

    for rel_path in json_files.get("ladder_json", []):
        payload = load_json_payload(rel_path)
        for item in iter_ladder_items(payload):
            code = stock_code_from_item(item)
            if not code:
                continue
            if is_first_board_item(item):
                first_board_codes.add(code)
                continue
            count = board_count_from_item(item)
            if count is None or count >= 2:
                eligible[code] = item
                if item_has_6d(item):
                    direct_6d.add(code)
                if item_has_reason_source_fields(item):
                    direct_source.add(code)

    covered = direct_6d | (set(eligible) & reason_6d)
    source_covered = direct_source | (set(eligible) & reason_source)
    effective_covered = covered | source_covered
    missing = sorted(set(eligible) - effective_covered)
    return {
        "ladder_2plus_codes": sorted(eligible),
        "ladder_2plus_count": len(eligible),
        "ladder_first_board_codes": sorted(first_board_codes),
        "ladder_first_board_count": len(first_board_codes),
        "ladder_2plus_6d_covered": len(covered),
        "ladder_2plus_reason_source_covered": len(source_covered),
        "ladder_2plus_effective_fact_covered": len(effective_covered),
        "ladder_2plus_6d_missing": missing,
    }


def json_market_scope_metrics(json_files: dict[str, list[str]]) -> dict:
    market_counts = {"mainboard_10cm": 0, "gem_20cm": 0, "star_20cm": 0, "bse_30cm": 0}
    scope_aliases = {
        "mainboard_10cm": ("mainboard_10cm", "mainboard_10cm_count", "主板10cm数量"),
        "gem_20cm": ("gem_20cm", "gem_20cm_count", "创业板20cm数量"),
        "star_20cm": ("star_20cm", "star_20cm_count", "科创板20cm数量"),
        "bse_30cm": ("bse_30cm", "bse_30cm_count", "北交所30cm数量"),
    }
    ladder_items_total = 0
    meta_total_limit_up = None
    meta_non_st = None
    meta_selection_rule = ""
    summary = {}
    scope_declared = False
    bse_declared = False
    for rel_path in json_files.get("ladder_json", []):
        payload = load_json_payload(rel_path)
        if not isinstance(payload, dict):
            continue
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        for total_key in ("total_limit_up", "剔除ST后涨停总数", "涨停总数"):
            if isinstance(meta.get(total_key), int):
                meta_total_limit_up = max(meta_total_limit_up or 0, meta[total_key])
        for non_st_key in ("non_st", "剔除ST后2板及以上总数", "2板及以上总数", "剔除ST后数量"):
            if isinstance(meta.get(non_st_key), int):
                meta_non_st = max(meta_non_st or 0, meta[non_st_key])
        for rule_key in ("selection_rule", "选择规则"):
            if isinstance(meta.get(rule_key), str):
                meta_selection_rule = meta.get(rule_key, meta_selection_rule)
        for key in ("market_scope", "limit_ladder_market_scope", "市场范围", "连板天梯市场范围"):
            scope = payload.get(key) or meta.get(key)
            if isinstance(scope, dict):
                scope_declared = True
                for count_key, aliases in scope_aliases.items():
                    for alias in aliases:
                        if isinstance(scope.get(alias), int):
                            market_counts[count_key] = max(market_counts[count_key], scope[alias])
                if any(alias in scope for alias in scope_aliases["bse_30cm"]):
                    bse_declared = True
        if isinstance(payload.get("summary"), dict):
            summary.update(payload["summary"])
        items = iter_ladder_items(payload)
        ladder_items_total = max(ladder_items_total, len(items))
        code_counts = market_prefix_counts({str(item.get("code", "")) for item in items if item.get("code")})
        for key, value in code_counts.items():
            market_counts[key] = max(market_counts[key], value)
        if code_counts["bse_30cm"] > 0:
            bse_declared = True
    return {
        "ladder_json_items": ladder_items_total,
        "meta_total_limit_up": meta_total_limit_up,
        "meta_non_st": meta_non_st,
        "meta_selection_rule": meta_selection_rule,
        "summary": summary,
        "market_counts": market_counts,
        "scope_declared": scope_declared,
        "bse_declared": bse_declared,
    }


def top100_json_max_rows(json_files: dict[str, list[str]]) -> int:
    return max([len(load_json_items(path)) for path in json_files.get("top100_json", [])] or [0])


def top100_json_complete(json_files: dict[str, list[str]]) -> bool:
    return any(len(load_json_items(path)) >= 100 for path in json_files.get("top100_json", []))


def six_dim_json_complete(json_files: dict[str, list[str]]) -> bool:
    field_sets = [
        {"D1", "D2", "D3", "D4", "D5", "D6"},
        {"theme", "catalyst", "industry_logic", "position", "tape_quality", "tomorrow_check"},
        {"题材归属", "事件催化", "产业逻辑", "个股地位", "盘口质量", "明日验证点"},
    ]
    for path in json_files.get("top100_json", []) + json_files.get("reason_6d_json", []):
        items = load_json_items(path)
        if not items:
            continue
        coverage = 0
        for item in items:
            keys = set(item.keys())
            if any(required.issubset(keys) for required in field_sets) or item_has_reason_source_fields(item):
                coverage += 1
        if coverage >= min(20, len(items)):
            return True
    return False


def ladder_taxonomy_json_complete(json_files: dict[str, list[str]]) -> bool:
    for rel_path in json_files.get("ladder_json", []):
        try:
            data = json.loads((ROOT / rel_path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        summary = data.get("summary")
        if isinstance(summary, dict) and {"continuous", "nDayMBoard", "rebound", "trend_new_high"}.issubset(summary.keys()):
            return True
        all_items = []
        for value in data.values():
            if isinstance(value, list):
                all_items.extend(item for item in value if isinstance(item, dict))
        if all_items and all("type" in item for item in all_items[: min(20, len(all_items))]):
            return True
    return False


def add_issue(issues: list[dict], severity: str, code: str, message: str, action: str) -> None:
    issues.append(
        {
            "severity": severity,
            "code": code,
            "message": message,
            "action": action,
        }
    )


def evaluate(trade_date: str) -> dict:
    raw_path = RAW_REVIEW_DIR / f"{trade_date}-复盘.md"
    issues: list[dict] = []
    warnings: list[dict] = []

    if not raw_path.exists():
        add_issue(
            issues,
            "critical",
            "missing_review",
            f"未找到龙虾复盘 RAW：{raw_path.relative_to(ROOT)}",
            "请龙虾先写入 raw/02-每日复盘/YYYY-MM-DD-复盘.md",
        )
        return {
            "ok": False,
            "trade_date": trade_date,
            "raw_review": str(raw_path.relative_to(ROOT)),
            "score": 0,
            "grade": "FAIL",
            "issues": issues,
            "warnings": warnings,
            "generated_at": now_text(),
        }

    text = read_text(raw_path)
    ladder = section(text, "## 七、连板天梯")
    top100 = section(text, "## 七补、通达信热榜 Top100")
    user_oral = section(text, "## 八、用户口述原文")
    trade_section = section(text, "## 四、今日实际交易")
    dplus_section = section(text, "## 十一、D+验证任务")

    stock_codes_ladder = unique_stock_codes(ladder)
    ladder_market_counts = market_prefix_counts(stock_codes_ladder)
    ladder_rows = table_row_count(ladder)
    top100_rows = table_row_count(top100)
    json_files = find_json_files(trade_date)
    json_scope = json_market_scope_metrics(json_files)
    ladder_board = ladder_board_metrics(json_files)
    top100_json_rows = top100_json_max_rows(json_files)
    top100_complete = top100_rows >= 100 or top100_json_complete(json_files)
    six_dim_complete = six_dim_json_complete(json_files)
    ladder_taxonomy_complete = ladder_taxonomy_json_complete(json_files)
    first_board_raw_present = bool(json_files["first_board_json"] or json_files["first_board_md"])
    panorama_present = bool(json_files["panorama_json"] or json_files["panorama_md"])
    board_strength_present = bool(json_files["board_strength_json"] and json_files["board_strength_md"])
    board_metrics = board_field_metrics(json_files)
    st_metrics = st_detail_metrics(json_files)

    if "writer: longxia" not in text:
        add_issue(issues, "critical", "missing_writer", "头部缺 writer: longxia。", "补 YAML 头部字段。")
    if "needs_codex_followup: true" not in text:
        add_issue(issues, "critical", "missing_followup", "头部缺 needs_codex_followup: true，可能无法触发 Codex 接力。", "补 YAML 头部字段。")

    if not trade_section or table_row_count(trade_section) == 0:
        add_issue(issues, "critical", "missing_trades", "没有逐笔交易表。", "补每笔成交/撤单、价格、数量、用户口述理由。")
    if not user_oral or len(user_oral.strip()) < 80:
        add_issue(issues, "major", "weak_user_oral", "用户飞书口述原文不足或未完整保留。", "补飞书原话，不要改写。")

    if not ladder and not json_files["ladder_json"]:
        add_issue(issues, "critical", "missing_ladder", "缺少连板天梯章节。", "补完整剔除 ST 后的连板天梯。")
    elif ladder_rows == 0 and ladder_board["ladder_2plus_count"] == 0:
        add_issue(
            issues,
            "critical",
            "missing_2plus_ladder_items",
            "连板天梯未识别到 2板及以上股票。",
            "连板天梯只写 2板及以上；若当天确无 2板及以上，必须在 summary 里明写 0 和数据源口径。",
        )

    if ladder_board["ladder_first_board_count"] > 0:
        add_issue(
            issues,
            "critical",
            "first_board_mixed_into_ladder",
            f"连板天梯 JSON 混入首板 {ladder_board['ladder_first_board_count']} 只。",
            "把首板移出连板天梯，单独写入首板涨停催化日报。",
        )

    if ladder and re.search(r"(?m)^\s*#{3,}.*首板|^\s*\|.*首板.*\|", ladder):
        add_issue(
            issues,
            "critical",
            "first_board_section_in_ladder",
            "连板天梯章节里仍有首板小节或首板表格。",
            "首板只能进入独立的首板涨停催化日报，复盘天梯段只保留 2板及以上情绪锚。",
        )

    if not first_board_raw_present:
        add_issue(
            issues,
            "critical",
            "missing_first_board_catalyst_raw",
            "未发现每日首板涨停催化日报 RAW。",
            "单独补 raw/04-市场数据/首板涨停催化/YYYY-MM-DD/tdx-first-board-catalyst.json 或 .md。",
        )
    if not panorama_present:
        add_issue(
            warnings,
            "warning",
            "missing_limit_up_panorama",
            "未发现每日涨停全景总表。",
            "补 raw/04-市场数据/每日涨停全景/YYYY-MM-DD/tdx-limit-up-panorama.json 或 .md，首板和2板以上都放在一个总入口里。",
        )
    if not board_strength_present:
        add_issue(
            issues,
            "critical",
            "missing_board_strength",
            "未发现板块强度 JSON/MD。",
            "补 raw/04-市场数据/板块强度/YYYY-MM-DD/通达信板块强度.json 和 .md，用于 D+跑赢板块验证。",
        )
    if st_metrics["st_detail_count"] > 0:
        add_issue(
            issues,
            "critical",
            "st_details_should_be_excluded",
            f"发现 ST 明细字段：{'; '.join(st_metrics['st_detail_preview'])}。",
            "按最新口径，ST 直接剔除，不写明细、不单列、不补全。",
        )
    elif board_metrics["board_strength_rows"] and board_metrics["board_strength_rows"] < 100:
        add_issue(
            issues,
            "major",
            "board_strength_too_few",
            f"板块强度 JSON 只有 {board_metrics['board_strength_rows']} 条，低于 Top100 底线。",
            "板块强度优先全量；接口受限最低 Top100。Top50 只允许作为临时缺口，并必须说明原因。",
        )
    if board_metrics["checked_stock_items"] and board_metrics["board_fields_missing"] > 0:
        add_issue(
            issues,
            "critical",
            "stock_board_fields_incomplete",
            f"个股板块字段未全覆盖：{board_metrics['board_fields_covered']}/{board_metrics['checked_stock_items']}。",
            "每日涨停全景、首板催化、连板天梯、涨停原因、热榜 JSON 每只票都必须带交易题材、主板块、板块来源、概念标签、板块归属证据。",
        )

    if not has_any(text, ["Top100 必须", "通达信热榜 Top100", "tdx-hot-top100"]) and not top100_complete:
        add_issue(issues, "critical", "missing_top100", "没有通达信热榜 Top100 全量要求或正文。", "补 Top100 全量表或附录。")
    elif top100_rows and top100_rows < 100 and not top100_complete:
        add_issue(issues, "critical", "top100_incomplete", f"Top100 表不足 100 行，识别到 {top100_rows} 行。", "补齐 Top100。")
    elif not top100_complete:
        add_issue(issues, "major", "top100_not_structured", "未发现 Top100 正文表，也未发现 Top100 JSON。", "补正文 Top100 或 tdx-hot-top100.json。")
    elif not top100_rows:
        add_issue(warnings, "warning", "top100_not_embedded", "Top100 JSON 已完整，但每日复盘正文/附录未嵌入 Top100。", "后续最好把 Top100 正文或附录也补进复盘。")

    if not has_any(text, ["连续涨停", "N日M板", "反包板", "趋势新高板"]) and not ladder_taxonomy_complete:
        add_issue(
            issues,
            "major",
            "mixed_board_taxonomy",
            "未明确区分连续涨停、N日M板、反包板、趋势新高板。",
            "龙虾需要把连板口径拆开，避免 3连板 和 5天3板 混用。",
        )

    if (
        json_scope["meta_non_st"]
        and json_scope["ladder_json_items"]
        and json_scope["ladder_json_items"] < int(json_scope["meta_non_st"] * 0.8)
        and "2板" not in json_scope.get("meta_selection_rule", "")
    ):
        add_issue(
            warnings,
            "warning",
            "ladder_json_not_full",
            f"连板 JSON 只有 {json_scope['ladder_json_items']} 条，但 meta.non_st={json_scope['meta_non_st']}，口径可能仍按全部涨停写。",
            "连板天梯 JSON 的 selection_rule 必须写清只包含 2板及以上；首板另走首板催化日报。",
        )

    if has_any(text, ["真经连板", "一根独苗"]) and len(stock_codes_ladder) >= 20:
        add_issue(
            warnings,
            "warning",
            "possible_ladder_contradiction",
            "文本出现“真经连板/一根独苗”等摘要，但后文又列出大量高位和连板票，可能存在口径冲突。",
            "在摘要处解释连续板、N日M板、反包板的区别。",
        )

    limit_counts = [int(n) for n in re.findall(r"涨停[（/ 0-9A-Za-z\u4e00-\u9fff]*?\|?\s*(\d{2,3})", text[:2500])]
    title_counts = [int(n) for n in re.findall(r"(\d{2,3})只涨停", ladder[:300])]
    if limit_counts and title_counts and abs(max(limit_counts) - max(title_counts)) >= 20:
        add_issue(
            warnings,
            "warning",
            "limit_count_gap",
            f"涨停数量口径可能不一致：前文最大 {max(limit_counts)}，天梯标题 {max(title_counts)}。",
            "解释剔除 ST 后的全市场涨停、主板10cm、创业板20cm、科创板20cm、北交所30cm统计口径。",
        )

    if ladder and not has_any(ladder, ["主板", "创业板", "科创板", "北交所", "北证", "10cm", "20cm", "30cm"]) and not json_scope["scope_declared"]:
        add_issue(
            warnings,
            "warning",
            "market_scope_not_labeled",
            "天梯有股票代码，但没有明确标注主板/创业板20cm/科创板20cm/北交所30cm市场范围。",
            "在 7.1 总览增加主板10cm数量、创业板20cm数量、科创板20cm数量、北交所30cm数量。",
        )
    if (
        ladder_market_counts["gem_20cm"]
        or ladder_market_counts["star_20cm"]
        or json_scope["market_counts"]["gem_20cm"]
        or json_scope["market_counts"]["star_20cm"]
    ) and "20cm" not in ladder and not json_scope["scope_declared"]:
        add_issue(
            warnings,
            "warning",
            "twenty_cm_not_labeled",
            "天梯里已有创业板/科创板代码，但没有显式标注 20cm 口径。",
            "20cm 票必须在市场和涨停幅度列中明确标注。",
        )
    if ladder_market_counts["bse_30cm"] == 0 and not has_any(ladder, ["北交所", "北证", "bse_30cm", "北交所30cm数量"]) and not json_scope["bse_declared"]:
        add_issue(
            warnings,
            "warning",
            "bse_scope_not_declared",
            "天梯没有北交所代码，也没有声明北交所当日为 0 或数据缺口。",
            "若北交所无涨停，写“北交所30cm数量：0”；若数据源未覆盖，写数据缺口。",
        )

    six_dim_terms = ["题材归属", "事件催化", "产业逻辑", "个股地位", "盘口质量", "明日验证点"]
    six_dim_hits = sum(1 for term in six_dim_terms if term in text)
    if ladder_board["ladder_2plus_count"] and ladder_board["ladder_2plus_6d_missing"]:
        missing_preview = "、".join(ladder_board["ladder_2plus_6d_missing"][:12])
        add_issue(
            issues,
            "critical",
            "ladder_2plus_reason_source_incomplete",
            f"2板及以上天梯票事实源未全覆盖：有效覆盖 {ladder_board['ladder_2plus_effective_fact_covered']}/{ladder_board['ladder_2plus_count']}，缺 {missing_preview}。",
            "每只 2板及以上必须有原始涨停原因、板型/封单/开板/成交额/换手/来源等事实字段；6维分析由 Codex Pro 生成。",
        )
    elif ("六维" not in text and "6 维" not in text) and not six_dim_complete:
        add_issue(issues, "major", "missing_reason_source_marker", "未标注涨停原因事实源。", "2板及以上连板票必须提供原始涨停原因和盘口事实字段。")
    elif six_dim_hits < 4 and not six_dim_complete:
        add_issue(
            issues,
            "major",
            "weak_reason_source_fields",
            f"涨停原因事实源字段不足，旧6维字段命中 {six_dim_hits}/6，且事实源不完整。",
            "补原始涨停原因、板型、封单、开板、成交额、换手、来源；Codex Pro 再做6维分析。",
        )

    if not dplus_section or table_row_count(dplus_section) == 0:
        add_issue(issues, "major", "missing_dplus", "缺少 D+验证任务表。", "补核心候选 D+1/D+3/D+5 验证点。")

    if not json_files["ladder_json"]:
        add_issue(warnings, "warning", "missing_ladder_json", "未发现连板天梯 JSON。", "补 tdx-limit-ladder.json，便于 Codex 训练。")
    if not json_files["reason_6d_json"]:
        add_issue(warnings, "warning", "missing_reason_json", "未发现涨停原因事实源 JSON。", "补 tdx-limit-reasons-source.json 或兼容 tdx-limit-reasons-6d.json。")
    if not json_files["top100_json"]:
        add_issue(warnings, "warning", "missing_top100_json", "未发现 Top100 JSON。", "补 tdx-hot-top100.json。")
    if not json_files["first_board_json"]:
        add_issue(warnings, "warning", "missing_first_board_json", "未发现首板涨停催化 JSON。", "首板日报最好同步写结构化 JSON，便于次日漏判验证。")

    score = 100
    for issue in issues:
        score -= 30 if issue["severity"] == "critical" else 15
    score -= min(15, len(warnings) * 5)
    score = max(0, score)
    grade = "PASS" if score >= 80 and not any(i["severity"] == "critical" for i in issues) else "NEEDS_FIX"
    if score < 60 or any(i["severity"] == "critical" for i in issues):
        grade = "FAIL"

    return {
        "ok": grade == "PASS",
        "trade_date": trade_date,
        "raw_review": str(raw_path.relative_to(ROOT)),
        "score": score,
        "grade": grade,
        "metrics": {
            "review_lines": len(text.splitlines()),
            "ladder_table_rows": ladder_rows,
            "ladder_unique_stock_codes": len(stock_codes_ladder),
            "ladder_market_counts": ladder_market_counts,
            "top100_table_rows": top100_rows,
            "top100_json_rows": top100_json_rows,
            "six_dim_field_hits": six_dim_hits,
            "reason_source_covered": ladder_board.get("ladder_2plus_reason_source_covered", 0),
            "effective_fact_covered": ladder_board.get("ladder_2plus_effective_fact_covered", 0),
            "json_files": json_files,
            "json_market_scope": json_scope,
            "ladder_board_metrics": ladder_board,
            "first_board_raw_present": first_board_raw_present,
            "panorama_present": panorama_present,
            "top100_json_complete": top100_complete,
            "reason_source_json_complete": six_dim_complete,
            "ladder_taxonomy_json_complete": ladder_taxonomy_complete,
            "board_strength_present": board_strength_present,
            "board_field_metrics": board_metrics,
            "st_detail_metrics": st_metrics,
        },
        "issues": issues,
        "warnings": warnings,
        "generated_at": now_text(),
    }


def markdown_report(result: dict) -> str:
    trade_date = result["trade_date"]
    lines = [
        f"# {trade_date} 龙虾复盘 RAW 质量验收",
        "",
        f"生成时间：{result['generated_at']}",
        "",
        "## 结论",
        "",
        f"- 等级：{result['grade']}",
        f"- 分数：{result['score']}/100",
        f"- RAW：`{result['raw_review']}`",
        "",
        "## 指标",
        "",
    ]
    metrics = result.get("metrics", {})
    for key, value in metrics.items():
        if key == "json_files":
            continue
        lines.append(f"- `{key}`: {value}")
    if metrics.get("json_files"):
        lines.extend(["", "## 结构化 JSON"])
        for key, files in metrics["json_files"].items():
            lines.append(f"- `{key}`: {', '.join(files) if files else '缺失'}")

    lines.extend(["", "## 必须修正"])
    if result["issues"]:
        for item in result["issues"]:
            lines.append(f"- [{item['severity']}] {item['message']} 处理：{item['action']}")
    else:
        lines.append("- 无")

    lines.extend(["", "## 警告"])
    if result["warnings"]:
        for item in result["warnings"]:
            lines.append(f"- [{item['severity']}] {item['message']} 处理：{item['action']}")
    else:
        lines.append("- 无")

    return "\n".join(lines) + "\n"


def feishu_text(result: dict) -> str:
    trade_date = result["trade_date"]
    problems = result["issues"] or result["warnings"]
    lines = [
        f"龙虾，{trade_date} 复盘 RAW 质量验收未通过：",
        f"等级：{result['grade']}，分数：{result['score']}/100",
        "",
        "需要补的硬项：",
    ]
    if not problems:
        lines.append("无")
    else:
        for idx, item in enumerate(problems[:8], start=1):
            lines.append(f"{idx}. {item['message']} 处理：{item['action']}")
    lines.extend(
        [
            "",
            f"请补到：raw/02-每日复盘/{trade_date}-复盘.md",
            "重点：Top100 全量、首板事实源单独 RAW、2板及以上连板天梯、每只连板票原始涨停原因和盘口字段、结构化 JSON、可验证事实字段。6维分析由 Codex Pro 做。",
        ]
    )
    return "\n".join(lines) + "\n"


def action_plan_markdown(result: dict) -> str:
    trade_date = result["trade_date"]
    metrics = result.get("metrics", {})
    lines = [
        f"# {trade_date} 龙虾复盘补交任务单",
        "",
        f"生成时间：{result['generated_at']}",
        f"质量等级：{result['grade']}，分数：{result['score']}/100",
        f"RAW：`{result['raw_review']}`",
        "",
        "## 补交优先级",
        "",
    ]
    problems = result.get("issues", []) + result.get("warnings", [])
    if not problems:
        lines.append("- 无。")
    else:
        for idx, item in enumerate(problems, start=1):
            severity = item.get("severity", "")
            lines.append(f"{idx}. [{severity}] {item.get('code', '')}：{item.get('message', '')}")
            lines.append(f"   - 补法：{item.get('action', '')}")
    lines.extend(
        [
            "",
            "## 机器验收字段",
            "",
            f"- Top100 JSON 完整：{metrics.get('top100_json_complete')}",
            f"- 首板催化日报已单独写 RAW：{metrics.get('first_board_raw_present')}",
            f"- 连板天梯 JSON 口径完整：{metrics.get('ladder_taxonomy_json_complete')}",
            f"- 涨停原因事实源 JSON 完整：{metrics.get('reason_source_json_complete')}",
            f"- Top100 正文行数：{metrics.get('top100_table_rows')}",
            f"- 天梯正文行数：{metrics.get('ladder_table_rows')}",
            f"- 旧6维字段命中：{metrics.get('six_dim_field_hits')}/6",
            f"- 事实源覆盖：{metrics.get('effective_fact_covered')}",
            "",
            "## 龙虾必须补齐的标准",
            "",
            "- `writer: longxia`",
            "- `needs_codex_followup: true`",
            "- 通达信热榜 Top100 全量正文或 `tdx-hot-top100.json`",
            "- 首板涨停事实源单独写 RAW，不能塞进连板天梯",
            "- 剔除 ST 后的连板天梯只包含 2板及以上，明确连续涨停、N日M板、反包板、趋势新高板",
            "- 北交所/创业板/科创板/主板涨停口径分列；无则写 0，缺数据则写数据缺口",
            "- 每只 2板及以上连板票必须有原始涨停原因、板型、封单、开板、成交额、换手、来源、主板块等事实字段",
            "- 可用于 Codex Pro 生成 D+1/D+3/D+5 验证任务的事实字段",
        ]
    )
    return "\n".join(lines) + "\n"


def append_issue_queue(result: dict) -> None:
    if result["grade"] == "PASS":
        return
    record = {
        "schema": "73wiki-longxia-review-quality-issue-v1",
        "trade_date": result["trade_date"],
        "generated_at": result["generated_at"],
        "grade": result["grade"],
        "score": result["score"],
        "raw_review": result["raw_review"],
        "issue_codes": [item.get("code") for item in result.get("issues", [])],
        "warning_codes": [item.get("code") for item in result.get("warnings", [])],
        "report": f"wiki/09-统计与进化/{result['trade_date']}-龙虾复盘RAW质量验收.md",
        "action_plan": f"wiki/09-统计与进化/{result['trade_date']}-龙虾复盘补交任务单.md",
    }
    seen_key = json.dumps(
        {
            "trade_date": record["trade_date"],
            "grade": record["grade"],
            "score": record["score"],
            "issue_codes": record["issue_codes"],
            "warning_codes": record["warning_codes"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    existing = set()
    if QUALITY_ISSUE_QUEUE.exists():
        for line in QUALITY_ISSUE_QUEUE.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            existing.add(
                json.dumps(
                    {
                        "trade_date": item.get("trade_date"),
                        "grade": item.get("grade"),
                        "score": item.get("score"),
                        "issue_codes": item.get("issue_codes", []),
                        "warning_codes": item.get("warning_codes", []),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
    if seen_key in existing:
        return
    with QUALITY_ISSUE_QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_outputs(result: dict) -> None:
    trade_date = result["trade_date"]
    SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    FEISHU_PENDING_DIR.mkdir(parents=True, exist_ok=True)

    (SYSTEM_DIR / f"longxia-review-quality-{trade_date}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (REPORT_DIR / f"{trade_date}-龙虾复盘RAW质量验收.md").write_text(
        markdown_report(result),
        encoding="utf-8",
    )
    (REPORT_DIR / f"{trade_date}-龙虾复盘补交任务单.md").write_text(
        action_plan_markdown(result),
        encoding="utf-8",
    )
    append_issue_queue(result)
    pending_path = FEISHU_PENDING_DIR / f"{trade_date}-龙虾复盘质量提醒.md"
    if result["grade"] == "PASS":
        pending_path.unlink(missing_ok=True)
    else:
        pending_path.write_text(
            feishu_text(result),
            encoding="utf-8",
        )
        maybe_notify_macos(result)
        maybe_send_feishu_pending()


def issue_signature(result: dict) -> str:
    parts = [
        result.get("trade_date", ""),
        result.get("grade", ""),
        str(result.get("score", "")),
    ]
    for item in result.get("issues", []):
        parts.append(item.get("code", ""))
    for item in result.get("warnings", []):
        parts.append(item.get("code", ""))
    return "|".join(parts)


def maybe_notify_macos(result: dict) -> None:
    if os.environ.get("LONGXIA_QUALITY_MAC_NOTIFY", "1") == "0":
        return
    signature = issue_signature(result)
    state = {}
    try:
        state = json.loads(NOTIFIED_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if state.get(result["trade_date"]) == signature:
        return

    title = "龙虾复盘质量未通过"
    message = f"{result['trade_date']} {result['grade']} {result['score']}/100，请看飞书待发文案。"
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except Exception:
        pass
    state[result["trade_date"]] = signature
    NOTIFIED_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def maybe_send_feishu_pending() -> None:
    if os.environ.get("LONGXIA_QUALITY_FEISHU_SEND", "1") == "0":
        return
    sender = SYSTEM_DIR / "scripts/send-feishu-pending-notifications.py"
    if not sender.exists():
        return
    try:
        subprocess.run(
            [sys.executable, str(sender)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    result = evaluate(args.date)
    if args.write:
        write_outputs(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["grade"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
