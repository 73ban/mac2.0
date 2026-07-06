import json
import re
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TODAY = datetime.now().strftime("%Y-%m-%d")
SRC = ROOT / "wiki" / "04-L4交易模式与执行" / f"游资心得正式模式候选-{TODAY}.md"
OUT = ROOT / "wiki" / "04-L4交易模式与执行" / "正式模式升级卡"


MODE_RULES = {
    "题材主升": {
        "position": "可重仓，但必须是A类模式且竞价/板块确认。",
        "market": "大题材持续强化，主线清晰，核心股新高，板块有高度也有宽度。",
        "trigger": ["主线连续2-3日强化", "核心股分歧后能修复", "人气榜多平台共振", "龙头/中军/补涨梯队完整"],
        "forbid": ["单日小作文刺激", "只有一个票强而板块无宽度", "后排大面扩散", "指数或情绪明显退潮"],
        "auction": ["9:15看一字和核心票是否超预期", "9:20确认强封单不撤、风险锚不恶化", "9:25确认板块扩散和核心票开盘质量"],
    },
    "趋势抱团": {
        "position": "标准仓为主，题材主升叠加核心容量票时可提高仓位。",
        "market": "连板不一定强，但容量核心沿趋势走强，资金抱团清晰。",
        "trigger": ["容量核心不断新高", "成交额稳定放大", "回调不破趋势", "机构/研报/产业逻辑持续强化"],
        "forbid": ["高位放量滞涨", "抱团核心补跌", "题材中军跌破趋势", "市场切到纯连板接力且趋势失血"],
        "auction": ["核心容量票不低于预期", "同题材中军不集体低开", "热门榜排名不明显坍塌"],
    },
    "市场情绪周期": {
        "position": "决定所有模式仓位权限，不单独作为买点。",
        "market": "用赚钱效应、亏钱效应、高手预期、实盘赛仓位和连板天梯判断市场阶段。",
        "trigger": ["涨停/连板/晋级率改善", "亏钱效应收敛", "高手复盘从悲观转分歧或乐观", "核心票不再A杀"],
        "forbid": ["把情绪词当事实", "没有盘面数据支撑", "忽视竞价风险锚", "退潮期强行套用主升模式"],
        "auction": ["9:15看方向", "9:20看真假", "9:25看是否符合昨日预期"],
    },
    "弱转强": {
        "position": "标准仓以内；只有主线核心弱转强才允许提高仓位。",
        "market": "分歧后资金重新选择核心，适合主线延续或情绪修复。",
        "trigger": ["昨日分歧但未破位", "竞价高于预期", "开盘快速承接", "板块同步修复"],
        "forbid": ["纯庄股高开", "板块不跟", "昨日大面未修复", "高开秒砸无承接"],
        "auction": ["9:20后仍强", "9:25不被撤单打回", "开盘5分钟承接确认"],
    },
    "冰点修复": {
        "position": "小仓试错，修复确认后再加仓。",
        "market": "亏钱效应释放后，核心票止跌，市场预期由悲观转分歧。",
        "trigger": ["跌停减少", "核心票止跌", "昨日大面股不继续核", "修复方向有人气核心"],
        "forbid": ["退潮未释放完", "核心票继续A杀", "指数系统性下跌", "只因跌多就低吸"],
        "auction": ["风险锚不再大幅低开", "昨日恐慌票有承接", "修复核心高于预期"],
    },
    "并购重组预期差": {
        "position": "事件强度高且确认早时可重点参与，但必须防假消息。",
        "market": "适合消息驱动、连板接力和预期差行情。",
        "trigger": ["公告/权威信源确认", "重组标的有想象空间", "流通盘和筹码适合短线", "竞价或一字体现资金认可"],
        "forbid": ["无公告小作文", "消息已充分兑现", "高位连续加速后无换手", "监管风险明显"],
        "auction": ["一字封单质量", "同类重组票联动", "9:20不撤单", "9:25仍有资金承接"],
    },
    "连板接力": {
        "position": "情绪强时标准仓到重仓；退潮期禁止。",
        "market": "高度打开、晋级率高、断板反馈不差。",
        "trigger": ["空间板打开高度", "晋级率提升", "断板不A杀", "同梯队竞争胜出"],
        "forbid": ["高标核按钮", "天地板频发", "断板次日大面", "后排炸板率过高"],
        "auction": ["高标不低于预期", "同梯队淘汰票不极端负反馈", "板块前排继续强"],
    },
    "低吸": {
        "position": "弱市小仓，主升核心回踩可标准仓。",
        "market": "适合主线分歧、趋势回踩、冰点修复、牛市急跌。",
        "trigger": ["核心逻辑未变", "恐慌释放", "关键支撑有承接", "次日有修复预期"],
        "forbid": ["下跌源于逻辑证伪", "无承接阴跌", "退潮期后排低吸", "没有止损位"],
        "auction": ["低吸票不能低于风险线", "核心票不破关键预期", "板块没有集体补跌"],
    },
    "半路": {
        "position": "标准仓以内，要求板块和盘口共振。",
        "market": "适合主线确认、弱转强、趋势启动、题材扩散。",
        "trigger": ["分时主动拉升", "量能同步放大", "板块前排共振", "不是孤立脉冲"],
        "forbid": ["缩量急拉", "无板块共振", "后排跟风", "盘口冲高回落明显"],
        "auction": ["计划内票开盘不弱", "板块有资金进攻", "人气榜排名配合"],
    },
    "打板": {
        "position": "只做前排和确认板，退潮期禁止重仓。",
        "market": "适合连板接力、题材主升、强分歧转一致。",
        "trigger": ["板块核心", "换手充分", "封单质量好", "炸板后回封有资金"],
        "forbid": ["后排杂毛", "缩量一字后高位接力", "退潮期打板", "封单虚弱反复炸"],
        "auction": ["竞价不能明显低于预期", "同题材前排有强度", "风险锚不恶化"],
    },
    "出监管": {
        "position": "近期有效时可重点跟踪，必须结合偏离值和监管节点。",
        "market": "适合强势核心在监管压力释放后的再选择。",
        "trigger": ["监管节点解除", "人气仍在", "核心逻辑未破", "竞价或盘口重新转强"],
        "forbid": ["监管解除但人气消失", "板块退潮", "高位筹码松动", "强行幻想二波"],
        "auction": ["出监管首日不被核", "人气榜回升", "板块有修复"],
    },
    "绕异动": {
        "position": "用户近期有效模式，允许重点跟踪，但必须严格计算偏离值。",
        "market": "适合强势股在异动规则约束下维持趋势或二波。",
        "trigger": ["偏离值空间可控", "资金主动规避监管", "走势强但不过度触发异动", "题材仍有预期"],
        "forbid": ["偏离值计算不清", "已经触发监管风险", "题材退潮", "高位无承接"],
        "auction": ["开盘不极端加速", "走势符合绕异动节奏", "核心票不被砸"],
    },
    "纪律风控": {
        "position": "这是所有模式的底层约束。",
        "market": "任何行情都适用，尤其连续盈利后和大亏后。",
        "trigger": ["计划外冲动", "持仓偏离计划", "市场状态降级", "亏损扩大"],
        "forbid": ["把纪律当建议", "盈利后放松仓位约束", "亏损后急于扳本", "无退出条件开仓"],
        "auction": ["不符合竞价条件则计划暂停", "风险锚恶化则降仓或空仓", "持仓低于预期先处理风险"],
    },
}


