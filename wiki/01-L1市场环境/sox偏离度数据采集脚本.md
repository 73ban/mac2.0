```yaml
---
type: 数据
title: SOX偏离度数据采集脚本
created: 2026-05-29
updated: 2026-05-29
tags:
  - 脚本
  - Python
  - AKShare
  - YahooFinance
  - 数据库
related:
  - 概念/sox偏离度跨境情绪监控
  - 数据/ai算力链等权指数构建方法
sources:
  - research-soxaai-2026-05-29-1.md
confidence_grade: B
confidence_reason: 技术方案明确，数据接口可用，但代码未经联调和异常处理测试
---
```

# SOX偏离度数据采集脚本

## 概述

本脚本用于自动化采集 **费城半导体指数（SOX）** 和 **自建AI算力链等权指数** 的日线数据，完成时差对齐、计算滚动相关性和Z‑Score偏离度，并写入SQLite数据库。是实现[[概念/SOX偏离度跨境情绪监控]]的数据引擎。

## 技术栈与数据源

- **Python** + **pandas** + **SQLite3**
- SOX历史数据：通过 `yfinance` 库读取 Yahoo Finance 的 `^SOX` 数据；备用：直接下载英为财情的CSV。
- A股成分股数据：**AKShare** (`ak.stock_zh_a_hist`) 获取全部成分股日线，按[[数据/ai算力链等权指数构建方法]]计算等权组合收益率。
- 上证指数：通过AKShare或搜狐接口获取。

## 脚本结构（伪代码大纲）

```
# 1. 配置
COMPONENTS = ['000063', '601138', '300308', ...]  # 股票代码列表
DB_PATH = "sox_monitor.db"

# 2. 拉取SOX数据 -> DataFrame sox_df
# 3. 拉取每个成分股数据 -> 计算等权日收益率 -> ai_index_df
# 4. 数据对齐：AI交易日 vs SOX前一日交易日，处理节日缺口
# 5. 计算衍生指标
#   - rolling_corr_20 = ai_chg.rolling(20).corr(sox_chg)
#   - rolling_corr_60 = ai_chg.rolling(60).corr(sox_chg)
#   - cum_diff = ai_cum - sox_cum
#   - deviation_z = (cum_diff - mean) / std  (滚动252日)
# 6. 写入SQLite三张表：sox_daily, a_share_ai_index, derived_metrics
# 7. 可选：生成预警推送（Z>2 等）
```

## 维护与执行

- **频率**：每日A股收盘后自动运行（可通过crontab或Windows任务计划程序调度）。
- **容错**：单日失败时支持增量更新，避免重复拉取全量历史。
- **监控**：若连续3日脚本未正常完成，触发人工检查提醒。

```
*页面创建：2026-05-29 — 将量化框架转化为可执行的自动化流程。*
```

