# Codex Pro 本机 LLM 桥接配置

- 状态：已启用
- 用途：让 Trading Review Wiki 的 LLM 功能调用本机 Codex CLI，消耗本机 ChatGPT/Codex 登录额度，不走 DeepSeek 分析费用。
- 本机服务：`http://127.0.0.1:17373/v1`
- 健康检查：`http://127.0.0.1:17373/health`
- 73WIKI provider：`ollama`
- 73WIKI ollamaUrl：`http://127.0.0.1:17373`
- 73WIKI model：`codex-pro-local`
- 工作目录：`/Users/qixinchaye/wiki/73神话`

## 文件

- 桥接服务：`raw/07-系统脚本/codex-openai-compatible-bridge.mjs`
- 启动脚本：`raw/07-系统脚本/start-codex-bridge.sh`
- 停止脚本：`raw/07-系统脚本/stop-codex-bridge.sh`
- LaunchAgent：`~/Library/LaunchAgents/com.tradingreviewwiki.codex-bridge.plist`
- 日志：`.system/logs/codex-bridge.launchd.out.log`

## 计划审计兼容

旧版 App 的计划审计只识别：

```md
## 五、明日计划
```

当前 13 段复盘使用“明日操盘要点初稿”等标题，所以额外生成兼容文件：

- 生成脚本：`raw/07-系统脚本/codex_generate_plan_audit_compat.py`
- 输出目录：`raw/02-每日复盘/计划审计兼容/`

旧版路径兼容：

- `raw/日复盘` -> `raw/02-每日复盘`
- `raw/交割单` -> `raw/01-交割单`

## 注意

- ChatGPT/Codex Pro 会员不能直接当 OpenAI API Key 填入第三方 App。
- 当前方案是本机桥接：73WIKI 用 Ollama 兼容入口调本机 HTTP 服务，本机服务再调用 `codex exec`。
- 使用 `ollama` provider 是为了兼容旧版 App 的“无 API Key 可运行”校验；实际并没有使用 Ollama 模型。
- `codex exec` 不是秒回 API，计划审计会比普通 API 慢，但不消耗 DeepSeek 分析费用。
