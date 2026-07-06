#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path("/Users/qixinchaye/wiki/73神话")
QUOTES_URL = "https://www.tgb.cn/quotes/"
HOT_POP_URL = "https://www.tgb.cn/search/hotPop"
DISCUSSION_URL = "https://www.tgb.cn/quotes/hotDiscussion"
HQ_URL = "https://hq.tgb.cn/tgb/realHQList"
POPULARITY_BOARD_URL = "https://www.tgb.cn/new/nrnt/toPopularityBoard?type=SP"
NOTICE_STOCK_URL = "https://www.tgb.cn/new/nrnt/getNoticeStock"
TALK_RANK_URL = "https://www.tgb.cn/new/nrnt/getTalkRank/1"
SPMATCH_INDEX_URL = "https://www.tgb.cn/spmatch/index/"
SPMATCH_HOT_STOCK_URL = "https://www.tgb.cn/spmatch/index/spIndexHotStock"
SPMATCH_SOCIAL_URL = "https://www.tgb.cn/spmatch/index/socilaList"
SPMATCH_INFO_URL = "https://www.tgb.cn/spmatch/index/getSpMatchInfoListIndex"


MODE_WORDS = [
    "首板", "半路", "低吸", "打板", "扫板", "排板", "反包", "弱转强", "反核",
    "龙头", "补涨", "中军", "容量", "趋势", "套利", "高切低", "卡位", "穿越",
    "分歧", "一致", "加速", "退潮", "修复", "回流", "承接", "兑现", "核按钮",
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": QUOTES_URL,
}


def now_cn() -> dt.datetime:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))


def http_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def http_json(url: str, params: dict | None = None, timeout: int = 25) -> dict:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    text = http_text(url, timeout=timeout)
    return json.loads(text)


def extract_js_array(page: str, var_name: str) -> list:
    pattern = rf"var\s+{re.escape(var_name)}\s*=\s*(\[.*?\])\s*;"
    match = re.search(pattern, page, flags=re.S)
    if not match:
        return []
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return []


def fetch_quotes_page() -> tuple[list, list, list]:
    page = http_text(QUOTES_URL)
    return (
        extract_js_array(page, "HotRank_inTime"),
        extract_js_array(page, "HotRank_Stock"),
        extract_js_array(page, "optionalList"),
    )


def fetch_hq(codes: list[str]) -> dict[str, dict]:
    if not codes:
        return {}
    params = {"stockCodeList": json.dumps(codes, ensure_ascii=False)}
    data = http_json(HQ_URL, params=params)
    if not data.get("status"):
        return {}
    result = {}
    for item in data.get("dto") or []:
        full_code = item.get("fullCode") or item.get("code")
        if full_code:
            result[full_code] = item
    return result


def normalize_stock_item(raw: dict, rank: int, board_name: str, hq: dict | None) -> dict:
    code = raw.get("tradeCode") or raw.get("keywordName") or ""
    name = raw.get("keyName") or raw.get("stockName") or raw.get("keywordName") or ""
    hq = hq or {}
    return {
        "排名": rank,
        "榜单": board_name,
        "代码": code,
        "名称": name,
        "淘股吧关键词ID": raw.get("keywordID"),
        "当前价": hq.get("price"),
        "涨跌额": hq.get("pxChange"),
        "涨跌幅": hq.get("pxChangeRate"),
        "成交额": hq.get("volumnPrice"),
        "换手率": hq.get("turnoverRate"),
        "连板标记": hq.get("linkingBoard"),
        "行情日期": hq.get("lastDate"),
        "行情时间": hq.get("lastTime"),
    }


def strip_tags(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value)))
    return re.sub(r"\s+", " ", text).strip()


