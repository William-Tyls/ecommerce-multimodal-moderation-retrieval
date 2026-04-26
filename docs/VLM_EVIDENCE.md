# Qwen2.5-VL 图片理解证据

本模块用于把多模态大模型的图片理解结果接入审核证据链。

## 模块位置

```text
商品图片
  -> Qwen2.5-VL 图片理解
  -> 结构化视觉风险 JSON
  -> vlm_evidence.jsonl
  -> build_evidence.py
  -> 商品级 audit case
```

SigLIP 负责“相似商品 / 近重复图片检索”，Qwen2.5-VL 负责“图片中是否存在可解释的违规元素”。

## 文件

```text
configs/vlm_prompts.yaml
src/vlm/qwen_vl.py
scripts/run_vlm_evidence.py
outputs/evidence/vlm_evidence.jsonl
outputs/evidence/vlm_summary.csv
```

## Evidence Schema

每个视觉风险判断会写成一条 JSONL evidence：

```json
{
  "item_id": "sku_000001",
  "risk_type": "counterfeit_brand",
  "confidence": 0.82,
  "evidence": {
    "type": "vlm_visual_risk",
    "field": "image",
    "image_id": "sku_000001_img_main",
    "image_path": "data/images/sku_000001/main.jpg",
    "image_role": "main",
    "caption": "商品主图中出现疑似品牌 logo",
    "ocr_like_text": ["同款", "高仿"],
    "risk_objects": ["logo", "luxury_brand_style"],
    "evidence_reason": "图片中包含疑似品牌标识和高仿表达",
    "bbox": [120, 80, 260, 180],
    "model": "Qwen/Qwen2.5-VL-3B-Instruct",
    "prompt_id": "ecommerce_visual_risk",
    "snippet": "图片中包含疑似品牌标识和高仿表达"
  },
  "suggested_action": "manual_review"
}
```

如果模型无法稳定定位区域，`bbox` 可以为 `null`。

## Dry Run

没有安装或下载 Qwen2.5-VL 时，可以用 `metadata` backend 验证 schema 和 evidence builder：

```bash
python scripts/run_vlm_evidence.py \
  --items data/items.csv \
  --backend metadata \
  --include-missing \
  --output outputs/evidence/vlm_evidence.jsonl \
  --summary outputs/evidence/vlm_summary.csv
```

## Qwen2.5-VL 推理

安装依赖后运行：

```bash
python scripts/run_vlm_evidence.py \
  --items data/items.csv \
  --backend qwen_vl \
  --model-name Qwen/Qwen2.5-VL-3B-Instruct \
  --device auto \
  --output outputs/evidence/vlm_evidence.jsonl \
  --summary outputs/evidence/vlm_summary.csv
```

再把 VLM evidence 合入 audit case：

```bash
python scripts/build_evidence.py \
  --items data/items.csv \
  --evidence outputs/evidence/rule_evidence.jsonl \
  --evidence outputs/evidence/ocr_rule_evidence.jsonl \
  --evidence outputs/evidence/clip_image_similarity_evidence.jsonl \
  --evidence outputs/evidence/vlm_evidence.jsonl \
  --include-clean
```

## 说明

- VLM 输出作为证据源之一，不直接替代规则、OCR 或 SigLIP 检索。
- Prompt 要求模型输出严格 JSON，便于下游解析。
- 生产使用前需要基于业务数据校准 prompt、阈值和风险标签。
