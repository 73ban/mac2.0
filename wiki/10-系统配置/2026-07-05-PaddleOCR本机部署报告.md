# 2026-07-05 PaddleOCR 本机部署报告

- 部署时间：2026-07-05 11:00
- 目标：给 `raw/08-截图` 提供本机 OCR，减少视觉模型图片 token 消耗。
- 结论：已可用。

## 部署内容

| 项 | 状态 |
|---|---|
| Python 环境 | `.venv-ocr` |
| OCR 包 | `paddleocr==3.7.0` |
| 推理框架 | `paddlepaddle==3.3.1` |
| 检测模型 | `PP-OCRv6_small_det` |
| 识别模型 | `PP-OCRv6_small_rec` |
| 模型缓存 | `/Users/qixinchaye/.paddlex/official_models` |
| 健康检查 | `python3 raw/07-系统脚本/codex_ocr_healthcheck.py --write` |

## 资源占用

| 目录 | 大小 |
|---|---:|
| `.venv-ocr` | 约 785 MB |
| `/Users/qixinchaye/.paddlex` | 约 30 MB |

## 实测

- 样本：`raw/08-截图/飞书图片/2026/07/05`
- 批量：9 张 WebP
- 总耗时：约 26 秒
- 单张耗时：约 2.6-4.4 秒
- 平均置信度：约 0.90-0.99
- 结论：适合新增截图触发和每日批量补跑；不建议高频实时全量扫描。

## 使用命令

单张：

```bash
python3 raw/07-系统脚本/codex_paddleocr_raw08.py --image raw/08-截图/飞书图片/2026/07/05/9d6fa25201e1.webp --force
```

按日期批量：

```bash
python3 raw/07-系统脚本/codex_paddleocr_raw08.py --date 2026-07-05 --limit 20
```

输出：

- `*.ocr.md`：可读文本侧车
- `*.ocr.json`：结构化行、置信度、框位置
- `data/facts/screenshot_ocr_index.jsonl`：索引总账

## 自动化配置

已配置用户级 LaunchAgent：

```text
~/Library/LaunchAgents/com.73wiki.paddleocr-raw08.plist
```

运行入口：

```text
.system/scripts/paddleocr-raw08-watch.sh
raw/07-系统脚本/start_paddleocr_raw08_watch.sh
```

频率：

- `RunAtLoad=true`
- `StartInterval=300`，每 5 分钟扫描一次
- 每次最多处理 20 张未 OCR 图片
- 有锁：`.system/locks/paddleocr-raw08.lock`，避免多实例重叠

自动化流程：

```text
图片进入 raw/08-截图
-> LaunchAgent 每 5 分钟扫描未识别图片
-> 调用 raw/07-系统脚本/codex_paddleocr_raw08.py
-> 生成同目录 OCR 侧车
-> 追加 data/facts/screenshot_ocr_index.jsonl
```

稳定规则页：

```text
wiki/10-系统配置/截图OCR自动化规则.md
```

保存位置：

| 内容 | 位置 |
|---|---|
| 原图 | `raw/08-截图/.../*.png|jpg|jpeg|webp` |
| 可读 OCR | 原图同目录，文件名追加 `.ocr.md` |
| 结构化 OCR | 原图同目录，文件名追加 `.ocr.json` |
| OCR 总索引 | `data/facts/screenshot_ocr_index.jsonl` |
| 自动任务日志 | `.system/logs/paddleocr-raw08.out.log`、`.system/logs/paddleocr-raw08.err.log` |

服务状态检查：

```bash
launchctl print gui/501/com.73wiki.paddleocr-raw08
```

## 使用边界

- 中文截图主体识别效果好。
- 英文小字、UI 装饰、低清图会有误识别。
- 盘口/表格截图仍需人工或视觉模型复核重点数值。
- 低置信度行优先进入人工复核，不直接进入交易结论。