def parse_hot_pop_table(page: str, title: str, board_name: str) -> list[dict]:
    start = page.find(title)
    if start < 0:
        return []
    end = page.find("</table>", start)
    if end < 0:
        return []
    block = page[start:end]
    rows = []
    for row in re.findall(r"<tr>\s*(.*?)\s*</tr>", block, flags=re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)
        if len(cells) < 6:
            continue
        rank_text = strip_tags(cells[0])
        if not rank_text.isdigit():
            continue
        name_match = re.search(r'data-hot-key="([^"]+)"', cells[1])
        code_match = re.search(r"/quotes/([a-z]{2}\d{6})", cells[1])
        keyword_match = re.search(r"keywordID=(\d+)", cells[5])
        trend = ""
        if "hotUp" in cells[2]:
            trend = "升温"
        elif "hotDown" in cells[2]:
            trend = "降温"
        rows.append(
            {
                "排名": int(rank_text),
                "榜单": board_name,
                "代码": code_match.group(1) if code_match else "",
                "名称": html.unescape(name_match.group(1)) if name_match else strip_tags(cells[1]),
                "淘股吧关键词ID": int(keyword_match.group(1)) if keyword_match else None,
                "热度趋势": trend or strip_tags(cells[2]),
                "今日搜索": strip_tags(cells[3]),
                "最近七日搜索": strip_tags(cells[4]),
                "当前价": None,
                "涨跌额": None,
                "涨跌幅": None,
                "成交额": None,
                "换手率": None,
                "连板标记": None,
                "行情日期": "",
                "行情时间": "",
            }
        )
    return rows


def fetch_hot_pop_stocks() -> tuple[list[dict], dict]:
    page = http_text(HOT_POP_URL)
    realtime = parse_hot_pop_table(page, "实时个股搜索热度", "实时个股搜索热度")
    day24 = parse_hot_pop_table(page, "24小时个股搜索热度", "24小时个股搜索热度")
    return realtime + day24, {
        "热门个股搜索热度条数": len(realtime) + len(day24),
        "热门个股搜索热度来源": HOT_POP_URL,
    }


def clean_text(value: str | None, limit: int = 240) -> str:
    if not value:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", "", str(value)))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def normalize_concepts(items: list | None) -> list[dict]:
    result = []
    for item in items or []:
        name = item.get("gnName") or item.get("概念名称")
        if not name:
            continue
        result.append({
            "概念ID": item.get("ztgnSeq") or item.get("gnSeq"),
            "概念名称": name,
        })
    return result


def normalize_notice_stock(raw: dict, board_name: str) -> dict:
    return {
        "排名": raw.get("ranking"),
        "榜单": board_name,
        "代码": raw.get("fullCode") or "",
        "名称": raw.get("stockName") or "",
        "淘股吧关键词ID": None,
        "当前价": None,
        "涨跌额": None,
        "涨跌幅": None,
        "成交额": None,
        "换手率": None,
        "连板标记": raw.get("linkingBoard") or "",
        "行情日期": "",
        "行情时间": "",
        "人气值": raw.get("popularValue"),
        "连续上榜": raw.get("continuenum"),
        "淘股吧关注理由": clean_text(raw.get("reason"), 360),
        "关联概念": normalize_concepts(raw.get("gnList")),
    }


def fetch_notice_stocks() -> tuple[list[dict], dict]:
    result = []
    counts = {}
    for type_code, board_name in (("H", "股票人气榜1小时"), ("D", "股票人气榜24小时")):
        data = http_json(NOTICE_STOCK_URL, params={"type": type_code})
        rows = data.get("dto") or []
        counts[f"{board_name}条数"] = len(rows)
        for row in rows:
            result.append(normalize_notice_stock(row, board_name))
    return result, {
        "股票人气榜来源": POPULARITY_BOARD_URL,
        **counts,
    }


def fetch_talk_rank() -> tuple[list[dict], dict]:
    data = http_json(TALK_RANK_URL)
    rows = (data.get("dto") or {}).get("list") or []
    result = []
    for idx, row in enumerate(rows, 1):
        result.append({
            "排名": idx,
            "话题ID": row.get("seq"),
            "话题": clean_text(row.get("talkName"), 120),
            "内容": clean_text(row.get("talkContent"), 500),
            "关注数": row.get("followNum"),
            "浏览数": row.get("viewNum"),
            "主帖数": row.get("topicNum"),
            "回复数": row.get("replyNum"),
            "说说数": row.get("shuoNum"),
            "话题类型": row.get("talkType"),
        })
    return result, {"话题榜条数": len(result), "话题榜来源": TALK_RANK_URL}


def fetch_spmatch_hot_buy() -> tuple[list[dict], dict]:
    data = http_json(SPMATCH_HOT_STOCK_URL, params={"flag": "B"})
    rows = data.get("dto") or []
    result = []
    for idx, row in enumerate(rows, 1):
        result.append({
            "排名": idx,
            "榜单": "实盘赛热门买入",
            "代码": row.get("stockCode") or "",
            "名称": row.get("stockName") or "",
            "买入人数": row.get("number"),
            "当前价": row.get("price"),
            "涨跌幅": row.get("yield"),
        })
    return result, {"实盘赛热门买入条数": len(result), "实盘赛热门买入来源": SPMATCH_HOT_STOCK_URL + "?flag=B"}


