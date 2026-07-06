# 截图OCR自动化规则

```yaml
type: 系统配置
owner: Codex
status: 已启用
engine: PaddleOCR PP-OCRv6 small
updated: 2026-07-05
```

## 目标

`raw/08-截图` 是所有截图原图入口。截图先由 Mac 本机 OCR 自动识别，降低视觉模型图片 token 消耗；只有低置信度、盘口表格复杂图、关键交易数值才再交给人工或视觉模型复核。

## 自动化流程

```text
图片进入 raw/08-截图/任意子目录
-> LaunchAgent 每 5 分钟扫描未识别图片
-> 每次最多处理 20 张
-> 调用 PaddleOCR PP-OCRv6 small 本机推理
-> 在原图同目录生成 OCR 侧车
-> 追加 OCR 总索引
-> 数据接口总控验收
```

## 后台任务

| 项 | 配置 |
|---|---|
| LaunchAgent | `~/Library/LaunchAgents/com.73wiki.paddleocr-raw08.plist` |
| 用户级标签 | `com.73wiki.paddleocr-raw08` |
| 运行入口 | `raw/07-系统脚本/start_paddleocr_raw08_watch.sh` |
| 包装入口 | `.system/scripts/paddleocr-raw08-watch.sh` |
| 扫描频率 | 每 300 秒 |
| 单次上限 | 20 张未 OCR 图片 |
| 锁文件 | `.system/locks/paddleocr-raw08.lock` |
| 日志 | `.system/logs/paddleocr-raw08.out.log`、`.system/logs/paddleocr-raw08.err.log` |

## 保存位置

| 内容 | 保存位置 |
|---|---|
| 原图 | `raw/08-截图/.../*.png|jpg|jpeg|webp|bmp` |
| 可读 OCR | 原图同目录，文件名追加 `.ocr.md` |
| 结构化 OCR | 原图同目录，文件名追加 `.ocr.json` |
| 总索引 | `data/facts/screenshot_ocr_index.jsonl` |
| 健康状态 | `.system/ocr-health.json` |
| 能力体检 | `wiki/10-系统配置/OCR截图识别能力体检.md` |
| 总控报告 | `wiki/09-统计与进化/YYYY-MM-DD-数据接口运行总控报告.md` |

## 手动命令

按日期补跑：

```bash
python3 raw/07-系统脚本/codex_paddleocr_raw08.py --date YYYY-MM-DD --limit 20
```

单张重跑：

```bash
python3 raw/07-系统脚本/codex_paddleocr_raw08.py --image raw/08-截图/路径/图片.webp --force
```

健康检查：

```bash
python3 raw/07-系统脚本/codex_ocr_healthcheck.py --write
```

服务状态：

```bash
launchctl print gui/$(id -u)/com.73wiki.paddleocr-raw08
```

## 入库规则

- OCR 结果仍属于 RAW 辅助材料，不直接生成交易结论。
- 图片先入 RAW，OCR 只做文字侧车，不覆盖原图。
- `.ocr.md` 用于人工快速阅读。
- `.ocr.json` 用于后续结构化抽取、关键词检索、低置信度复核。
- `avgScore < 0.85`、盘口表格、价格/涨跌幅/数量等关键数值，默认需要复核。
- 系统方法论截图识别后可沉淀到 `wiki/10-系统配置`。
- 交易截图识别后进入作战室、个股档案、复盘或 D+验证前，必须保留原图路径作为证据。

## OCR 后分流

| 图片类型 | 分流位置 | 规则 |
|---|---|---|
| 交易截图 | `raw/01-交割单`、`raw/02-每日复盘`、`raw/04-市场数据` | 交割单、委托、持仓、盘口、市场数据按事实层归类 |
| 公告/互动问答截图 | `raw/05-研报新闻` | 只作事实证据，不直接写交易结论 |
| 短线知识/淘股吧/公众号图片 | `raw/09-短线知识` | 原文和截图先保真，再提炼 |
| 系统方法论截图 | `wiki/10-系统配置` | 必须保留原图或 OCR 侧车证据路径 |
| Codex 分析产物 | `raw/11-Codex分析产物` | 只能放派生分析，不混入事实层 receiveonly 目录 |

## 边界

- PaddleOCR 适合中文截图主体文本。
- 长图和表格能识别，但关键数值不能无复核直接用于买卖判断。
- 低清、压缩、遮挡、UI 小字可能误识别。
- 自动任务只扫描新增或缺侧车图片；不会覆盖已有结果，除非手动加 `--force`。
