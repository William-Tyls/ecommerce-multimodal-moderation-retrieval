# Image Manifest and Embedding Cache

本文档记录多图商品的图片级数据设计。真实电商商品通常有多张图片，因此系统需要先做图片级检索，再聚合为商品级结果。

## Design Principle

不要只做商品级 embedding。

推荐流程：

```text
item
  -> image-level manifest
  -> image-level embedding
  -> image-level retrieval hits
  -> item-level aggregation
  -> image-level evidence retained
```

原因：

- 风险可能只出现在详情图、包装图或 OCR 图里。
- 多张图平均成一个商品 embedding 会稀释少数风险图。
- 审核员需要知道“到底是哪张图命中”，而不是只看到商品 ID。

## Current Manifest

当前由 `items.csv` 派生：

```bash
python3 scripts/build_image_manifest.py --items data/items.csv --output data/image_manifest.csv
```

当前字段：

```text
image_id
item_id
image_index
image_role
image_path
is_primary
title
category
shop_id
risk_labels
risk_objects
source
split
```

当前规则：

- 第一张图默认为 `main`。
- 后续图片默认是 `detail_1`、`detail_2` 等。
- 如果图片路径包含 package / ocr / text 等关键词，会推断为对应 role。

当前 v0.1 状态：

```text
items: 120
image rows: 120
primary images: 120
```

当前每个商品仍然只有一张主图，所以 manifest 行数等于 item 数。后续真实商品接入多图后，同一个 `item_id` 会展开成多行。

## Retrieval Output

图片检索结果需要同时保留 query image 和 matched image：

```text
query_item_id
query_image_id
query_image
query_image_role
matched_item_id
matched_image_id
matched_image
matched_image_role
rank
score
kept
```

当前 `scripts/run_image_similarity.py` 已经输出这些字段。

## Evidence

图片相似 evidence 应保留图片级线索：

```json
{
  "item_id": "sku_000046",
  "risk_type": "image_duplicate",
  "evidence": {
    "type": "image_to_item_similarity",
    "query_image": "data/samples/dup_earbuds_main.jpg",
    "matched_item_id": "sku_000047",
    "matched_image_id": "sku_000047_img_main",
    "matched_image_path": "data/samples/dup_earbuds_main.jpg",
    "matched_image_role": "main",
    "score": 1.0
  }
}
```

## Future Embedding Cache

后续接入 CLIP / Chinese CLIP / SigLIP 时，建议落地为 JSONL 或 parquet：

```text
image_id
item_id
image_path
image_role
encoder_name
encoder_version
embedding_dim
embedding_path
created_at
```

小样本可以直接把 vector 存在 JSONL；真实数据建议把向量存为 `.npy` / parquet / 向量库，manifest 只保存索引和元数据。

## Aggregation

第一版商品级聚合建议：

```text
item_score = max(image_scores)
```

同时保留：

```text
best_image_id
best_image_role
best_image_score
hit_image_count
```

审核场景里，一张图违规就足以进入人工复核，所以 `max` 比平均更适合 MVP。
