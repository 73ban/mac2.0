# OCR截图识别能力体检

- 生成时间：2026-07-06 07:58:43
- 状态：可直接OCR
- tesseract：`not found`
- version：-
- PaddleOCR：可用：PaddleOCR PP-OCRv6 small
- PaddleOCR Python：`.venv-ocr/bin/python`
- PaddlePaddle：`3.3.1`
- PaddleOCR版本：`3.7.0`
- PP-OCRv6 small模型：已就绪
- raw/08 原图数：25
- raw/08 `.ocr.md`：26
- raw/08 `.ocr.json`：25
- 缺侧车原图数：0

## 使用规则

- 截图原图仍统一进入 `raw/08-截图`。
- 默认优先使用 PaddleOCR PP-OCRv6 small；少数低置信度、版面复杂图再交给视觉模型复核。
- 自动化规则见 [[截图OCR自动化规则]]。
- OCR 不可用时，不阻塞入库；重要截图后续人工或外部OCR补文本。