def fetch_spmatch_social(limit_pages: int = 2) -> tuple[list[dict], dict]:
    result = []
    for page_no in range(1, limit_pages + 1):
        data = http_json(SPMATCH_SOCIAL_URL, params={"pageNo": page_no, "type": 0})
        rows = (data.get("dto") or {}).get("list") or []
        if not rows:
            break
        for row in rows:
            topic_id = row.get("newTopicID")
            result.append({
                "排名": len(result) + 1,
                "帖子ID": row.get("topicID"),
                "新帖子ID": topic_id,
                "作者": row.get("userName"),
                "作者ID": row.get("userID"),
                "标题": clean_text(row.get("subject"), 180),
                "发帖时间": row.get("postDateStr"),
                "最后回复": row.get("lastReplyDateStr"),
                "浏览数": row.get("totalViewNum"),
                "回复数": row.get("totalReplyNum"),
                "点赞数": row.get("usefulNum"),
                "精选标记": row.get("bestFlag"),
                "实盘标记": row.get("dlFlag"),
                "链接": f"https://www.tgb.cn/a/{topic_id}" if topic_id else "",
            })
        time.sleep(0.2)
    return result, {"实盘赛社交热帖条数": len(result), "实盘赛社交热帖来源": SPMATCH_SOCIAL_URL}


def fetch_spmatch_info() -> tuple[list[dict], dict]:
    result = []
    type_names = {1: "报名中", 2: "进行中", 3: "已结束"}
    for type_num, type_name in type_names.items():
        data = http_json(SPMATCH_INFO_URL, params={"type": type_num})
        rows = (data.get("dto") or {}).get("list") or []
        for row in rows:
            result.append({
                "状态": type_name,
                "比赛ID": row.get("seq"),
                "比赛简称": row.get("simpleName"),
                "标题": clean_text(row.get("subject"), 160),
                "主办方": row.get("userName"),
                "主办方ID": row.get("userID"),
                "参赛人数": row.get("nowUserNum"),
                "比赛总资产": row.get("allMoneyStr") or row.get("allMoney"),
                "累计平均收益": row.get("allRate"),
                "比赛类型": row.get("spType"),
                "结束标记": row.get("endFlag"),
                "新帖ID": row.get("newTopicID"),
                "链接": f"https://www.tgb.cn/a/{row.get('newTopicID')}" if row.get("newTopicID") else "",
            })
        time.sleep(0.2)
    return result, {"官方比赛列表条数": len(result), "官方比赛列表来源": SPMATCH_INFO_URL}


def count_mode_words(text: str) -> list[dict]:
    counts = []
    for word in MODE_WORDS:
        count = len(re.findall(re.escape(word), text, flags=re.I))
        if count:
            counts.append({"模式词": word, "出现次数": count})
    return sorted(counts, key=lambda x: (-x["出现次数"], x["模式词"]))


def extract_related_discussions(page: str, limit: int = 20) -> list[dict]:
    result = []
    pattern = re.compile(
        r'<a class="related-body" href="([^"]+)".*?<span>(.*?)</span>.*?'
        r'<div class="quote_content related-topic">\s*<a href="([^"]+)".*?>(.*?)</a>：<span>(.*?)</span>',
        flags=re.S,
    )
    for match in pattern.finditer(page):
        result.append({
            "链接": html.unescape(match.group(1)),
            "摘要": clean_text(match.group(2), 220),
            "作者主页": html.unescape(match.group(3)),
            "作者": clean_text(match.group(4), 80),
            "评论": clean_text(match.group(5), 260),
        })
        if len(result) >= limit:
            break
    return result


def fetch_stock_detail(code: str, name: str) -> dict:
    url = f"https://www.tgb.cn/quotes/{code}"
    page = http_text(url, timeout=30)
    title_match = re.search(r"<title>(.*?)</title>", page, flags=re.S)
    text = strip_tags(page)
    return {
        "代码": code,
        "名称": name,
        "链接": url,
        "页面标题": clean_text(title_match.group(1), 160) if title_match else "",
        "讨论分类": [label for label in ["全部讨论", "研股", "复盘", "实盘", "方法论", "其他"] if label in page],
        "模式词计数": count_mode_words(text)[:20],
        "相关讨论摘录": extract_related_discussions(page, 20),
        "关注点摘录": [
            clean_text(text[max(0, idx - 80): idx + 180], 320)
            for idx in sorted({m.start() for word in MODE_WORDS for m in re.finditer(re.escape(word), text, flags=re.I)})[:20]
        ],
    }


