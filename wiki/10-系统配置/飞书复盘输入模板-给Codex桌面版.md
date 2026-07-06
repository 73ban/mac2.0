# 飞书复盘输入模板-给Codex桌面版

更新时间：2026-06-29

## 固定读取顺序

Codex 桌面版收到飞书复盘输入时，先读本文件，再读：

1. `raw/07-系统脚本/每日工作流程.md`
2. `wiki/10-系统配置/飞书复盘落RAW操作清单.md`
3. `raw/07-系统脚本/templates/daily-report-template-v2.md`
4. `.system/current-ai-context.json`

## 飞书输入字段

| 字段 | 必填 | 用途 |
|---|---:|---|
| 类型 | 是 | 盘后复盘 / 盘中记录 / 交割单 / 短线心得 |
| 交易日期 | 是 | 写入 `YYYY-MM-DD` 对应 RAW |
| 今日操作 | 是 | 买入、卖出、撤单、未成交都保留原文 |
| 买入理由 | 否 | 用户口述逻辑，禁止 AI 编造 |
| 卖出理由 | 否 | 用户口述逻辑，禁止 AI 编造 |
| 持仓状态 | 否 | 持仓、现金、融资、仓位 |
| 盘面观察 | 否 | 主线、分歧、一致、亏钱效应、赚钱效应 |
| 心态纪律 | 否 | 冲动、恐惧、贪婪、犹豫、执行问题 |
| 明日计划 | 否 | 只保留用户原话，后续再提炼 |
| 附件 | 否 | 交割单截图、持仓截图、盘口截图、手写图 |

## 落地路径

飞书原始内容先写 RAW，不直接写正式 WIKI。

```text
交割单/附件 -> raw/01-交割单/YYYY-MM-DD/
复盘口述 -> raw/02-每日复盘/YYYY-MM-DD-飞书复盘RAW.md
盘中记录 -> raw/02-每日复盘/YYYY-MM-DD-盘中记录RAW.md
短线心得 -> raw/09-短线知识/飞书输入/YYYY-MM-DD-*.md
截图附件 -> raw/截图/盘中关键信号/YYYY-MM-DD/ 或 raw/09-短线知识/截图OCR/
```

## 本机接入口

飞书桥接器收到文字消息后，优先调用本机规则脚本，不先调用大模型：

```bash
python3 raw/07-系统脚本/codex_ingest_feishu_message.py --stdin
```

指定交易日时：

```bash
python3 raw/07-系统脚本/codex_ingest_feishu_message.py --date YYYY-MM-DD --type review --stdin
```

脚本职责：

1. 原话写入 `raw/10-飞书交易沟通/YYYY/MM/DD/`。
2. 复盘口述追加到 `raw/02-每日复盘/YYYY-MM-DD-飞书复盘RAW.md`。
3. 结构化事件追加到 `raw/02-每日复盘/YYYY-MM-DD-飞书复盘RAW.jsonl`。
4. 生成飞书回执到 `.system/feishu-notify-pending/`，由通知脚本发送。
5. 只做低风险识别，不把识别结果当正式买卖理由。

## 防误判硬规则

1. `飞书原话` 和 `Codex低风险识别` 必须分开保存。
2. 买卖理由只能来自用户原话、交割单证据和用户后续确认。
3. 出现“这个、那个、它、他、刚才”且对象不清楚时，必须标记 `待确认`。
4. 出现买入、卖出、加仓、减仓、清仓但没有明确股票代码或名称时，不能写成逐笔交易理由。
5. 用户提问“为什么、什么意思、重不重要”时，只能作为问题记录，不能当成用户已有结论。
6. 正式复盘引用口述时，要优先引用原话；如果需要改写，必须标注“根据原话理解”。

## 正式复盘结构

正式复盘使用 `raw/07-系统脚本/templates/daily-report-template-v2.md` 的 10 节结构，并兼容 `raw/07-系统脚本/每日工作流程.md` 中的 13 段要求。

最低必须覆盖：

1. 大盘环境与赚钱效应
2. 主线、板块、题材强弱
3. 连板天梯与情绪阶段
4. 今日操作与持仓复盘
5. 买卖理由与规则符合度
6. 仓位、资金、风险暴露
7. 关键反思
8. 心态、纪律、执行力
9. 明日方向与操作计划
10. 需要 D+1 / D+3 验证的问题

## 执行规则

1. 原始飞书内容必须先入 RAW。
2. 买入理由、卖出理由、心态原因只能来自用户原文或交割单证据。
3. 缺数据写“数据缺失”，不得补编。
4. 交割单、持仓、资金必须优先于口述。
5. 正式复盘先发回飞书送审，用户确认后再写 WIKI。
6. 用户确认后运行：

```bash
python3 raw/07-系统脚本/codex_daily_workflow.py --date YYYY-MM-DD --phase postmarket --force
python3 raw/07-系统脚本/codex_raw_watch.py --once --lookback-hours 24
python3 raw/07-系统脚本/codex_batch_ingest_queue.py
python3 raw/07-系统脚本/codex_update_ai_context.py --date YYYY-MM-DD
```

## 给 Codex 桌面版的固定指令

```text
把 /Users/qixinchaye/wiki/73神话 作为 Trading Review Wiki 根目录。
收到飞书复盘后，先读 wiki/10-系统配置/飞书复盘输入模板-给Codex桌面版.md。
先把飞书原文、交割单和附件落 RAW，再按每日复盘模板生成正式复盘草稿。
正式复盘必须先发回飞书给用户确认；确认前不要写正式 WIKI。
确认后再刷新 RAW 索引、月度统计、错误账本、D+验证和 .system/current-ai-context.json。
```
