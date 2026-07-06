#!/usr/bin/env python3
"""Update the current AI context manifest for a trading day.

Usage:
  python3 raw/07-系统脚本/codex_update_ai_context.py --date 2026-06-29
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def page(title: str, path: str, reason: str, required: bool = True) -> dict:
    return {
        "title": title,
        "path": path,
        "required": required,
        "reason": reason,
    }


def build_manifest(date: str) -> dict:
    return {
        "version": 1,
        "enabled": True,
        "activeDate": date,
        "title": f"{date} 20万小资金作战与AI进化上下文",
        "systemInstruction": (
            "回答交易问题前，必须先基于本清单的 pinnedPages 判断当前作战计划、"
            "持仓缺口、D+验证、模式权限和统计回写。资料卡和搜索结果只能作为补充，"
            "不能越过当前作战主链。"
        ),
        "pinnedPages": [
            page(
                "总目标：20万小资金做大与AI超短进化",
                "wiki/00-总纲/20万小资金做大与AI超短进化总控.md",
                "定义两个总目标和AI判断优先级",
            ),
            page(
                "AI每日启动读取清单",
                "wiki/10-系统配置/AI每日启动读取清单.md",
                "规定对话框回答前的读取顺序",
            ),
            page(
                "Mac迁移体检报告",
                "wiki/10-系统配置/Mac迁移体检报告.md",
                "服务器到Mac迁移后的运行状态、依赖和剩余缺口",
            ),
            page(
                "Mac迁移收尾报告",
                "wiki/10-系统配置/Mac迁移收尾报告-2026-06-29.md",
                "Trading Review Wiki主链、wx-cli、WeKnora、QUEST和WeRSS交接状态",
            ),
            page(
                "当前持仓决策",
                "wiki/06-持仓与资金管理/当前持仓决策.md",
                "当前真实持仓、证据日期和去留口径",
            ),
            page(
                "交割单与复盘证据审计",
                "wiki/06-持仓与资金管理/2026-06-28-交割单与复盘证据审计.md",
                "6月交割单/复盘覆盖和证据优先级",
            ),
            page(
                "2026-06 RAW交割单复盘覆盖索引",
                "wiki/06-持仓与资金管理/2026-06-RAW交割单复盘覆盖索引.md",
                "6月每日交割单、复盘和盈亏可统计状态",
            ),
            page(
                f"{date} AI上下文包",
                f"wiki/07-作战室/{date}-AI上下文包.md",
                "今日最小必读包",
            ),
            page(
                f"{date} 作战总控",
                f"wiki/07-作战室/{date}-作战总控.md",
                "今日作战、竞价、盘后回填总入口",
            ),
            page(
                "当前作战室工作页",
                "wiki/07-作战室/当前作战室工作页.md",
                "当前主计划、备选、执行短名单",
            ),
            page(
                f"{date} 作战室候选票评分表",
                f"wiki/07-作战室/{date}-作战室候选票评分表.md",
                "候选票评分和触发/降级条件",
            ),
            page(
                f"{date} 作战室候选验证回看",
                f"wiki/09-统计与进化/{date}-作战室候选验证回看.md",
                "作战室候选D+0表现、加分扣分和规则回写",
            ),
            page(
                f"{date} 竞价监控清单",
                f"raw/03-每日计划/{date}-竞价监控清单.md",
                "竞价和持仓监控表",
            ),
            page(
                f"{date} D+验证任务",
                f"wiki/09-统计与进化/{date}-D+验证任务.md",
                "今日到期D+验证项",
            ),
            page(
                "D+验证待回填总览",
                "wiki/09-统计与进化/D+验证待回填总览.md",
                "已到期未回填D+任务和未来到期压力",
            ),
            page(
                "自动核心池评分修正规则",
                "wiki/10-系统配置/自动核心池评分修正规则.md",
                "高分低信号和D+失败后的自动降级规则",
            ),
            page(
                "20万小资金超短模式总控",
                "wiki/04-L4交易模式与执行/20万小资金超短模式总控.md",
                "模式和仓位权限",
            ),
            page(
                "短线知识待提炼池",
                "wiki/04-L4交易模式与执行/短线知识待提炼池.md",
                "飞书输入、游资公众号和图片OCR进入正式模式前的候选池",
            ),
            page(
                "短线知识验证队列",
                "wiki/09-统计与进化/短线知识验证队列.md",
                "短线知识从候选观点到验证、证伪、升级或降级的跟踪队列",
            ),
            page(
                "2026-06下旬错误候选汇总",
                "wiki/05-错误库/2026-06下旬错误候选汇总.md",
                "最近高置信错误和盘中约束",
            ),
            page(
                "2026-06错误成本账本草案",
                "wiki/09-统计与进化/2026-06-错误成本账本草案.md",
                "6月下旬错误候选的结构化成本账本",
            ),
            page(
                "2026-06-05豫能控股天地板错误",
                "wiki/05-错误库/2026-06-05-豫能控股天地板三次卖点错过.md",
                "6月最大回撤、退潮日满仓满融和三次卖点错过规则",
            ),
            page(
                "2026-06-10外围利空下卖点拖延错误",
                "wiki/05-错误库/2026-06-10-外围利空下卖点拖延与换仓过度.md",
                "外围利空下旧仓卖点拖延、弱票止损拖延和换仓顺序规则",
            ),
            page(
                "2026-06模式胜率与回撤贡献v0.1",
                "wiki/04-L4交易模式与执行/2026-06模式胜率与回撤贡献v0.1.md",
                "6月高置信模式样本、胜率、回撤贡献和仓位权限",
            ),
            page(
                "利通电子出监管博弈样本",
                "wiki/04-L4交易模式与执行/2026-06-10至06-12利通电子出监管博弈样本.md",
                "出监管模式真实样本、正负反馈和仓位权限修正",
            ),
            page(
                "核心题材生命周期总表",
                "wiki/02-L2方向题材/核心题材生命周期/核心题材生命周期总表-2026-06-28.md",
                "L2主线阶段判断",
            ),
            page(
                "20万小资金统计与进化仪表盘",
                "wiki/09-统计与进化/20万小资金统计与进化仪表盘.md",
                "盘后统计和AI训练指标",
            ),
            page(
                "2026-06交易统计初稿",
                "wiki/09-统计与进化/2026-06-交易统计初稿.md",
                "6月交割单和复盘证据级统计",
            ),
            page(
                "2026-06待核验日期标准化报告",
                "wiki/09-统计与进化/2026-06-待核验日期标准化报告.md",
                "待核验日期处理、排除和覆盖规则",
            ),
            page(
                "2026-06月度净值表v0.1",
                "wiki/09-统计与进化/2026-06-月度净值表v0.1.md",
                "6月交易盈亏累计、待复核项和出入金处理",
            ),
            page(
                "盘后AI训练回写清单",
                "wiki/09-统计与进化/盘后AI训练回写清单.md",
                "盘后回写路径",
            ),
        ],
    }


def validate_manifest(root: Path, manifest: dict) -> list[str]:
    missing: list[str] = []
    for item in manifest.get("pinnedPages", []):
        if item.get("required", True) and not (root / item["path"]).exists():
            missing.append(item["path"])
    return missing


def ensure_daily_context_inputs(root: Path, date: str) -> list[str]:
    """Create conservative daily war-room skeletons when the context chain is missing.

    This is a guardrail for direct calls to codex_update_ai_context.py. It does not
    create a bullish plan; it only prevents the AI context chain from breaking.
    """
    required = [
        root / f"wiki/07-作战室/{date}-AI上下文包.md",
        root / f"wiki/07-作战室/{date}-作战总控.md",
        root / f"wiki/07-作战室/{date}-作战室候选票评分表.md",
        root / f"raw/03-每日计划/{date}-竞价监控清单.md",
    ]
    if all(path.exists() for path in required):
        return []

    actions: list[str] = []
    generator = root / "raw/07-系统脚本/codex_generate_daily_candidate_score.py"
    preparer = root / "raw/07-系统脚本/codex_prepare_trading_day.py"
    score = root / f"wiki/07-作战室/{date}-作战室候选票评分表.md"
    auction = root / f"raw/03-每日计划/{date}-竞价监控清单.md"

    if generator.exists() and (not score.exists() or not auction.exists()):
        result = subprocess.run(
            [sys.executable, str(generator), "--date", date],
            cwd=str(root),
            text=True,
            capture_output=True,
        )
        actions.append(f"generate_daily_candidate_score status={result.returncode}")

    if preparer.exists():
        result = subprocess.run(
            [sys.executable, str(preparer), "--date", date, "--skip-context-update"],
            cwd=str(root),
            text=True,
            capture_output=True,
        )
        actions.append(f"prepare_trading_day status={result.returncode}")

    return actions


def update_configs(root: Path, date: str) -> None:
    system_path = root / "73wiki.system.json"
    config_path = root / "73wiki.config.json"

    system = load_json(system_path)
    system["aiContext"] = {
        "enabled": True,
        "activeDate": date,
        "manifestPath": ".system/current-ai-context.json",
        "dailyReadmePath": "wiki/10-系统配置/AI每日启动读取清单.md",
        "activeContextPage": f"wiki/07-作战室/{date}-AI上下文包.md",
        "rule": "聊天和Codex Local回答交易问题前，先读取manifestPath里的pinnedPages，再做关键词搜索。",
    }
    write_json(system_path, system)

    config = load_json(config_path)
    trading_brain = config.setdefault("tradingBrain", {})
    trading_brain["aiContext"] = {
        "enabled": True,
        "activeDate": date,
        "manifestPath": ".system/current-ai-context.json",
        "activeContextPage": f"wiki/07-作战室/{date}-AI上下文包.md",
        "requiredBeforeTradingAnswer": True,
    }
    write_json(config_path, config)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Trading date, e.g. 2026-06-29")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[2]),
        help="73神话 project root",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Write manifest even if required pinned pages are missing",
    )
    parser.add_argument(
        "--no-auto-prepare",
        action="store_true",
        help="Do not auto-generate conservative daily war-room skeletons before validation",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    auto_actions = [] if args.no_auto_prepare else ensure_daily_context_inputs(root, args.date)
    manifest = build_manifest(args.date)
    if auto_actions:
        manifest["autoPrepare"] = auto_actions
    missing = validate_manifest(root, manifest)

    if missing and not args.allow_missing:
        print("Missing required pinned pages:", file=sys.stderr)
        for item in missing:
            print(f"- {item}", file=sys.stderr)
        return 2

    write_json(root / ".system/current-ai-context.json", manifest)
    update_configs(root, args.date)

    print(f"updated=.system/current-ai-context.json")
    print(f"activeDate={args.date}")
    print(f"pinned={len(manifest['pinnedPages'])}")
    print(f"missing={len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
