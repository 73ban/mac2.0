# 龙虾复盘到 Codex 主流程自动接力规则

更新时间：2026-06-30

## 目标

龙虾可以在任意时间完成每日复盘 RAW。只要 RAW 同步到 Mac，Codex 主流程应自动接力，补齐交易大脑层复盘并写入 WIKI，不依赖用户固定时间提醒。

## 触发条件

Mac 后台服务每 30 秒扫描：

```text
raw/02-每日复盘/
```

只有满足以下条件的文件才触发：

```text
文件名：YYYY-MM-DD-复盘.md
文件稳定：90 秒内未继续写入
文件内容包含：writer: longxia
文件内容包含：needs_codex_followup: true
文件包含龙虾 13 段复盘结构
```

历史旧复盘、飞书原文 RAW、市场数据补全文件不会触发。

## 龙虾必须写入的头部字段

```yaml
trade_date: YYYY-MM-DD
writer: longxia
source_type: feishu_oral_review_with_trade_slip
status: RAW 待 Codex 主流程提炼
needs_codex_followup: true
```

## Codex 自动写入

触发后，Codex 主流程自动补写：

```text
wiki/09-统计与进化/YYYY-MM-DD-盘后复盘与AI训练回写.md
wiki/07-作战室/YYYY-MM-DD-盘后回看.md
.system/codex-review-done-YYYY-MM-DD.json
```

Codex 不覆盖龙虾 RAW。

## 后台服务

LaunchAgent：

```text
com.qixinchaye.longxia-review-handoff
```

脚本：

```text
.system/scripts/watch-longxia-review-handoff.py
```

健康检查：

```bash
python3 .system/scripts/check-longxia-review-handoff.py
```

状态文件：

```text
.system/longxia-review-handoff-current.json
.system/longxia-review-handoff-state.json
```

日志：

```text
.system/logs/longxia-review-handoff.log
.system/logs/longxia-review-handoff.launchd.out.log
.system/logs/longxia-review-handoff.launchd.err.log
.system/logs/longxia-review-handoff/
```

## 手动补跑

如果自动触发失败，但龙虾 RAW 已经到位，可以手动跑：

```bash
python3 .system/scripts/watch-longxia-review-handoff.py --once --date YYYY-MM-DD
```

## 故障判断

如果状态是：

```text
idle
```

说明还没看到符合条件的龙虾完整复盘。

如果状态是：

```text
waiting_for_ready_raw
```

说明文件名匹配，但缺 `writer: longxia`、`needs_codex_followup: true` 或 13 段结构。

如果状态是：

```text
processing
```

说明 Codex 正在补 WIKI。

如果状态是：

```text
done
```

说明 Codex 已完成接力。

如果状态是：

```text
codex_failed / codex_timeout / error
```

先看日志，再手动补跑。

## 分工边界

龙虾负责事实层 RAW：

```text
交割单、用户口述、市场数据、连板天梯、热榜、资金流向、13 段 RAW 复盘
```

Codex 负责交易大脑层：

```text
作战室回看、交易归因、错误候选升级、模式进化、D+验证、统计与 WIKI 沉淀
```
