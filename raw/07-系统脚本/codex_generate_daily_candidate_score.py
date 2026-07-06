import argparse
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WIKI_ROOM = ROOT / "wiki" / "07-作战室"
RAW_PLAN = ROOT / "raw" / "03-每日计划"


def render_score_table(market_date: str) -> str:
    return f"""# {market_date} 作战室候选票评分表

## 基本判断

```yaml
date: {market_date}
market_state: 盘前作战室未人工生成，自动兜底为防守观察
market_expectation: 缺少人工盘前主计划，不允许据此开新仓
market_score_0_10:
emotion_score_0_10:
main_theme:
main_mode:
backup_mode:
position_permission: 防守观察；没有用户/作战室确认前不新增风险
data_quality: 自动兜底模板；缺人工盘前候选、缺竞价确认、缺热榜/连板/龙虎榜复核
```

## 数据缺口

```text
本页为系统兜底骨架，不代表已完成盘前作战室。
盘口/竞价数据缺失时，不能进入最终主计划。
热榜、连板、成交额、龙虎榜缺失时，必须降低候选票权重。
如当天已经开盘，本页只用于恢复 AI 上下文链路，不能倒推盘前买入计划。
```

## 今日主模式

| 类型 | 模式 | 使用条件 | 禁用条件 |
|---|---|---|---|
| 主模式 |  |  |  |
| 备选模式 |  |  |  |
| 禁用模式 |  |  |  |

## 候选票评分表

| 股票 | 方向 | 角色 | 主模式 | 信息可信度 | 逻辑硬度 | 题材地位 | 盘口/竞价 | 资金关注 | 风险扣分 | 总分 | 处理 |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
|  |  |  |  | S1/S2/S3/S4 |  |  |  |  |  |  | 主计划/备选/观察/删除 |
|  |  |  |  | S1/S2/S3/S4 |  |  |  |  |  |  | 主计划/备选/观察/删除 |
|  |  |  |  | S1/S2/S3/S4 |  |  |  |  |  |  | 主计划/备选/观察/删除 |
|  |  |  |  | S1/S2/S3/S4 |  |  |  |  |  |  | 主计划/备选/观察/删除 |
|  |  |  |  | S1/S2/S3/S4 |  |  |  |  |  |  | 主计划/备选/观察/删除 |

## 主计划

```text
主计划股票：无
为什么是它：盘前作战室未生成，禁止事后补造主计划
买入触发：无
禁止买入：未完成盘前主计划、未完成竞价确认、未确认真实持仓
退出条件：已有持仓按交割单和实时风险处理
仓位权限：防守观察
竞价确认：缺失，需要 Mac 本机竞价快照或用户导入 9:15 / 9:20 / 9:25 RAW 数据
```

## 备选

```text
备选股票：
触发条件：
不能转主计划的原因：
```

## 观察与禁买

```text
观察：
禁买：
```

## 收盘后必须回填

```text
D+0 表现：
是否符合盘前判断：
是否进入 D+1 跟踪：
模式是否加分/扣分：
错误成本：
```

## 生成依据

```text
模板来源：wiki/07-作战室/每日作战室候选票评分自动生成模板.md
生成脚本：raw/07-系统脚本/codex_generate_daily_candidate_score.py
生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
```
"""


def render_auction_watch(market_date: str) -> str:
    return f"""# {market_date} 竞价监控清单

## 用途

本清单由候选票评分表联动生成。Mac 本机竞价快照或用户导入 RAW 必须围绕这里的股票补齐 9:15、9:20、9:25 数据。

## 核心监控

| 股票 | 角色 | 盘前预期 | 9:15 看点 | 9:20 看点 | 9:25 看点 | 超预期 | 低于预期 | 开盘处理 |
|---|---|---|---|---|---|---|---|---|
| 全市场 | 风险锚 | 盘前作战室未生成 | 看涨跌停、连板、高标反馈 | 看撤单和题材分歧 | 看主线是否确认 | 主线明确且风险锚不恶化 | 退潮/跌停扩散/高标负反馈 | 只观察，不开新仓 |
|  | 主计划/备选/风险锚 |  |  |  |  |  |  |  |
|  | 主计划/备选/风险锚 |  |  |  |  |  |  |  |

## 风险提醒

```text
高标反馈：
核心补跌：
题材退潮：
竞价撤单：
跌停扩散：
```

## 生成依据

```text
联动文件：wiki/07-作战室/{market_date}-作战室候选票评分表.md
生成脚本：raw/07-系统脚本/codex_generate_daily_candidate_score.py
生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
```
"""


def write_if_allowed(path: Path, text: str, force: bool) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate daily candidate score and auction watch templates.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Market date, YYYY-MM-DD.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    args = parser.parse_args()

    score_path = WIKI_ROOM / f"{args.date}-作战室候选票评分表.md"
    auction_path = RAW_PLAN / f"{args.date}-竞价监控清单.md"

    wrote_score = write_if_allowed(score_path, render_score_table(args.date), args.force)
    wrote_auction = write_if_allowed(auction_path, render_auction_watch(args.date), args.force)

    print(f"score_table={'written' if wrote_score else 'exists'} {score_path}")
    print(f"auction_watch={'written' if wrote_auction else 'exists'} {auction_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
