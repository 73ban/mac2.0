# Firecrawl短线知识抓取评估与接入规则

## 安装状态

本机已安装 Firecrawl CLI，并已部署 Firecrawl 开源自托管服务：

```text
firecrawl-cli@1.19.24
服务目录：/Users/qixinchaye/services/firecrawl
本地 API：http://127.0.0.1:3002
Docker compose：已接入
```

说明：

- 当前不依赖 firecrawl.dev 云账号。
- 不需要登录 Firecrawl 账号才能抓淘股吧公开文章。
- 自部署 API 返回 metadata 里仍可能出现 `creditsUsed` 字段，这是 Firecrawl 统一返回格式里的内部计数，不代表消耗云账号额度。
- 服务只绑定本机 `127.0.0.1:3002`，不对外网开放。

## 2026-07-05 小样本测试

测试输出目录：

```text
raw/11-Codex分析产物/Firecrawl评估/2026-07-05/
```

| 来源 | 测试结果 | 结论 |
| --- | --- | --- |
| 同花顺热榜接口 | 能抓到 100 条，字段含排名、代码、名称、热度、涨跌幅、题材标签、部分 AI 分析标题和分析正文。强制刷新约 9.7 秒，`creditsUsed=5`。 | 可作为备份验证源，但不应替代直接接口/Playwright。直接接口更快、更省、字段一样接近。 |
| 东方财富网页行情中心 | 能抓到页面壳、导航和链接，但没有拿到核心行情表；页面出现滑块验证提示。 | 不适合用 Firecrawl 抓东方财富网页行情。东方财富仍应走 API/数据接口。 |
| 淘股吧首页 | 能抓到公开栏目、推荐和 `/a/...` 文章链接。 | 可作为公开帖子发现入口。 |
| 淘股吧公开文章 | 能抓到作者、标题、发布时间、浏览/评论数和正文 Markdown。 | 适合作为短线知识自学习入口。 |

## 结论

Firecrawl 对 73wiki 的真正价值不在行情数据，而在“网页文章转干净 Markdown”：

- 淘股吧公开高手帖；
- 淘股吧实盘复盘帖；
- 游资/短线心得公开网页；
- 情绪状态类论坛讨论；
- 需要网页正文清洗的学习材料。

Firecrawl 不适合替代：

- tdxrs 行情底座；
- 通达信涨停、连板、资金、龙虎榜；
- 同花顺热榜直接接口；
- 东方财富行情 API；
- WeRSS 和 URL 种子公众号链路。

## RAW落点

Firecrawl 抓到的原文放：

```text
raw/09-短线知识/淘股吧/YYYY-MM-DD/
```

Codex 提炼产物放：

```text
raw/11-Codex分析产物/短线知识提炼/YYYY-MM-DD/
```

验证后才允许进入：

```text
wiki/04-L4交易模式/
wiki/05-错误库/
wiki/09-统计与进化/
```

## 抓取边界

只抓公开网页，不抓登录后、付费、私密、绕权限内容。

不全站乱抓，只抓三类：

1. 用户指定的高手、实盘、战法、复盘文章。
2. 首页/精华/实盘比赛里公开推荐的高价值帖子。
3. 与当前持仓、候选、主线题材相关的公开讨论。

## 自进化闭环

每篇短线知识必须按这个链路处理：

```text
网页原文
-> RAW保真
-> 提取观点/交易动作/情绪状态/适用条件
-> 对照当日市场环境、涨停全景、连板天梯、板块强度、龙虎榜
-> 标记是否有后视镜风险
-> D+1/D+3/D+5验证
-> 有效才升级规则，无效降权或丢弃
```

## 使用规则

当前只允许手动或低频运行。

禁止接入：

- 15 分钟云数据任务；
- 盘中高频任务；
- 同花顺热榜主链路；
- 东方财富行情主链路。

允许接入：

- 周末短线知识学习；
- 晚间低频公开文章采集；
- 用户指定 URL 的单篇抓取；
- 历史高手帖回补。

## 当前脚本

已提供轻量脚本：

```text
raw/07-系统脚本/codex_firecrawl_taoguba_fetch.py
raw/07-系统脚本/start_firecrawl_selfhost.sh
raw/07-系统脚本/stop_firecrawl_selfhost.sh
raw/07-系统脚本/status_firecrawl_selfhost.sh
```

用途：把指定淘股吧公开文章抓到 RAW，不做规则升级。

示例：

```bash
python3 raw/07-系统脚本/codex_firecrawl_taoguba_fetch.py \
  --date 2026-07-05 \
  --url https://www.tgb.cn/a/2taZOtt7m49
```

脚本默认走本机自部署 API：

```text
http://127.0.0.1:3002
```

如果服务未启动，脚本会自动执行：

```bash
docker compose up -d
```

服务管理：

```bash
raw/07-系统脚本/status_firecrawl_selfhost.sh
raw/07-系统脚本/start_firecrawl_selfhost.sh
raw/07-系统脚本/stop_firecrawl_selfhost.sh
```
