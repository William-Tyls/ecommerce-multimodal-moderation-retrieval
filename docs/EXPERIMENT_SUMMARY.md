# Experiment Summary

本文档汇总当前合成数据闭环里的关键实验结果，用于最终报告和后续模型选择。当前结论只代表 v0.4 / v0.5 synthetic datasets，不代表真实线上分布。

## Current Objective

技术部已确认暂时无法提供真实平台数据，因此当前第一目标调整为：

```text
基于合成数据完成完整流程：
数据生成 -> OCR / 规则 / 文本检索 -> 图片 embedding 检索 -> 轻量微调 -> 评估 -> 报告
```

真实数据需求仍保留在 `docs/REAL_DATASET_REQUIREMENTS.md`，但不再阻塞当前主线。

## Dataset Summary

| Dataset | Purpose | Size | Key Design |
| --- | --- | ---: | --- |
| v0.4 synthetic platform | End-to-end audit pipeline and fine-tuning | 500 items / 485 unique images | Platform-style synthetic goods with controlled risk labels and OCR overlays |
| v0.5 image retrieval | Near-duplicate and hard-negative image retrieval | 160 items / 120 unique images | 40 groups, each with anchor, exact duplicate, near duplicate, hard negative |

## v0.4 End-to-End Audit Baseline

v0.4 baseline covers rules, OCR, text retrieval, local image similarity, evidence building, and case evaluation.

| Metric | Value |
| --- | ---: |
| Items / cases | 500 / 500 |
| Binary precision | 1.000000 |
| Binary recall | 0.996000 |
| Binary F1 | 0.997996 |
| Macro F1 | 0.957468 |
| Micro F1 | 0.941399 |

Per-label result:

| Label | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| counterfeit_brand | 0.666667 | 1.000000 | 0.800000 |
| image_duplicate | 1.000000 | 1.000000 | 1.000000 |
| misleading_claim | 1.000000 | 0.975000 | 0.987342 |
| off_platform_contact | 1.000000 | 1.000000 | 1.000000 |
| prohibited_goods | 1.000000 | 1.000000 | 1.000000 |

Interpretation:

- The full audit pipeline is already usable as an MVP regression baseline.
- The main remaining baseline error is `counterfeit_brand` precision, where duplicate / same-style wording can be over-interpreted as brand infringement.
- This baseline is intentionally rule-heavy and evidence-friendly; it is not meant to prove generalization.

## v0.4 Lightweight Fine-Tuning

Fine-tuning experiments use frozen image embeddings plus a lightweight classifier or adapter. The split is 16 train / 8 validation / remaining test per label.

| Backbone | Method | Test Accuracy | Test Macro F1 | Best Hyperparameter |
| --- | --- | ---: | ---: | --- |
| CLIP ViT-B/32 | Tip-Adapter-style | 0.884831 | 0.791881 | beta=50 |
| CLIP ViT-B/32 | Linear probe | 0.957865 | 0.915325 | C=100 |
| SigLIP base patch16 | Tip-Adapter-style | 0.924157 | 0.865321 | beta=50 |
| SigLIP base patch16 | Linear probe | 0.988764 | 0.972048 | C=100 |

Interpretation:

- Linear probe is stronger than Tip-Adapter-style cache classification on this synthetic image classification task.
- SigLIP outperforms CLIP under both lightweight adaptation methods.
- Current best synthetic fine-tuning configuration is `SigLIP + Linear Probe`.
- The high score is plausible for controlled synthetic data, but should be reported as synthetic-data evidence rather than expected production accuracy.

## v0.5 Image Retrieval

v0.5 evaluates whether image embeddings can recover exact / near duplicates while rejecting visually similar hard negatives.

### Best / Strict Operating Points

| Model | Operating Point | Precision | Recall | F1 | Hard Negative FP |
| --- | --- | ---: | ---: | ---: | ---: |
| SimpleImageEncoder | strict, score=0.999999 | 1.000000 | 0.333333 | 0.500000 | 0 |
| CLIP ViT-B/32 | best-F1, score=0.95 | 0.583333 | 0.816667 | 0.680556 | 8 |
| CLIP ViT-B/32 | strict, score=0.97 | 0.729730 | 0.450000 | 0.556701 | 0 |
| Chinese-CLIP ViT-B/16 | best-F1, score=0.97 | 0.676558 | 0.950000 | 0.790295 | 6 |
| Chinese-CLIP ViT-B/16 | strict, score=0.985 | 0.779221 | 0.500000 | 0.609137 | 0 |
| SigLIP base patch16 | best / strict, score=0.97 | 0.711974 | 0.916667 | 0.801457 | 0 |

Interpretation:

- `SimpleImageEncoder` mainly catches exact duplicates and misses many near duplicates.
- CLIP improves near-duplicate retrieval, but strict filtering causes recall to drop sharply.
- Chinese-CLIP is competitive at best-F1 and has high recall, but still keeps hard-negative false positives at its best-F1 point.
- SigLIP is the strongest current retrieval backbone: at score `0.97`, it keeps hard-negative false positives at 0 while maintaining recall `0.916667`.

## Backbone Conclusion

Across the two main visual experiments, SigLIP is currently the best default backbone:

| Task | Best Model | Evidence |
| --- | --- | --- |
| v0.4 lightweight classification | SigLIP + Linear Probe | test macro F1 `0.972048` |
| v0.5 near-duplicate retrieval | SigLIP | F1 `0.801457`, recall `0.916667`, hard FP `0` |

Recommended current system choice:

```text
Primary image backbone: SigLIP
Primary v0.5 threshold: 0.97
Primary lightweight fine-tuning baseline: Linear probe on frozen SigLIP embeddings
```

CLIP remains a useful baseline. Chinese-CLIP should be kept as a comparison model, especially for future text-image or Chinese text-conditioned retrieval, but current pure image retrieval evidence does not beat SigLIP.

## Why the CLIP Thresholded Metrics Matter

The CLIP v0.5 thresholded JSON files are needed for experiment completeness:

- They make the CLIP comparison reproducible from local files rather than chat history.
- They support automatic summary table generation.
- They preserve both operating points: best-F1 and strict no-hard-negative-FP.
- They make the SigLIP recommendation auditable, because the CLIP control group is fully documented.

Required local files now present:

```text
outputs/metrics/v0_5_clip_group_image_similarity_best_f1_metrics.json
outputs/metrics/v0_5_clip_group_image_similarity_strict_metrics.json
```

## Caveats

- All current results are based on synthetic data.
- v0.4 labels and visual styles are controlled, so classification scores are likely optimistic.
- v0.5 is useful for testing relative model behavior, but its hard negatives are generated from our synthetic image distribution.
- A real platform dataset would still be needed before claiming production performance.

## Next Steps

1. Use SigLIP as the default visual backbone in final report and demo narrative.
2. Keep CLIP and Chinese-CLIP as comparison baselines.
3. Build the final report around three claims: complete audit pipeline, measurable near-duplicate retrieval, and lightweight synthetic fine-tuning.
4. If time allows, add a small script to generate this summary table directly from metrics JSON files.
