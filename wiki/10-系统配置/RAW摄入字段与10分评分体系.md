# RAW摄入字段与10分评分体系

更新时间：2026-06-18

## 必填字段

```yaml
raw_id:
source_agent:
agent_name:
task_id:
data_type:
data_time:
source:
preferred_ingestor: codex
deepseek_action: skip_after_registered
content_hash:
truth_grade:
fate:
```

## 角色口径

1. 河马、Mac本机RAW入口只负责采集，写入 RAW，不允许写 WIKI。
2. 用户导入RAW入口当前待命，不作为固定日常采集源。
3. 所有投资相关 RAW 默认 `preferred_ingestor: codex`，由大鸟主摄入。
4. 大鸟负责读取研报、知识星球、新闻、纪要等高价值资料，必要时联网验证，再打 `truth_grade=S1/S2/S3/S4` 和 `fate=A/B/C/D`。
5. 大鸟写入 WIKI 后，必须登记 `.system/ingest-registry.jsonl`。
6. DEEPSEEK 扫描 RAW 前必须先查登记表；看到 `status: ingested`、`preferred_ingestor: codex` 或 `deepseek_action: skip`，不得读取正文，不得二次摄入。
7. DEEPSEEK 只处理大鸟明确交接的内容，或 `preferred_ingestor: deepseek` 的本地兜底任务。

## 10 分评分原则

评分只用于帮助大鸟判断是否值得进入下一步处理，不替代最终交易判断。

### 建议拆分

- 证据完整度
- 信息新鲜度
- 可验证性
- 与主计划相关度
- 与持仓相关度

## 限制

1. 没有证据路径，不得高分。
2. 小作文、传闻、二手转述不得直接进入主计划。
3. 分数高不等于可以买，只代表值得进一步处理。
