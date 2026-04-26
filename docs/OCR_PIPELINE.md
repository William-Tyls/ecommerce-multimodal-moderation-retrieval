# OCR Pipeline

本文档记录 OCR baseline 的当前设计和运行方式。

## Goal

OCR 用于把商品图片中的可见文本转成可检索、可规则匹配、可进入 evidence chain 的结构化证据。

当前 OCR pipeline 分两步：

```text
item image
  -> image-level OCR records
  -> OCR text rule matching
  -> ocr_rule_evidence.jsonl
  -> build_evidence.py aggregate audit cases
```

## Scripts

生成图片级 OCR 记录：

```bash
python3 scripts/run_ocr.py \
  --items data/items.csv \
  --backend auto \
  --output outputs/ocr/item_ocr.jsonl
```

对 OCR 文本跑现有规则：

```bash
python3 scripts/run_ocr_rules.py \
  --ocr outputs/ocr/item_ocr.jsonl \
  --output outputs/evidence/ocr_rule_evidence.jsonl \
  --summary outputs/evidence/ocr_rule_summary.csv
```

把 OCR evidence 聚合进审核 case：

```bash
python3 scripts/build_evidence.py \
  --items data/items.csv \
  --evidence outputs/evidence/rule_evidence.jsonl \
  --evidence outputs/evidence/duplicate_evidence.jsonl \
  --evidence outputs/evidence/retrieval_evidence.jsonl \
  --evidence outputs/evidence/image_similarity_evidence.jsonl \
  --evidence outputs/evidence/ocr_rule_evidence.jsonl \
  --output outputs/evidence/audit_cases_with_ocr.jsonl \
  --summary outputs/evidence/audit_cases_with_ocr.csv \
  --include-clean
```

## Backends

`scripts/run_ocr.py` 当前支持：

- `--backend metadata`：使用 `items.csv` 中已有 `ocr_text` 字段作为 fallback OCR。
- `--backend tesseract`：尝试使用 `pytesseract` + Pillow 直接识别图片。
- `--backend auto`：优先尝试 tesseract；不可用时回退到 metadata。

当前本地环境检查：

```text
tesseract: 5.5.2 installed by Homebrew
tesseract-lang: 4.1.0 installed by Homebrew, 163 languages, includes eng and chi_sim
pytesseract: 0.3.13 installed in project .venv
Pillow in .venv: 12.2.0
```

安装体积：

```text
tesseract: 34.9 MB
tesseract-lang: 685.7 MB
pytesseract wheel: 14 KB
Pillow wheel: 4.7 MB
```

真实 OCR 命令需要使用项目 `.venv`，因为当前系统 `python3` 是 Anaconda 且未安装 `pytesseract`：

```bash
.venv/bin/python scripts/run_ocr.py \
  --items data/items.csv \
  --backend tesseract \
  --languages eng+chi_sim \
  --output outputs/ocr/item_ocr_tesseract.jsonl
```

曾尝试过 macOS 系统 OCR helper，但当前 CommandLineTools/runtime 环境中预检失败，相关实验代码已移除，避免后续维护负担。

## Output Schema

`outputs/ocr/item_ocr.jsonl` 每行是一张图片的 OCR 记录：

```json
{
  "item_id": "sku_000001",
  "image_id": "sku_000001_img_main",
  "image_index": 0,
  "image_role": "main",
  "image_path": "data/samples/sku_000001_main.jpg",
  "image_exists": 1,
  "ocr_text": "VAPE",
  "backend": "metadata_ocr_text",
  "source": "metadata",
  "confidence": 1.0
}
```

OCR evidence 会保留图片定位信息：

```json
{
  "item_id": "sku_000001",
  "risk_type": "prohibited_goods",
  "evidence": {
    "type": "ocr_text_keyword_match",
    "field": "ocr_text",
    "matched_text": "VAPE",
    "image_id": "sku_000001_img_main",
    "image_path": "data/samples/sku_000001_main.jpg",
    "ocr_backend": "metadata_ocr_text",
    "ocr_source": "metadata"
  }
}
```

## Current v0.1 Smoke Result

```text
OCR records written: 120
Records with text: 34
OCR evidence records: 13
Matches by risk type:
  off_platform_contact: 7
  prohibited_goods: 6
audit_cases_with_ocr errors found: 0
```

## Current Tesseract Smoke Result

```text
.venv/bin/python scripts/run_ocr.py --backend tesseract
OCR backend: pytesseract
OCR records written: 120
Records with text: 38
records using pytesseract image OCR: 7

.venv/bin/python scripts/run_ocr_rules.py --ocr outputs/ocr/item_ocr_tesseract.jsonl
OCR evidence records: 10
Matches by risk type:
  off_platform_contact: 6
  prohibited_goods: 4

audit_cases_with_tesseract_ocr errors found: 0
```

注意：当前 `data/samples/` 是合成占位图，Tesseract 对其中部分文字识别成噪声，例如 `vape kit` 被识别成不稳定片段。因此 Tesseract 输出目前作为真实 OCR 对比实验保存在 `outputs/ocr/item_ocr_tesseract.jsonl`，暂不覆盖默认 `outputs/ocr/item_ocr.jsonl`。
