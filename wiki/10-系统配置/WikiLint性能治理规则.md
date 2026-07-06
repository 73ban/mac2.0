# Wiki Lint 性能治理规则

```yaml
type: 系统配置
date: 2026-07-04
owner: Codex
status: active
```

## 问题结论

应用内 Wiki lint 卡死的主要原因不是 Mac 性能不够，而是扫描范围失控。

本次排查到的高风险项：

| 问题 | 影响 | 当前处理 |
|---|---|---|
| `wiki/wiki` 旧嵌套副本 | 多扫 12909 个旧文件，链接图和 LLM prompt 成倍膨胀 | 已移到 `.conflicts/lint-quarantine-20260704/wiki-nested-old-copy` |
| 应用内语义 lint | 会把大量页面摘要一次性塞给模型，可能卡死 | 不做全库语义 lint，改按专题/月份分批 |
| `raw` 目录过大 | 2G+ 原始资料，不适合作为 wiki lint 对象 | lint 不扫 raw，只扫活动 wiki |
| `.llm-wiki/.llm-wiki`、`.system/.system`、`data/data` | 迁移嵌套副本，容易拖慢全局扫描 | 已加入忽略规则 |
| 超大索引文件 | 单文件 2M+，链接解析成本高 | 安全 lint 跳过超大文件 |

## 标准命令

日常只用安全 lint：

```bash
python3 raw/07-系统脚本/codex_safe_wiki_lint.py --date YYYY-MM-DD --write
```

输出：

```text
.system/safe-wiki-lint.json
wiki/09-统计与进化/YYYY-MM-DD-安全WikiLint报告.md
```

## 使用边界

允许：

- 检查活动 `wiki/` 的失效链接。
- 检查孤立页面。
- 检查无出链页面。
- 生成可追溯报告。

不允许：

- 对全库一次性跑 LLM 语义 lint。
- 把 `raw/` 纳入 wiki lint。
- 把 `.llm-wiki/`、`.system/`、`data/`、`.stversions/` 纳入 lint。
- 在没有备份/隔离的情况下直接删除旧副本。

## 应用内 Lint 使用规则

在 Trading Review Wiki 应用里：

1. 可以先跑不带 LLM 的结构检查。
2. 不要勾选“语义分析 LLM”做全库检查。
3. 不要勾选“策略一致性 LLM”做全库检查。
4. 需要语义检查时，由 Codex 按目录、月份、主题单独跑。

## 当前隔离目录

```text
.conflicts/lint-quarantine-20260704/
```

已隔离：

```text
wiki-nested-old-copy/
wiki-99-migration/
```

这是隔离，不是删除。确认无用后再清理。

## 当前性能基线

2026-07-04 安全 lint 实测：

```text
活动 wiki md 文件：9616
安全 lint 耗时：约 0.6 秒
旧 wiki/wiki 副本：12909 文件，65M，已移出活动扫描范围
```

## 后续改进

1. 应用源码已补性能保护，但打包版 app 需要重新构建后才会生效。
2. 后续如果重装 Trading Review Wiki，应包含以下保护：
   - 底层目录扫描跳过 `wiki/wiki`、`99-待删除审核`、`99-迁移`、`.stversions`。
   - 结构 lint 设置最大扫描文件数。
   - 语义 lint 设置最大页面数和摘要长度。
   - 语义 lint 默认只扫近期作战室、统计、系统配置、错误库。
