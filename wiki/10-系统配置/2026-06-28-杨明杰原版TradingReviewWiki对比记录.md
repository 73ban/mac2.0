# 2026-06-28 杨明杰原版 Trading Review Wiki 对比记录

## 下载位置

- 杨明杰原版：`/Users/qixinchaye/Workspace/trading-review-wiki-original`
- 当前 73WIKI：`/Users/qixinchaye/Workspace/73wiki-source`
- 73神话数据工作区：`/Users/qixinchaye/wiki/73神话`

## 版本结论

| 项目 | 杨明杰原版 | 当前 73WIKI |
|---|---|---|
| Git remote | `ymj8903668-droid/trading-review-wiki` | `73ban/73wiki-source` |
| 当前提交 | `95def04` | `3930eee` + 本地未提交改动 |
| package name | `trading-review-wiki` | `73wiki` |
| version | `0.10.5` | `1.0.0` |
| Tauri 产品名 | `Trading Review Wiki` | `73WIKI` |
| Tauri identifier | `com.tradingreviewwiki.app` | `com.seventythree.wiki` |
| npm scripts | 7 个 | 66 个 |
| scripts 文件 | 9 个 | 73 个 |

## LLM 接入差异

杨明杰原版 provider：

- OpenAI
- Anthropic
- Google
- MiniMax
- Kimi Code
- Codex (Responses API)
- Ollama
- Custom

当前 73WIKI provider：

- OpenAI
- Anthropic
- Gemini
- DeepSeek
- Qwen
- MiniMax
- 智谱
- Ollama
- OpenAI Compatible

关键判断：

- 原版有 `Codex (Responses API)`，但仍然是 API 接入。
- 原版 `codex` provider 请求 `https://api.openai.com/v1/responses`，并使用 `Authorization: Bearer ${apiKey}`。
- 原版没有发现 ChatGPT Pro 订阅登录态、cookie、session、浏览器自动化直连接入。
- 所以原版不能把 GPT Pro 会员直接填进 App 设置里当免费模型调用。

## 原版比当前多的功能模块

原版当前 `main` 相比 73WIKI 有这些值得评估是否移植的模块：

- `Codex (Responses API)` provider
- LLM 连接测试：`src/lib/llm-test.ts`
- 设置页模型连接测试按钮
- Schema 迁移：`migrate-schema-dialog.tsx` / `migrate-schema-v1.ts`
- 目录规范化：`normalize-dirs-dialog.tsx` / `normalize-dirs.ts`
- 垃圾页面清理：`cleanup-garbage-dialog.tsx` / `cleanup-garbage.ts`
- body residue 清理：`body-residue-dialog.tsx` / `body-residue.ts`
- stock code 同步：`stock-codes.ts` / `stock_codes.rs`
- docs 目录下的 CLI、RAG、Schema 文档

## 当前 73WIKI 比原版多的功能模块

当前 73WIKI 已深度交易化，新增大量交易系统自动化脚本，包括：

- D+验证、计划审计、卖后验证、假设验证
- 同花顺/通达信/腾讯行情相关采集脚本
- 市场强度、市场聚焦、市场环境、作战室骨架
- 训练飞轮、学习层、证据队列、评分反馈
- 迁移审计、编码健康、系统健康、pipeline 审计
- RAW 编号目录和 73神话工作区适配

## 取舍建议

1. 不建议回退到杨明杰原版。原版是通用交易复盘工具，当前 73WIKI 已经是你的交易操作系统底座。
2. 可以从原版选择性移植：
   - LLM 连接测试按钮
   - Codex Responses API provider
   - Schema 迁移与目录规范化工具
   - 垃圾页面清理工具
3. 不要误判 `Codex (Responses API)` 为 GPT Pro 订阅接入。它仍然是 OpenAI API，会产生 API 费用。
4. GPT Pro / Codex 会员主力用法仍应保持：外部智能体直接读写 `/Users/qixinchaye/wiki/73神话` 文件。