def choose_detail_targets(stock_hotlists: list[dict], spmatch_hot_buy: list[dict], top_n: int) -> list[dict]:
    targets = []
    seen = set()
    priority_boards = {"股票人气榜1小时", "股票人气榜24小时", "实时热搜", "24小时热搜", "实盘赛热门买入"}
    for collection in (stock_hotlists, spmatch_hot_buy):
        for item in collection:
            code = item.get("代码") or ""
            name = item.get("名称") or ""
            if not re.match(r"^(sh|sz|bj)\d{6}$", code):
                continue
            if code in seen:
                continue
            if item.get("榜单") not in priority_boards:
                continue
            seen.add(code)
            targets.append({"代码": code, "名称": name, "来源榜单": item.get("榜单"), "来源排名": item.get("排名")})
            if len(targets) >= top_n:
                return targets
    return targets


def build_tgb_six_dim(stock_hotlists: list[dict], spmatch_hot_buy: list[dict], details: list[dict]) -> list[dict]:
    by_code: dict[str, dict] = {}
    for item in stock_hotlists:
        code = item.get("代码") or ""
        if not code:
            continue
        current = by_code.setdefault(code, {
            "代码": code,
            "名称": item.get("名称") or "",
            "热度来源": [],
            "淘股吧题材归属": [],
            "淘股吧关注理由": "",
            "社区模式词": [],
            "社区关注点": [],
            "实盘赛买入人数": None,
            "验证点": "",
        })
        current["名称"] = current["名称"] or item.get("名称") or ""
        current["热度来源"].append({"榜单": item.get("榜单"), "排名": item.get("排名")})
        if item.get("淘股吧关注理由") and not current["淘股吧关注理由"]:
            current["淘股吧关注理由"] = item.get("淘股吧关注理由")
        for concept in item.get("关联概念") or []:
            name = concept.get("概念名称")
            if name and name not in current["淘股吧题材归属"]:
                current["淘股吧题材归属"].append(name)
    for item in spmatch_hot_buy:
        code = item.get("代码") or ""
        current = by_code.setdefault(code, {
            "代码": code,
            "名称": item.get("名称") or "",
            "热度来源": [],
            "淘股吧题材归属": [],
            "淘股吧关注理由": "",
            "社区模式词": [],
            "社区关注点": [],
            "实盘赛买入人数": None,
            "验证点": "",
        })
        current["热度来源"].append({"榜单": "实盘赛热门买入", "排名": item.get("排名")})
        current["实盘赛买入人数"] = item.get("买入人数")
    for detail in details:
        current = by_code.get(detail.get("代码"))
        if not current:
            continue
        current["社区模式词"] = detail.get("模式词计数") or []
        points = []
        for raw_point in (detail.get("相关讨论摘录") or detail.get("关注点摘录") or [])[:5]:
            if isinstance(raw_point, dict):
                points.append(raw_point.get("摘要") or raw_point.get("评论") or str(raw_point))
            else:
                points.append(str(raw_point))
        current["社区关注点"] = points
    result = []
    for idx, item in enumerate(by_code.values(), 1):
        item["排名"] = idx
        item["验证点"] = "D+1看是否有溢价或负反馈；D+3看题材是否扩散；D+5看社区共识是否兑现或失效。"
        result.append(item)
    return result


