# WeRSS 私密公众号补种说明

更新时间：2026-07-01

## 适用场景

- 公众号关闭了微信搜索入口
- WeRSS 里已有旧订阅，但新环境或新会话里无法通过搜索重新发现
- 典型例子：`爱在冰川`

## 当前做法

不再依赖公众号搜索，也不依赖旧 Windows 服务器 WeRSS 入口，而是走下面这条链：

`分享文章链接 -> 反查公众号 biz/fakeid -> 写回 WeRSS -> 直接刷新文章列表`

## 已落地文件

- 项目根目录：`/Users/qixinchaye/wiki/73神话`
- 本机 WeRSS：`http://127.0.0.1:8002`
- URL 种子：`/Users/qixinchaye/wiki/73神话/.system/wechat-mp-url-seeds.json`
- 15 分钟主任务：`/Users/qixinchaye/wiki/73神话/.system/scripts/run-cloud-data-connectors.mjs`
- RAW 落点：`/Users/qixinchaye/wiki/73神话/raw/05-研报新闻/公众号/游资号/`

## 配置格式

```json
{
  "items": [
    {
      "mp_name": "爱在冰川",
      "category": "游资号",
      "article_url": "https://mp.weixin.qq.com/s/replace-with-a-shared-article-url",
      "end_page": 5
    }
  ]
}
```

## 使用方式

1. 往 `werss-private-mp-seeds.json` 里填 1 篇这个公众号的分享文章链接
2. 15 分钟主任务会走本机 WeRSS 与 URL 种子双通道
3. 补种成功后，WeRSS 会把该公众号恢复为可直接刷新
4. 后续常规抓取继续走 `本机 WeRSS API + URL 种子直抓 -> RAW -> OCR/游资学习`

## 说明

- 这条链适合“搜不到，但文章链接能拿到”的公众号
- 如果公众号更换 `biz` 或文章已全部不可见，需要重新提供新的分享链接
- 以今天 Mac 本机 WeRSS 订阅为准，旧服务器曾保留但不需要的游资号不再继续抓取
