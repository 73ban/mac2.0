---
type: 系统配置
title: Codex Local / GPT Pro 接入记录
date: 2026-06-28
---

# Codex Local / GPT Pro 接入记录

## 结论

73WIKI 已新增 `Codex Local / GPT Pro` 模型通道。

这个通道不调用 `https://api.openai.com/v1/responses`，不读取 OpenAI API key，而是通过本机 `codex exec` 使用当前 Codex CLI 的 ChatGPT 登录态。

本机已确认：

- Codex CLI: `codex-cli 0.142.3`
- Codex auth mode: `chatgpt`
- API key field: empty
- 本机连通性测试：在 `/Users/qixinchaye/wiki/73神话` 下执行 `codex exec`，模型显示 `gpt-5.5`，返回正常

## 已改动能力

- Wiki 对话框新增 Provider：`Codex Local / GPT Pro`
- 选择该 Provider 后，不显示 URL/API Key 输入框
- 默认 LLM Provider 已改为 `codex-local`
- 本机 Tauri store 已写入 `codex-local`，API key 清空
- 聊天框提问时通过 Tauri 后端启动本机 `codex exec`
- `codex exec` 使用 `--json` 输出，程序只接收 `agent_message.text`，过滤运行头、token 统计和状态信息
- 停止生成按钮会调用后端取消命令，杀掉对应 Codex 进程
- 聊天栏新增手动上下文文件选择，手动加入的 Markdown 文件优先进入提示词
- 原自动检索 wiki 页面仍保留
- Save to Wiki 按钮继续复用原有保存链路
- 验证任务提示词已加入 D+1、D+3、D+5、D+10、D+20、D+30 规范

## 安装状态

- 源码目录：`/Users/qixinchaye/Workspace/73wiki-source`
- 桌面应用：`/Applications/73WIKI.app`
- Bundle id：`com.seventythree.wiki`
- 版本：`1.0.0`
- DMG：`/Users/qixinchaye/Workspace/73wiki-source/src-tauri/target/release/bundle/dmg/73WIKI_1.0.0_aarch64.dmg`

## 保留说明

`/Applications/Trading Review Wiki.app` 后续发现容易误开旧原版并触发 OpenAI API `HTTP 401`。已在 2026-06-28 15:21 将旧原版备份，并把该路径替换为同一套 Codex Local 版本。

当前可用入口：

- `/Applications/73WIKI.app`
- `/Applications/Trading Review Wiki.app`

两者现在都指向 `com.seventythree.wiki` / `73wiki`，默认 Provider 都是 `codex-local`，API key 为空。

旧原版备份：

- `/Applications/Trading Review Wiki.app.before-codex-local-20260628152133`