def normalize_discussion(raw: dict, rank: int) -> dict:
    stocks = []
    for item in raw.get("stockAttr") or []:
        stocks.append({
            "代码": item.get("stockCode"),
            "名称": item.get("stockName"),
        })
    concepts = []
    for item in raw.get("ztGnAttr") or []:
        concepts.append({
            "概念ID": item.get("gnSeq"),
            "概念名称": item.get("gnName"),
        })
    topic = raw.get("tops") or {}
    r_id = raw.get("rID")
    other_id = raw.get("otherID")
    topic_id = raw.get("newTopicID")
    if raw.get("rType") == "T" and r_id:
        link = f"https://www.tgb.cn/Article/{r_id}/1"
    elif topic_id and r_id:
        link = f"https://www.tgb.cn/a/{topic_id}/{r_id}#{r_id}"
    elif other_id:
        link = f"https://www.tgb.cn/Article/{other_id}/1"
    else:
        link = ""
    return {
        "排名": rank,
        "作者": raw.get("userName"),
        "作者ID": raw.get("userID"),
        "类型": raw.get("rType"),
        "标记": raw.get("flag"),
        "时间": raw.get("actionDate"),
        "主题": clean_text(raw.get("subject"), 160),
        "摘要": clean_text(raw.get("body"), 260),
        "主帖作者": topic.get("userName"),
        "主帖标题": clean_text(topic.get("subject"), 160),
        "谈及股票": stocks,
        "谈及概念": concepts,
        "点赞数": raw.get("usefulNum"),
        "浏览数": raw.get("viewNum"),
        "评论数": raw.get("replyNum"),
        "链接": link,
        "原始ID": r_id,
    }


def fetch_hot_discussions(limit: int) -> tuple[list[dict], dict]:
    items = []
    page_no = 1
    page_num = None
    per_page = None
    while len(items) < limit:
        data = http_json(DISCUSSION_URL, params={"groupID": 0, "pageNo": page_no})
        dto = data.get("dto") or {}
        page_num = dto.get("pageNum", page_num)
        per_page = dto.get("perPageNum", per_page)
        rows = dto.get("list") or []
        if not rows:
            break
        for row in rows:
            if len(items) >= limit:
                break
            items.append(normalize_discussion(row, len(items) + 1))
        if page_num and page_no >= int(page_num):
            break
        page_no += 1
        time.sleep(0.2)
    meta = {"页数": page_num, "每页条数": per_page, "实际请求页数": page_no}
    return items, meta


def build_stock_hotlists() -> tuple[list[dict], dict]:
    realtime, day24, bars = fetch_quotes_page()
    all_codes = []
    for collection in (realtime, day24):
        all_codes.extend([item.get("tradeCode") for item in collection if item.get("tradeCode")])
    all_codes.extend([item.get("keywordName") for item in bars if item.get("keywordName")])
    hq = fetch_hq(sorted(set(all_codes)))

    result = []
    for idx, item in enumerate(realtime, 1):
        result.append(normalize_stock_item(item, idx, "实时热搜", hq.get(item.get("tradeCode"))))
    for idx, item in enumerate(day24, 1):
        result.append(normalize_stock_item(item, idx, "24小时热搜", hq.get(item.get("tradeCode"))))
    for idx, item in enumerate(bars, 1):
        result.append(normalize_stock_item(item, idx, "热门股吧", hq.get(item.get("keywordName"))))

    hot_pop, hot_pop_meta = fetch_hot_pop_stocks()
    result.extend(hot_pop)
    notice_stocks, notice_meta = fetch_notice_stocks()
    result.extend(notice_stocks)

    return result, {
        "实时热搜条数": len(realtime),
        "24小时热搜条数": len(day24),
        "热门股吧条数": len(bars),
        "公开页股票榜条数": len(result),
        **hot_pop_meta,
        **notice_meta,
    }


def aggregate_mentions(discussions: list[dict]) -> tuple[list[dict], list[dict]]:
    stock_counter: dict[tuple[str, str], int] = {}
    concept_counter: dict[str, int] = {}
    for item in discussions:
        seen_stocks = set()
        for stock in item.get("谈及股票") or []:
            key = (stock.get("代码") or "", stock.get("名称") or "")
            if key != ("", ""):
                seen_stocks.add(key)
        for key in seen_stocks:
            stock_counter[key] = stock_counter.get(key, 0) + 1
        seen_concepts = set()
        for concept in item.get("谈及概念") or []:
            name = concept.get("概念名称")
            if name:
                seen_concepts.add(name)
        for name in seen_concepts:
            concept_counter[name] = concept_counter.get(name, 0) + 1

    stocks = [
        {"排名": idx, "代码": code, "名称": name, "出现次数": count}
        for idx, ((code, name), count) in enumerate(
            sorted(stock_counter.items(), key=lambda kv: (-kv[1], kv[0][1]))[:100],
            1,
        )
    ]
    concepts = [
        {"排名": idx, "概念名称": name, "出现次数": count}
        for idx, (name, count) in enumerate(
            sorted(concept_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:50],
            1,
        )
    ]
    return stocks, concepts


