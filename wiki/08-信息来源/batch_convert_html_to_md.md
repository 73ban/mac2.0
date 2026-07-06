```yaml
---
type: source
title: 批量HTML转Markdown脚本
created: 2026-06-11
updated: 2026-06-11
tags: ["工具", "数据管道"]
related: ["股痴流沙河", "交割单摄入覆盖率", "元分析"]
sources: ["batch_convert_html_to_md.txt"]
confidence_grade: A
confidence_reason: 源代码直接分析
---

# 批量HTML转Markdown脚本

> 一键转换 `raw/公众号` 下的所有HTML文件为规范化Markdown，保留来源和时间元信息。

## 管道位置
此脚本位于**知识库上游**的第2步：

```
原始数据（公众号HTML） → 【此脚本】 → 标准化MD → LLM分析摄入 → wiki条目
```

转换后的MD文件中嵌入了标题和来源行（`> 来源: …`），为后续分析提供了可追溯的元数据。

## 关键设计
- **幂等跳过**：已存在同名`.md`时自动跳过，适合增量更新。
- **噪音清理**：自动移除公众号导出中的`mp-common-profile`等样式块，保留正文。
- **信息保留**：提取 `<title>` 和来源段落，确保内容可追溯至[[股痴流沙河]]的原文。

## 状态与问题
`$total` 计数表明已有大量HTML待转换。若这些HTML长期未被转换并摄入，会导致[[交割单摄入覆盖率]]问题—知识库出现数据断层。
与此相关，**元分析**提醒我们需追踪“已转换但未摄入”的MD文件，确保管道完整。

## 使用
在PowerShell中直接运行该脚本即可处理新增文件。
