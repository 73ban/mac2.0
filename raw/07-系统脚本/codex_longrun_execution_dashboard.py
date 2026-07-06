#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
QUEUE = ROOT / ".system/codex-longrun-queue.json"
OUT_JSON = ROOT / ".system/codex-longrun-dashboard.json"
OUT_MD = ROOT / f"wiki/09-统计与进化/{date.today().isoformat()}-Codex长期运行驾驶舱.md"
OUT_RAW_DIR = ROOT / f"raw/11-Codex分析产物/Codex长期运行驾驶舱/{date.today().isoformat()}"


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def latest_audit(pattern: str) -> dict:
    paths = sorted(ROOT.glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    if not paths:
        return {}
    return read_json(paths[0], {})


def build() -> dict:
    today = date.today().isoformat()
    queue = read_json(QUEUE, {"activeQueue": []})
    mode_lint = latest_audit(f"raw/11-Codex分析产物/交易模式质量检查/{today}/mode-page-lint.json")
    attribution = latest_audit(f"raw/11-Codex分析产物/交易模式归因审计/{today}/trade-mode-attribution-audit.json")
    attribution_enrich = latest_audit(f"raw/11-Codex分析产物/交易模式逐笔归因/{today}/recent-trade-mode-attribution.json")
    mode_dplus = latest_audit(f"raw/11-Codex分析产物/交易模式D+验证/{today}/trade-mode-dplus.json")
    bigday = latest_audit(f"raw/11-Codex分析产物/交易模式大赚大亏日归因/{today}/trade-mode-bigday-review.json")
    watchdog = read_json(ROOT / ".system/automation-watchdog.json", {})
    return {
        "schema": "73wiki-codex-longrun-dashboard-v1",
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "queue": queue.get("activeQueue", []),
        "modePageLint": {
            "total": mode_lint.get("total"),
            "ok": mode_lint.get("ok"),
            "needs_fix": mode_lint.get("needs_fix"),
        },
        "tradeModeAttributionAudit": {
            "total_trade_files": attribution.get("total_trade_files"),
            "missing_mode_attribution": attribution.get("missing_mode_attribution"),
        },
        "tradeModeAttributionEnrich": {
            "dates": len(attribution_enrich.get("dates") or []),
            "row_count": attribution_enrich.get("row_count"),
            "output": f"raw/11-Codex分析产物/交易模式逐笔归因/{today}/recent-trade-mode-attribution.md" if attribution_enrich else "",
        },
        "tradeModeDplus": {
            "row_count": mode_dplus.get("row_count"),
            "mode_count": len(((mode_dplus.get("summary") or {}).get("byMode") or {})),
            "output": f"raw/11-Codex分析产物/交易模式D+验证/{today}/trade-mode-dplus.md" if mode_dplus else "",
        },
        "tradeModeBigday": {
            "day_count": len(((bigday.get("summary") or {}).get("days") or [])),
            "big_win_count": len(((bigday.get("summary") or {}).get("big_win") or [])),
            "big_loss_count": len(((bigday.get("summary") or {}).get("big_loss") or [])),
        },
        "watchdog": {
            "status": watchdog.get("status"),
            "criticalCount": watchdog.get("criticalCount"),
            "warningCount": watchdog.get("warningCount"),
            "generatedAt": watchdog.get("generatedAt"),
        },
    }


def render_md(payload: dict) -> str:
    lines = [
        f"# {date.today().isoformat()} Codex长期运行驾驶舱",
        "",
        f"- 生成时间：{payload['generatedAt']}",
        "",
        "## 当前P0队列",
        "",
        "| ID | 优先级 | 状态 | 任务 | 完成标准 |",
        "|---|---|---|---|---|",
    ]
    for item in payload["queue"]:
        lines.append(
            f"| {item.get('id')} | {item.get('priority')} | {item.get('status')} | {item.get('task')} | {item.get('acceptance')} |"
        )

    mode = payload["modePageLint"]
    attr = payload["tradeModeAttributionAudit"]
    enrich = payload["tradeModeAttributionEnrich"]
    dplus = payload["tradeModeDplus"]
    bigday = payload["tradeModeBigday"]
    wd = payload["watchdog"]
    lines += [
        "",
        "## 关键缺口",
        "",
        "| 项目 | 当前值 | 目标 |",
        "|---|---:|---:|",
        f"| 模式页总数 | {mode.get('total')} | - |",
        f"| 结构完整模式页 | {mode.get('ok')} | {mode.get('total')} |",
        f"| 需要补齐模式页 | {mode.get('needs_fix')} | 0 |",
        f"| 有买入记录文件 | {attr.get('total_trade_files')} | - |",
        f"| 缺模式归因文件 | {attr.get('missing_mode_attribution')} | 0 |",
        f"| 全量扫描逐笔归因日期数 | {enrich.get('dates')} | 持续增长 |",
        f"| 全量扫描逐笔归因笔数 | {enrich.get('row_count')} | 持续增长 |",
        f"| 交易模式D+验证笔数 | {dplus.get('row_count')} | 持续增长 |",
        f"| 已纳入D+统计主模式数 | {dplus.get('mode_count')} | 持续增长 |",
        f"| 大赚/大亏日已归因交易日 | {bigday.get('day_count')} | 持续增长 |",
        f"| 大赚日数量 | {bigday.get('big_win_count')} | 用于沉淀有效模式 |",
        f"| 大亏日数量 | {bigday.get('big_loss_count')} | 用于沉淀错误库 |",
        "",
        "## 自动化健康",
        "",
        "| 项目 | 状态 |",
        "|---|---|",
        f"| Watchdog状态 | {wd.get('status')} |",
        f"| 硬故障 | {wd.get('criticalCount')} |",
        f"| 软告警 | {wd.get('warningCount')} |",
        f"| Watchdog生成时间 | {wd.get('generatedAt')} |",
        "",
        "## 下一步",
        "",
        "1. 消化历史缺口：把缺模式归因的旧交易/复盘文件逐步原地回填，当前缺口以审计结果为准。",
        "2. 把真实D+统计回填到模式页、错误库和统计进化页，避免只停留在RAW分析产物。",
        "3. 继续扩充待人工归因样本，把“待人工归因”逐步转成标准模式名。",
        "4. 自动脚本继续每小时刷新模式词典、模式页质量检查、归因缺口审计、逐笔D+验证和本驾驶舱。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    payload = build()
    OUT_RAW_DIR.mkdir(parents=True, exist_ok=True)
    md = render_md(payload)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(md, encoding="utf-8")
    (OUT_RAW_DIR / "codex-longrun-dashboard.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_RAW_DIR / "codex-longrun-dashboard.md").write_text(md, encoding="utf-8")
    print(json.dumps({"ok": True, "output": OUT_MD.relative_to(ROOT).as_posix()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
