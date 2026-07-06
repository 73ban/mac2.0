# 当前 AI 上下文清单说明

更新时间：2026-06-28

## 目的

`.system/current-ai-context.json` 是机器可读的当前交易上下文清单。

它解决的问题是：Wiki 对话框提问时，AI 不应该只靠关键词搜索随机读取资料，而应该先读取当前交易主链。

## 当前配置

```yaml
manifest: .system/current-ai-context.json
activeDate: 2026-06-29
activeContextPage: wiki/07-作战室/2026-06-29-AI上下文包.md
```

系统配置入口：

- `73wiki.system.json -> aiContext`
- `73wiki.config.json -> tradingBrain.aiContext`

## 读取规则

聊天上下文构建顺序：

1. 读取 `purpose.md`。
2. 读取 `.system/current-ai-context.json`。
3. 先加载 `pinnedPages` 中的 P0 必读页面。
4. 再根据用户问题做关键词搜索和图谱扩展。
5. 最终把 P0 页面和搜索页面一起发给模型。

## pinnedPages 更新规则

每天盘前需要更新：

- `activeDate`
- 今日 AI 上下文包
- 今日作战总控
- 今日候选评分表
- 今日竞价监控清单
- 今日 D+验证任务

推荐使用脚本更新：

```bash
python3 raw/07-系统脚本/codex_update_ai_context.py --date 2026-06-29
```

脚本会同时更新：

- `.system/current-ai-context.json`
- `73wiki.system.json -> aiContext`
- `73wiki.config.json -> tradingBrain.aiContext`

不建议每天改：

- 总目标页
- AI每日启动读取清单
- 模式总控
- 题材生命周期总表
- 统计仪表盘
- 盘后AI训练回写清单

## 注意

本清单不是买入建议。它只规定 AI 应该优先读取哪些页面。

真正的交易判断仍必须经过：

```text
L1市场环境 -> L2主线 -> L3个股核心性 -> L4模式权限 -> 持仓/仓位 -> D+验证
```
