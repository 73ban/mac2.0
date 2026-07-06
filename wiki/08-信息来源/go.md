```
---
type: source
title: go - 批量HTML转Markdown脚本
created: 2026-06-11
updated: 2026-06-11
tags: [数据管道, PowerShell, HTML转换]
related: ["批量HTML转Markdown脚本", "数据摄入管道", "管道脚本设计原则"]
sources: ["go.txt"]
confidence_grade: A
confidence_reason: 源文件本身，未经处理的原始资料
---

# go - 批量HTML转Markdown脚本

## 概述

`go.txt` 是一个 PowerShell 脚本，用于将 `raw\公众号` 目录下的所有 HTML 文件批量转换为 Markdown 文件，作为数据摄入管道的上游自动化步骤。该脚本设计要点包括：

- **幂等性**：跳过已存在同名 `.md` 的文件，避免重复转换。
- **来源追溯**：自动提取 HTML 中的来源行（格式 `作者|公众号名`）并写入 MD 头部。
- **内容清洗**：移除公众号平台专用标签（如 `<mp-common-profile>`），转换图片为 Markdown 语法，解码 HTML 实体。
- **进度反馈**：每 100 个文件输出转换进度，最终展示汇总统计。

## 核心逻辑

```powershell
$rawRoot = "C:\wiki\73神话\raw\公众号"
...
if (Test-Path $mdPath) { $skipped++; continue }
...
$md = @"
# $title
> 来源: $source
---
$body
"@
```

## 管道位置

该脚本位于 `raw/` 到 `wiki/sources/` 的中间环节，属于 [[数据摄入管道]] 的 HTML→MD 转换步骤。

## 相关页面

- 本脚本的 wiki 条目：[[批量HTML转Markdown脚本]]
- 设计原则：[[管道脚本设计原则]]
- 格式规范：[[源文档格式规范]]
- 运维监控：[[数据管道健康检查]]
```
