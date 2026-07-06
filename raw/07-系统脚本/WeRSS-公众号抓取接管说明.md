# WeRSS-公众号抓取接管说明

更新时间：2026-07-01

## 目的

由 Codex 在 Mac 本机接管公众号抓取，不再依赖旧 Windows 服务器暴露的 WeRSS 入口，也不再依赖河马手工搬运或粗转换。

## 入口

- 项目根目录：`/Users/qixinchaye/wiki/73神话`
- 本机 WeRSS：`http://127.0.0.1:8002`
- WeRSS 服务 LaunchAgent：`~/Library/LaunchAgents/com.73wiki.local-werss.plist`
- 15 分钟主任务 LaunchAgent：`~/Library/LaunchAgents/com.73wiki.cloud-data-connectors.plist`
- 主任务脚本：`/Users/qixinchaye/wiki/73神话/.system/scripts/run-cloud-data-connectors.mjs`
- URL 种子：`/Users/qixinchaye/wiki/73神话/.system/wechat-mp-url-seeds.json`
- RAW 落点：`/Users/qixinchaye/wiki/73神话/raw/05-研报新闻/公众号/游资号/`

## 工作流

1. 本机 WeRSS 维护公众号订阅列表。
2. 15 分钟任务刷新 WeRSS 订阅文章。
3. WeRSS 文章写入 RAW。
4. URL 种子直抓补充 WeRSS 覆盖不到的文章。
5. 图片进入本机 OCR，OCR 文本随 RAW 一起供游资学习流水线提炼。

## 当前抓取顺序

`财联社 -> 腾讯行情 -> 同花顺热榜 -> WeRSS订阅更新 -> WeRSS写RAW -> URL直抓写RAW -> OCR/学习状态健康检查`

## 当前规则

- `category` 默认写 `游资号`，但建议只给真正的交易类来源。
- 非交易公众号不要放进 `游资号`。
- 新来源先小批量验证，确认正文质量后再长期订阅。
- 以今天 Mac 本机 WeRSS 订阅列表为准，旧服务器保留过但今天不需要的游资号不再继续抓。
- 同一篇文章按 `来源 + guid/link + 标题 + 时间` 去重；URL 种子直抓和 WeRSS 抓取重复时，以去重状态为准。

## 建议

- 新公众号优先先加入本机 WeRSS；搜不到或私域号再加入 URL 种子。
- 不再使用 Windows `.ps1` 后台启动脚本作为 Mac 当前入口。