def parse_candidates() -> list[dict]:
    text = SRC.read_text(encoding="utf-8", errors="ignore")
    rows = []
    for line in text.splitlines():
        if not line.startswith("| ") or line.startswith("|---") or "模式" in line and "资料数" in line:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 6:
            continue
        rows.append(
            {
                "mode": parts[0],
                "docs": parts[1],
                "a_docs": parts[2],
                "themes": parts[3],
                "stocks": parts[4],
                "representative": parts[5],
            }
        )
    return rows


def card(row: dict) -> str:
    mode = row["mode"]
    rule = MODE_RULES.get(mode, {})
    trigger = rule.get("trigger", [])
    forbid = rule.get("forbid", [])
    auction = rule.get("auction", [])
    return "\n".join(
        [
            f"# {mode}模式升级卡-{TODAY}",
            "",
            "## 来源强度",
            "",
            f"- 候选资料数：{row['docs']}",
            f"- A级资料数：{row['a_docs']}",
            f"- 代表资料：{row['representative']}",
            f"- 适用题材：{row['themes']}",
            f"- 代表个股：{row['stocks']}",
            "",
            "## 模式定位",
            "",
            rule.get("market", "待补充。"),
            "",
            "## 仓位权限",
            "",
            rule.get("position", "默认标准仓以内，未验证前不允许重仓。"),
            "",
            "## 触发条件",
            "",
            "\n".join(f"- {x}" for x in trigger) if trigger else "- 待补充。",
            "",
            "## 禁止条件",
            "",
            "\n".join(f"- {x}" for x in forbid) if forbid else "- 待补充。",
            "",
            "## 竞价确认",
            "",
            "\n".join(f"- {x}" for x in auction) if auction else "- 必须写入 9:15/9:20/9:25 观察条件。",
            "",
            "## 作战室使用",
            "",
            "- 只有与 L1 市场环境匹配时，才能进入主计划。",
            "- 必须写明买入方式：低吸、半路、打板或持仓处理。",
            "- 必须写明触发条件、禁止条件、退出条件。",
            "- 如果竞价或开盘低于预期，计划自动降级。",
            "",
            "## 统计要求",
            "",
            "- 每笔交易必须标注本模式是否参与。",
            "- 按持股周期统计胜率、盈亏额、最大回撤、平均收益。",
            "- 按市场状态拆分：题材主升、连板接力、趋势抱团、轮动、冰点修复、退潮。",
            "- 连续 3 次失效必须降级，连续 3 次验证有效可升级为 A 类模式。",
            "",
            "## 当前结论",
            "",
            "这是正式模式升级卡，已经可以进入作战室候选规则；但是否允许重仓，仍取决于近期验证结果和当日市场环境。",
            "",
        ]
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = parse_candidates()
    index_lines = [
        f"# 正式模式升级卡索引-{TODAY}",
        "",
        "| 模式 | 候选资料数 | A级资料数 | 文件 |",
        "|---|---:|---:|---|",
    ]
    for row in rows:
        mode = row["mode"]
        if mode not in MODE_RULES:
            continue
        path = OUT / f"{mode}模式升级卡-{TODAY}.md"
        path.write_text(card(row), encoding="utf-8")
        index_lines.append(f"| {mode} | {row['docs']} | {row['a_docs']} | {path.relative_to(ROOT).as_posix()} |")
    index_path = OUT / f"正式模式升级卡索引-{TODAY}.md"
    index_path.write_text("\n".join(index_lines), encoding="utf-8")
    print(json.dumps({"mode_cards": len(index_lines) - 4, "index": str(index_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
