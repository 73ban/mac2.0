```
---
type: source
title: 批量HTML转Markdown脚本
created: 2026-06-11
updated: 2026-06-11
tags: [数据管道, PowerShell]
related: ["go - 批量HTML转Markdown脚本", "数据摄入管道", "管道脚本设计原则"]
sources: ["go.txt", "batch_convert_html_to_md.txt"]
confidence_grade: A
confidence_reason: 源文件 go.txt 的直接体现，并基于 batch_convert_html_to_md.txt 验证
---

# 批量HTML转Markdown脚本

## 概述

该页面对应源文件 `go.txt`，是一个 PowerShell 脚本，用于批量将微信公众号导出的 HTML 文章转换为 Markdown 格式，作为整个 [[数据摄入管道]] 的自动化上游步骤。

## 脚本功能

- 递归扫描 `C:\wiki\73神话\raw\公众号` 下所有 `*.html` 文件。
- 对每个文件，若同名的 `.md` 不存在，则执行转换：
  1. 提取 `<title>` 作为标题。
  2. 匹配来源行 `<p>...|...</p>` 作为来源标识。
  3. 删除公众号平台噪音标签（`mp-common-profile` 等）。
  4. 将 `<img>` 转为 `![]()` 语法。
  5. 移除所有剩余 HTML 标签，解码实体，压缩多余空行。
- 输出头格式：
  ```
  # 标题
  > 来源: 作者|公众号名
  ---
  正文
  ```
- 统计最终结果并显示。

## 设计原则

该脚本体现了 [[管道脚本设计原则]] 中的多项原则：幂等性、来源追溯、可观测性。

## 相关页面

- 源文件摘要：[[go - 批量HTML转Markdown脚本]]
- 管道概念：[[数据摄入管道]]
- 运维监控：[[数据管道健康检查]]
```