def format_money(value) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:.2f}亿"
    if abs(number) >= 10_000:
        return f"{number / 10_000:.2f}万"
    return f"{number:.2f}"


def md_table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        safe = [str(cell).replace("\n", " ").replace("|", "/") if cell is not None else "" for cell in row]
        lines.append("| " + " | ".join(safe) + " |")
    return "\n".join(lines)


def write_markdown(path: Path, payload: dict) -> None:
    meta = payload["元数据"]
    stock_hotlists = payload["股票热榜"]
    discussions = payload["热门讨论100"]
    mention_stocks = payload["讨论提及股票排行"]
    mention_concepts = payload["讨论提及概念排行"]
    talk_rank = payload.get("话题榜") or []
    spmatch_hot_buy = payload.get("实盘赛热门买入") or []
    spmatch_social = payload.get("实盘赛社交热帖") or []
    spmatch_info = payload.get("官方比赛列表") or []
    stock_details = payload.get("热门个股详情TopN") or []
    tgb_six_dim = payload.get("淘股吧6维补充") or []

    lines = [
        f"# {meta['日期']} 淘股吧热榜100（{meta['时段']}）",
        "",
        "## 抓取概况",
        "",
        f"- 抓取时间：{meta['抓取时间']}",
        f"- 来源页面：{meta['来源页面']}",
        f"- 热门个股搜索热度页：{meta.get('热门个股搜索热度来源', '')}",
        f"- 热门讨论目标条数：{meta['目标条数']}",
        f"- 热门讨论实际条数：{meta['热门讨论实际条数']}",
        f"- 股票热榜公开页条数：{meta['公开页股票榜条数']}",
        f"- 热门个股搜索热度条数：{meta.get('热门个股搜索热度条数', 0)}",
        f"- 股票人气榜1小时条数：{meta.get('股票人气榜1小时条数', 0)}",
        f"- 股票人气榜24小时条数：{meta.get('股票人气榜24小时条数', 0)}",
        f"- 话题榜条数：{meta.get('话题榜条数', 0)}",
        f"- 实盘赛热门买入条数：{meta.get('实盘赛热门买入条数', 0)}",
        f"- 实盘赛社交热帖条数：{meta.get('实盘赛社交热帖条数', 0)}",
        f"- 官方比赛列表条数：{meta.get('官方比赛列表条数', 0)}",
        f"- 热门个股详情深挖条数：{meta.get('热门个股详情深挖条数', 0)}",
        f"- 完整度：{meta['完整度']}",
        f"- 数据缺口：{meta['数据缺口']}",
        "",
        "## 淘股吧股票热榜",
        "",
    ]
    lines.append(md_table(
        ["榜单", "排名", "代码", "名称", "当前价", "涨跌幅", "成交额", "连板标记", "人气值", "连续上榜", "关注理由", "行情时间"],
        [
            [
                item.get("榜单"),
                item.get("排名"),
                item.get("代码"),
                item.get("名称"),
                item.get("当前价"),
                item.get("涨跌幅"),
                format_money(item.get("成交额")),
                item.get("连板标记"),
                item.get("人气值") if item.get("人气值") is not None else item.get("今日搜索"),
                item.get("连续上榜") if item.get("连续上榜") is not None else item.get("最近七日搜索"),
                item.get("淘股吧关注理由", ""),
                item.get("行情时间"),
            ]
            for item in stock_hotlists
        ],
    ))
    lines += ["", "## 淘股吧话题榜", ""]
    lines.append(md_table(
        ["排名", "话题", "关注", "浏览", "主帖", "回复", "内容"],
        [
            [
                item.get("排名"),
                item.get("话题"),
                item.get("关注数"),
                item.get("浏览数"),
                item.get("主帖数"),
                item.get("回复数"),
                item.get("内容"),
            ]
            for item in talk_rank
        ],
    ))
    lines += ["", "## 实盘赛热门买入", ""]
    lines.append(md_table(
        ["排名", "代码", "名称", "买入人数", "当前价", "涨跌幅"],
        [
            [item.get("排名"), item.get("代码"), item.get("名称"), item.get("买入人数"), item.get("当前价"), item.get("涨跌幅")]
            for item in spmatch_hot_buy
        ],
    ))
    lines += ["", "## 淘股吧6维补充", ""]
    lines.append(md_table(
        ["排名", "代码", "名称", "热度来源", "题材归属", "关注理由", "模式词", "实盘赛买入", "验证点"],
        [
            [
                item.get("排名"),
                item.get("代码"),
                item.get("名称"),
                "、".join([f"{x.get('榜单')}#{x.get('排名')}" for x in item.get("热度来源") or []][:8]),
                "、".join((item.get("淘股吧题材归属") or [])[:6]),
                item.get("淘股吧关注理由"),
                "、".join([f"{x.get('模式词')}:{x.get('出现次数')}" for x in item.get("社区模式词") or []][:6]),
                item.get("实盘赛买入人数"),
                item.get("验证点"),
            ]
            for item in tgb_six_dim[:80]
        ],
    ))
    lines += ["", "## 热门讨论提及股票排行", ""]
    lines.append(md_table(
        ["排名", "代码", "名称", "出现次数"],
        [[item.get("排名"), item.get("代码"), item.get("名称"), item.get("出现次数")] for item in mention_stocks[:50]],
    ))
    lines += ["", "## 热门讨论提及概念排行", ""]
    lines.append(md_table(
        ["排名", "概念", "出现次数"],
        [[item.get("排名"), item.get("概念名称"), item.get("出现次数")] for item in mention_concepts[:30]],
    ))
    lines += ["", "## 热门讨论100", ""]
    lines.append(md_table(
        ["排名", "时间", "作者", "主题", "谈及股票", "谈及概念", "赞", "浏览", "评论", "链接"],
        [
            [
                item.get("排名"),
                item.get("时间"),
                item.get("作者"),
                item.get("主题") or item.get("主帖标题"),
                "、".join([s.get("名称") or "" for s in item.get("谈及股票") or []][:8]),
                "、".join([c.get("概念名称") or "" for c in item.get("谈及概念") or []][:5]),
                item.get("点赞数"),
                item.get("浏览数"),
                item.get("评论数"),
                item.get("链接"),
            ]
            for item in discussions
        ],
    ))
    lines += ["", "## 实盘赛社交热帖", ""]
    lines.append(md_table(
        ["排名", "时间", "作者", "标题", "浏览", "回复", "实盘标记", "链接"],
        [
            [
                item.get("排名"),
                item.get("发帖时间"),
                item.get("作者"),
                item.get("标题"),
                item.get("浏览数"),
                item.get("回复数"),
                item.get("实盘标记"),
                item.get("链接"),
            ]
            for item in spmatch_social[:80]
        ],
    ))
    lines += ["", "## 官方比赛列表", ""]
    lines.append(md_table(
        ["状态", "比赛ID", "比赛简称", "主办方", "参赛人数", "总资产", "标题", "链接"],
        [
            [
                item.get("状态"),
                item.get("比赛ID"),
                item.get("比赛简称"),
                item.get("主办方"),
                item.get("参赛人数"),
                item.get("比赛总资产"),
                item.get("标题"),
                item.get("链接"),
            ]
            for item in spmatch_info[:120]
        ],
    ))
    lines += ["", "## 热门个股详情TopN", ""]
    for item in stock_details:
        mode_summary = "、".join(
            [f"{x.get('模式词')}:{x.get('出现次数')}" for x in item.get("模式词计数") or []][:10]
        )
        lines += [
            f"### {item.get('代码')} {item.get('名称')}",
            "",
            f"- 链接：{item.get('链接')}",
            f"- 页面标题：{item.get('页面标题')}",
            f"- 讨论分类：{'、'.join(item.get('讨论分类') or [])}",
            f"- 模式词：{mode_summary}",
            "",
        ]
        snippets = []
        for related in item.get("相关讨论摘录") or []:
            snippets.append([related.get("作者"), related.get("摘要") or related.get("评论"), related.get("链接")])
        if snippets:
            lines.append(md_table(["作者", "摘录", "链接"], snippets[:10]))
            lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(date: str | None, slot: str | None, limit: int, deep_top_n: int) -> dict:
    ts = now_cn()
    date = date or ts.date().isoformat()
    slot = slot or ts.strftime("%H%M")
    out_dir = ROOT / "raw" / "04-市场数据" / "热榜" / date
    out_dir.mkdir(parents=True, exist_ok=True)

    stock_hotlists, stock_meta = build_stock_hotlists()
    discussions, discussion_meta = fetch_hot_discussions(limit)
    talk_rank, talk_meta = fetch_talk_rank()
    spmatch_hot_buy, hot_buy_meta = fetch_spmatch_hot_buy()
    spmatch_social, social_meta = fetch_spmatch_social()
    spmatch_info, match_meta = fetch_spmatch_info()
    detail_targets = choose_detail_targets(stock_hotlists, spmatch_hot_buy, max(0, deep_top_n))
    stock_details = []
    for target in detail_targets:
        try:
            stock_details.append(fetch_stock_detail(target["代码"], target["名称"]))
            time.sleep(0.4)
        except Exception as exc:
            stock_details.append({
                "代码": target["代码"],
                "名称": target["名称"],
                "链接": f"https://www.tgb.cn/quotes/{target['代码']}",
                "错误": str(exc),
            })
    tgb_six_dim = build_tgb_six_dim(stock_hotlists, spmatch_hot_buy, stock_details)
    mention_stocks, mention_concepts = aggregate_mentions(discussions)

    complete = len(discussions) >= limit
    data_gap = []
    if stock_meta["公开页股票榜条数"] < 100:
        data_gap.append("淘股吧公开稳定股票源包含热搜、hotPop、人气榜1小时/24小时；未发现稳定官方股票Top100分页接口，不能命名为官方个股Top100。")
    if not complete:
        data_gap.append(f"热门讨论只抓到{len(discussions)}条，未达到{limit}条。")
    if not data_gap:
        data_gap.append("热门讨论100已抓满；股票热搜以公开页暴露条目为准。")

    payload = {
        "元数据": {
            "数据源": "淘股吧",
            "日期": date,
            "时段": slot,
            "抓取时间": ts.isoformat(),
            "来源页面": QUOTES_URL,
            "热门个股搜索热度页面": HOT_POP_URL,
            "股票人气榜页面": POPULARITY_BOARD_URL,
            "实盘赛页面": SPMATCH_INDEX_URL,
            "目标条数": limit,
            "热门讨论实际条数": len(discussions),
            "公开页股票榜条数": stock_meta["公开页股票榜条数"],
            "热门个股详情深挖条数": len(stock_details),
            "完整度": "热门讨论已抓满" if complete else "部分完成",
            "数据缺口": "；".join(data_gap),
            **stock_meta,
            **discussion_meta,
            **talk_meta,
            **hot_buy_meta,
            **social_meta,
            **match_meta,
        },
        "股票热榜": stock_hotlists,
        "话题榜": talk_rank,
        "实盘赛热门买入": spmatch_hot_buy,
        "实盘赛社交热帖": spmatch_social,
        "官方比赛列表": spmatch_info,
        "热门个股详情TopN": stock_details,
        "淘股吧6维补充": tgb_six_dim,
        "热门讨论100": discussions,
        "讨论提及股票排行": mention_stocks,
        "讨论提及概念排行": mention_concepts,
    }

    stem = f"淘股吧热榜100-{slot}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    latest_json = out_dir / "淘股吧热榜100-latest.json"
    latest_md = out_dir / "淘股吧热榜100-latest.md"
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_path.write_text(json_text + "\n", encoding="utf-8")
    latest_json.write_text(json_text + "\n", encoding="utf-8")
    write_markdown(md_path, payload)
    write_markdown(latest_md, payload)
    return {
        "json": str(json_path),
        "md": str(md_path),
        "热门讨论实际条数": len(discussions),
        "公开页股票榜条数": stock_meta["公开页股票榜条数"],
        "话题榜条数": len(talk_rank),
        "实盘赛热门买入条数": len(spmatch_hot_buy),
        "实盘赛社交热帖条数": len(spmatch_social),
        "官方比赛列表条数": len(spmatch_info),
        "热门个股详情深挖条数": len(stock_details),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取淘股吧热榜100，写入RAW统一热榜目录。")
    parser.add_argument("--date", help="日期，默认今天，格式YYYY-MM-DD")
    parser.add_argument("--slot", help="时段标记，例如1800/2200，默认当前HHMM")
    parser.add_argument("--limit", type=int, default=100, help="热门讨论目标条数，默认100")
    parser.add_argument("--deep-top-n", type=int, default=10, help="热门个股详情页深挖数量，默认10；设为0则跳过")
    args = parser.parse_args()
    try:
        result = run(args.date, args.slot, args.limit, args.deep_top_n)
    except Exception as exc:
        print(f"抓取失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
