#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path("/Users/qixinchaye/wiki/73神话")
CONFIG = ROOT / ".system/taoguba-contest-watchlist.json"
PLAYER_POOL = ROOT / ".system/taoguba-contest-player-pool.json"
RAW_ROOT = ROOT / "raw/09-短线知识/淘股吧实盘赛"
ANALYSIS_ROOT = ROOT / "raw/11-Codex分析产物/短线知识提炼"
VALIDATION_QUEUE = ROOT / "wiki/09-统计与进化/淘股吧实盘赛高手样本验证队列.md"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Referer": "https://www.tgb.cn/",
}

KEYWORDS = ["千万组", "持有", "买入", "卖出", "今日盈亏", "总收益", "交割单", "实盘", "比赛", "梦想杯", "创世纪", "镀金"]


def today() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def slug(value: str) -> str:
    parsed = urlparse(value)
    raw = (parsed.netloc + "-" + parsed.path.strip("/")).strip("-") or "source"
    raw = re.sub(r"[^0-9A-Za-z._-]+", "-", raw)
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{raw[:70]}-{digest}"


def fetch_text(url: str, timeout: int = 30) -> tuple[str, int]:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return body, getattr(resp, "status", 0)


def html_to_text(markup: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", markup)
    text = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</tr>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def urls_from_config(config: dict) -> list[dict]:
    result = []
    for source in config.get("公开信息源") or []:
        url = source.get("url")
        if url:
            result.append({"name": source.get("名称") or url, "url": url, "priority": source.get("优先级") or ""})
    for item in config.get("当前已知样本页") or []:
        url = item.get("url")
        if url:
            result.append({"name": item.get("标题") or url, "url": url, "priority": "P1"})
    seen = set()
    unique = []
    for item in result:
        if item["url"] not in seen:
            unique.append(item)
            seen.add(item["url"])
    return unique


def extract_relevant_lines(text: str, window: int = 1) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    hits = []
    for idx, line in enumerate(lines):
        if any(word in line for word in KEYWORDS):
            start = max(0, idx - window)
            end = min(len(lines), idx + window + 1)
            block = " / ".join(lines[start:end])
            if block not in hits:
                hits.append(block[:1200])
    return hits[:80]


def extract_players_from_line(line: str, source: dict) -> list[dict]:
    players = []
    rank_patterns = [
        r"千万组第\s*([一二三四五六七八九十\d]+)\s*名\s*@?([A-Za-z0-9_\-\u4e00-\u9fa5]{2,24})",
        r"千万组\s*([一二三四五六七八九十\d]+)\s*[、.．:：]\s*@?([A-Za-z0-9_\-\u4e00-\u9fa5]{2,24})",
    ]
    for pattern in rank_patterns:
        for match in re.finditer(pattern, line):
            rank_raw, name = match.groups()
            players.append(
                {
                    "采集日期": "",
                    "比赛日期": "",
                    "主办方": "待从来源页复核",
                    "比赛名称": source["name"],
                    "选手": name.strip(),
                    "选手主页": "",
                    "分组": "千万组",
                    "组内排名原文": rank_raw,
                    "组内排名": cn_rank_to_int(rank_raw),
                    "排名口径": "千万组组内排名",
                    "排名证据URL": source["url"],
                    "来源名称": source["name"],
                    "证据片段": line,
                    "是否千万组前10": (cn_rank_to_int(rank_raw) or 999) <= 10,
                    "公开资料完整度": completeness(line),
                    "持有": extract_after(line, "持有"),
                    "买入": extract_after(line, "买入"),
                    "卖出": extract_after(line, "卖出"),
                    "仓位变化": "",
                    "交割单证据": source["url"],
                    "今日盈亏": extract_metric(line, "今日盈亏"),
                    "总收益": extract_metric(line, "总收益"),
                    "公开交割单字段": build_trade_fields(line, source),
                    "每日分享字段": build_share_fields(line, source),
                    "D+验证字段": build_dplus_fields(),
                    "样本偏差": "公开页文本抽取，仍需复核主办方、比赛名称、千万组口径和买卖字段完整性。",
                    "模式初判": guess_mode(line),
                }
            )
    return players


def build_trade_fields(line: str, source: dict) -> dict:
    hold = extract_after(line, "持有")
    buy = extract_after(line, "买入")
    sell = extract_after(line, "卖出")
    gaps = []
    if not hold:
        gaps.append("持有缺失")
    if not buy:
        gaps.append("买入缺失")
    if not sell:
        gaps.append("卖出缺失")
    if "？" in buy or "?" in buy:
        gaps.append("买入为问号")
    return {
        "持有": hold,
        "买入": buy,
        "卖出": sell,
        "仓位变化": "",
        "交割单证据": source["url"],
        "字段缺口": gaps,
    }


def build_share_fields(line: str, source: dict) -> dict:
    return {
        "观点原文": line[:1200],
        "观点摘要": "",
        "题材判断": "",
        "风险态度": "空仓" if "空仓" in line or "持有：无" in line else "",
        "是否空仓": "是" if "持有：无" in line else "待判断",
        "来源URL": source["url"],
    }


def build_dplus_fields() -> dict:
    return {
        "D+1": "待验证",
        "D+3": "待验证",
        "D+5": "待验证",
        "验证指标": ["个股涨跌幅", "是否跑赢指数", "板块强弱", "是否按预判走"],
        "验证状态": "待入队",
        "最终结论": "待回填",
    }


def dedupe_players(players: list[dict]) -> list[dict]:
    merged: dict[tuple[str, int | None, str], dict] = {}
    for player in players:
        key = (player.get("选手") or "", player.get("组内排名"), player.get("排名证据URL") or "")
        if key not in merged:
            merged[key] = {**player}
            continue
        current = merged[key]
        for field in ("持有", "买入", "卖出", "今日盈亏", "总收益"):
            if not current.get(field) and player.get(field):
                current[field] = player[field]
            elif current.get(field) and player.get(field) and player[field] not in current[field]:
                current[field] = (current[field] + "；" + player[field])[:800]
        grade_rank = {"A": 4, "B": 3, "C": 2, "D": 1}
        if grade_rank.get(player.get("公开资料完整度") or "D", 1) > grade_rank.get(current.get("公开资料完整度") or "D", 1):
            current["公开资料完整度"] = player.get("公开资料完整度")
        modes = sorted(set((current.get("模式初判") or []) + (player.get("模式初判") or [])))
        current["模式初判"] = modes
        if player.get("证据片段") and player["证据片段"] not in current.get("证据片段", ""):
            current["证据片段"] = (current.get("证据片段", "") + " / " + player["证据片段"])[:1600]
    return list(merged.values())


def cn_rank_to_int(value: str) -> int | None:
    value = value.strip()
    if value.isdigit():
        return int(value)
    mapping = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    if value in mapping:
        return mapping[value]
    if value.startswith("十") and len(value) == 2:
        return 10 + mapping.get(value[1:], 0)
    return None


def extract_after(line: str, key: str) -> str:
    match = re.search(rf"{re.escape(key)}[：:]\s*([^。；;\n]+)", line)
    return match.group(1).strip()[:240] if match else ""


def extract_metric(line: str, key: str) -> str:
    match = re.search(rf"{re.escape(key)}\s*[-+]?[\d.]+%?", line)
    return match.group(0).replace(key, "").strip() if match else ""


def completeness(line: str) -> str:
    score = sum(1 for key in ["持有", "买入", "卖出", "今日盈亏", "总收益", "交割单"] if key in line)
    if score >= 5:
        return "A"
    if score >= 3:
        return "B"
    if score >= 1:
        return "C"
    return "D"


def guess_mode(text: str) -> list[str]:
    rules = {
        "首板/打板": ["首板", "打板", "封板", "涨停"],
        "半路": ["半路", "冲高", "突破"],
        "低吸": ["低吸", "水下", "回踩", "分歧买"],
        "趋势": ["趋势", "容量", "中军", "机构"],
        "龙空龙": ["空仓", "龙空龙", "只做龙头"],
        "反包/修复": ["反包", "反核", "修复", "弱转强"],
        "套利": ["套利", "转债", "T+0", "做T"],
    }
    return [name for name, keys in rules.items() if any(key in text for key in keys)]


def merge_pool_candidates(players: list[dict], date: str) -> None:
    pool = read_json(PLAYER_POOL)
    official = pool.setdefault("正式跟踪", [])
    candidates = pool.setdefault("候选待复核", [])
    known = {(p.get("选手"), p.get("比赛"), p.get("排名证据")) for p in official + candidates}
    for player in players:
        if not player.get("是否千万组前10"):
            continue
        item = {
            "player_key": re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "-", player["选手"]).strip("-"),
            "选手": player["选手"],
            "淘股吧用户ID": "",
            "主页": "",
            "状态": "候选待复核",
            "主办方": "待从来源页复核",
            "比赛": player.get("来源名称") or "待复核",
            "分组": "千万组",
            "排名类型": "公开来源抽取",
            "组内排名": player.get("组内排名"),
            "排名日期": date,
            "排名证据": player.get("排名证据URL"),
            "公开资料完整度": player.get("公开资料完整度"),
            "重点观察": ["买卖点归因", "环境判断", "仓位变化"],
            "跟踪频率": "交易日每日",
            "样本偏差": "脚本从公开页文本抽取，仍需人工或后续页面交叉复核主办方、比赛名称和最终排名。"
        }
        key = (item["选手"], item["比赛"], item["排名证据"])
        if key not in known:
            candidates.append(item)
            known.add(key)
    PLAYER_POOL.write_text(json.dumps(pool, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_md(path: Path, title: str, lines: list[str]) -> None:
    path.write_text("# " + title + "\n\n" + "\n".join(lines).rstrip() + "\n", encoding="utf-8")


def append_validation_queue(date: str, players: list[dict], analysis_path: Path) -> None:
    VALIDATION_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    if not VALIDATION_QUEUE.exists():
        VALIDATION_QUEUE.write_text(
            "\n".join(
                [
                    "# 淘股吧实盘赛高手样本验证队列",
                    "",
                    "只跟踪白名单比赛千万组组内前10公开样本。没有排名证据的线索不能升级为正式模式。",
                    "",
                    "| 入队日期 | 选手 | 排名口径 | 动作/模式初判 | 证据 | D+1 | D+3 | D+5 | 结论 |",
                    "|---|---|---|---|---|---|---|---|---|",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    existing = VALIDATION_QUEUE.read_text(encoding="utf-8")
    emitted = set()
    with VALIDATION_QUEUE.open("a", encoding="utf-8") as f:
        for player in players:
            if not player.get("是否千万组前10"):
                continue
            modes = "、".join(player.get("模式初判") or []) or "待归因"
            line = (
                f"| {date} | {player.get('选手')} | 千万组第{player.get('组内排名')} | {modes} | "
                f"`{analysis_path.relative_to(ROOT)}` | 待验证 | 待验证 | 待验证 | 待回填 |\n"
            )
            if line not in existing and line not in emitted:
                f.write(line)
                emitted.add(line)


def run(date: str) -> dict:
    config = read_json(CONFIG)
    day_dir = RAW_ROOT / date
    sources_dir = day_dir / "sources"
    track_dir = day_dir / "选手轨迹"
    analysis_dir = ANALYSIS_ROOT / date
    for path in (sources_dir, track_dir, analysis_dir):
        path.mkdir(parents=True, exist_ok=True)

    source_index = []
    all_players = []
    all_lines = []
    for source in urls_from_config(config):
        source_slug = slug(source["url"])
        out_dir = sources_dir / source_slug
        out_dir.mkdir(parents=True, exist_ok=True)
        record = {**source, "slug": source_slug, "status": "pending"}
        try:
            markup, status = fetch_text(source["url"])
            text = html_to_text(markup)
            lines = extract_relevant_lines(text)
            (out_dir / "source.html").write_text(markup, encoding="utf-8")
            (out_dir / "source.txt").write_text(text + "\n", encoding="utf-8")
            write_md(out_dir / "抽取片段.md", source["name"], [f"- {line}" for line in lines] or ["- 未抽取到关键词片段。"])
            players = []
            for line in lines:
                players.extend(extract_players_from_line(line, source))
            all_players.extend(players)
            all_lines.extend([{"source": source, "line": line} for line in lines])
            record.update({"status": "ok", "http_status": status, "片段数": len(lines), "候选选手数": len(players)})
        except Exception as exc:
            record.update({"status": "error", "error": str(exc)})
        source_index.append(record)

    all_players = dedupe_players(all_players)
    for player in all_players:
        player["采集日期"] = date
        player.setdefault("比赛日期", "")
        player.setdefault("主办方", "待从来源页复核")
        player.setdefault("比赛名称", player.get("来源名称") or "")
        player.setdefault("选手主页", "")
        player.setdefault("公开交割单字段", build_trade_fields(player.get("证据片段") or "", {"url": player.get("排名证据URL") or ""}))
        player.setdefault("每日分享字段", build_share_fields(player.get("证据片段") or "", {"url": player.get("排名证据URL") or ""}))
        player.setdefault("D+验证字段", build_dplus_fields())
        player.setdefault("样本偏差", "公开页文本抽取，仍需复核主办方、比赛名称、千万组口径和买卖字段完整性。")

    sample = {
        "元数据": {
            "日期": date,
            "来源": "淘股吧公开实盘赛",
            "白名单配置": str(CONFIG.relative_to(ROOT)),
            "选手池": str(PLAYER_POOL.relative_to(ROOT)),
            "说明": "只从公开页保守抽取千万组排名线索；正式入池仍要求官方/主办方复核。",
            "阶段策略": "不先扩大到几百人，先做准比赛白名单、千万组前10选手池、公开交割单字段、每日分享字段、D+验证字段。",
        },
        "来源索引": source_index,
        "千万组前10候选样本": all_players,
        "抽取缺口": [
            "公开页可能只展示部分内容或需要浏览器渲染；若候选为空，需要用浏览器/Firecrawl补抓。",
            "脚本不会用全组排名、人气排名、博客排名替代千万组组内排名。",
            "未出现明确'千万组第N名'的片段只保留为RAW，不升级选手池。"
        ],
    }
    (day_dir / "source_index.json").write_text(json.dumps(source_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (day_dir / "结构化样本.json").write_text(json.dumps(sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "## 抓取概况",
        "",
        f"- 来源数：{len(source_index)}",
        f"- 成功数：{sum(1 for x in source_index if x.get('status') == 'ok')}",
        f"- 千万组前10候选样本：{len([p for p in all_players if p.get('是否千万组前10')])}",
        "",
        "## 候选选手",
        "",
    ]
    if all_players:
        for player in all_players:
            lines.append(f"- {player.get('选手')}：千万组第{player.get('组内排名')}，来源 {player.get('排名证据URL')}，模式初判 {'、'.join(player.get('模式初判') or []) or '待归因'}")
    else:
        lines.append("- 今日未从公开页文本中稳定抽取到“千万组第N名”候选，保留源文件等待浏览器/Firecrawl补抓。")
    write_md(day_dir / "高手行为摘录.md", f"{date} 淘股吧实盘赛高手行为摘录", lines)

    analysis_path = analysis_dir / "淘股吧千万组高手样本库-每日提炼.md"
    analysis_lines = [
        "## 今日处理结果",
        "",
        f"- RAW目录：`{day_dir.relative_to(ROOT)}`",
        f"- 来源数：{len(source_index)}",
        f"- 候选选手数：{len(all_players)}",
        "",
        "## 处理口径",
        "",
        "- 正式样本必须是白名单比赛 + 千万组组内前10 + 官方/主办方公开验证。",
        "- 本脚本只做公开源抓取和保守抽取，不把未复核线索写成事实。",
        "- 后续每个买卖动作必须与市场环境、主线、连板天梯、热榜和D+验证对照。",
        "",
        "## 待验证样本",
        "",
    ]
    if all_players:
        for player in all_players:
            analysis_lines.append(f"- {player.get('选手')}：证据 `{player.get('排名证据URL')}`；持有={player.get('持有') or '未抽取'}；买入={player.get('买入') or '未抽取'}；卖出={player.get('卖出') or '未抽取'}。")
    else:
        analysis_lines.append("- 暂无可升级样本。")
    write_md(analysis_path, f"{date} 淘股吧千万组高手样本库每日提炼", analysis_lines)

    merge_pool_candidates(all_players, date)
    append_validation_queue(date, all_players, analysis_path)
    return {"raw_dir": str(day_dir), "analysis": str(analysis_path), "sources": len(source_index), "players": len(all_players)}


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取淘股吧白名单实盘赛公开源，生成千万组高手样本RAW。")
    parser.add_argument("--date", default=today())
    args = parser.parse_args()
    print(json.dumps(run(args.date), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
