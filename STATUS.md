# Project Status

最后更新：2026-04-26 04:40 AEST

本文档用于在上下文窗口不足、会话压缩、或下次重新打开项目时快速续上当前进度。恢复上下文时建议先读 `PROJECT_FLOW.md`，再读本文档。

## TL;DR

当前项目已经从通用多模态检索作业，改造成“电商平台违规内容审核多模态图文检索系统”的 MVP。

核心目标：

- 用自然语言查询疑似违规商品。
- 检索商品标题、描述、图片等多模态信息。
- 识别违禁品、假货/盗版、站外导流、夸大宣传、盗图/重复铺货等风险。
- 生成可解释证据链，帮助审核员定位商品、查看命中原因、辅助处理。

当前阶段：MVP 广度优先。

最新策略更新：由于时间原因，真实平台手动收集/标注暂时降级；下一阶段优先使用 API 批量生成平台风格合成数据，把指标脚本、Tip-Adapter 数据准备和 Qwen2.5-VL 指令数据流程先跑通。

最新进展：v0.4 synthetic platform 500 条数据已经跑通 baseline 回归；新增 `scripts/run_v0_4_pipeline.sh` 和 `docs/V0_4_BASELINE.md`，完成规则、Tesseract OCR、文本检索、LSI 语义检索确认、本地图片相似、证据聚合和指标评估。

RunPod 进展：v0.4 CLIP ViT-B/32 image embedding baseline 已跑通。`openai/clip-vit-base-patch32` 在 v0.4 exact duplicate 子集上，`min_score=0.995` 时 image retrieval 达到 pair precision / recall / F1 = 1.0 / 1.0 / 1.0。

v0.5 进展：已新增 image retrieval hard-case 数据集生成器和 group-aware 评估脚本，生成 40 组、160 item、120 唯一图片的 near-duplicate / hard-negative 数据。SimpleImageEncoder 在无误报阈值 `0.999999` 下 precision=1.0 但 recall=0.333333；CLIP ViT-B/32 在 best-F1 阈值 `0.95` 下 precision=0.583333、recall=0.816667、F1=0.680556，在 strict 阈值 `0.97` 下 hard_negative_false_positive=0、precision=0.72973、recall=0.45、F1=0.556701。Chinese-CLIP 在 best-F1 阈值 `0.97` 下 precision=0.676558、recall=0.95、F1=0.790295、hard_fp=6，在 strict 阈值 `0.985` 下 hard_fp=0、precision=0.779221、recall=0.5、F1=0.609137。SigLIP 在 `0.97` 阈值下同时作为 best/strict operating point：hard_negative_false_positive=0、precision=0.711974、recall=0.916667、F1=0.801457，是当前最强 v0.5 图搜 backbone。

策略调整：技术部明确做不了真实数据采集，后续第一目标改为“基于合成数据把完整流程跑完”，包括 CLIP/SigLIP embedding、近重复检索、few-shot adapter、linear probe 轻量微调、评估和最终报告。不再等待真实数据。

微调进展：已新增 `scripts/build_finetune_splits.py`、`scripts/run_tip_adapter.py`、`scripts/run_linear_probe.py` 和 `docs/SYNTHETIC_FINETUNING.md`。v0.4 few-shot split 已生成：每个标签 16 train / 8 val / 剩余 test。Tip-Adapter-style 与 linear probe 已用本地 LSI text embedding smoke 跑通，并已在 RunPod 上用 CLIP ViT-B/32 和 SigLIP image embeddings 跑通正式结果。CLIP: Tip-Adapter-style test accuracy=0.884831、macro_f1=0.791881；linear probe test accuracy=0.957865、macro_f1=0.915325。SigLIP: Tip-Adapter-style test accuracy=0.924157、macro_f1=0.865321；linear probe test accuracy=0.988764、macro_f1=0.972048。当前最佳合成微调配置为 SigLIP + Linear Probe。

实验汇总：`docs/EXPERIMENT_SUMMARY.md` 已新增，统一记录 v0.4 端到端 baseline、v0.4 轻量微调、v0.5 CLIP / Chinese-CLIP / SigLIP 图搜 hard-case 对比、模型选择结论和 caveats。CLIP v0.5 best-F1 / strict thresholded metrics JSON 已补拉到本地，当前核心实验产物闭环完整。

已经跑通：

```text
商品数据
  -> 规则检测
  -> 文本检索
  -> 图片相似检索 baseline
  -> 图片相似评估
  -> 证据聚合
  -> 审核 case
  -> 指标评估
  -> CLI 自然语言查询入口
```

重要策略：先把完整链路打通，再回来优化各模块。规则 baseline 已经有第一轮效果，不要继续只深挖规则；后续做完 MVP 后再回到规则、检索阈值、图片模型、真实数据集上逐步增强。

## Project Positioning

项目包装方向：

> 针对电商平台违规内容审核中违禁词、盗图、假货导流等内容排查效率低、人工审核耗时长的问题，构建一套支持自然语言问答式交互的多模态图文检索系统，实现对违规商品图文的精确定位、证据链构建与高效处理。

当前 MVP 不追求一开始就训练大模型，而是先搭出可演示、可评估、可替换模型的系统骨架：

- 规则检测负责高精度、可解释 baseline。
- 文本检索负责自然语言到商品的召回。
- 图片检索负责盗图、重复铺货、近重复图识别。
- Evidence Builder 负责把不同来源的证据聚合成审核 case。
- CLI 查询入口模拟审核员问答式使用方式。

## Current Phase

当前阶段：MVP 广度优先搭建。

已完成模块：

- 商品 metadata schema：`data/items.csv`
- 风险标签体系：`configs/risk_labels.yaml`
- 规则配置：`configs/rules.yaml`
- 检索 query 配置：`configs/retrieval_queries.yaml`
- 数据校验：`scripts/validate_items.py`
- 规则检测：`scripts/run_rules.py`
- exact duplicate 检测：`scripts/detect_duplicates.py`
- 文本检索：`scripts/run_text_retrieval.py` + `src/retrieval/text_search.py`
- 检索后处理：`src/retrieval/filters.py`
- 轻量 query router：`src/agents/router.py`
- CLI 查询入口：`scripts/query_cli.py`
- 样例图片生成：`scripts/generate_sample_images.py`
- 图片级 manifest：`scripts/build_image_manifest.py` -> `data/image_manifest.csv`
- 图片 encoder baseline：`src/models/image_encoder.py`
- CLIP/SigLIP image embedding smoke：`scripts/smoke_clip_image_encoder.py`
- CLIP/SigLIP image embedding cache：`scripts/compute_clip_image_embeddings.py`
- CLIP/SigLIP image-to-item retrieval：`scripts/run_clip_image_retrieval.py`
- 图片相似检索：`src/retrieval/image_search.py`
- 单图查询：`scripts/query_image.py`
- OCR baseline：`src/ocr/backends.py` + `scripts/run_ocr.py`
- OCR 规则证据：`scripts/run_ocr_rules.py`
- 批量图片相似证据：`scripts/run_image_similarity.py`
- 图片相似指标评估：`scripts/evaluate_image_similarity.py`
- 文本检索 TopK/阈值扫描：`scripts/sweep_text_retrieval.py`
- 图片相似阈值扫描：`scripts/sweep_image_similarity.py`
- Evidence Builder：`scripts/build_evidence.py` + `src/evidence/builder.py`
- 审核指标评估：`scripts/evaluate_cases.py` + `src/evaluation/metrics.py`
- 检索指标评估：`scripts/evaluate_retrieval.py`
- 误报/漏报分析：`scripts/analyze_errors.py`

当前样本：

- `data/items.csv` 中有 120 条 synthetic 商品数据。
- `data/items_v0_2.csv` 中有 536 条 v0.2 candidate 商品数据，保留 v0.1 的 120 条 seed items，新增 380 条 `synthetic_v0_2_template` 样本，并加入 36 条 `curated_v0_2_seed` 人工样本。
- `data/samples/` 中有 110 张本地生成样例图。
- `data/image_manifest.csv` 中有 120 条图片级记录，当前均为 `main` 图。
- `data/image_manifest_v0_2.csv` 中有 536 条图片级记录；`data/items_v0_2.csv` 对应 510 张唯一占位图。
- `scripts/expand_sample_items.py` 可以确定性生成/刷新其中 70 条 `synthetic_v0_1_template` 样本。
- `scripts/expand_sample_items_v0_2.py` 可以确定性生成 `data/items_v0_2.csv`，默认不覆盖 `data/items.csv`。
- `docs/DATASET_V0_1.md` 记录了当前小数据集画像。
- `docs/DATASET_V0_2.md` 记录了 v0.2 candidate 数据集画像、生成方式和第一轮校验结果。
- `data/seeds/v0_2_curated_items.csv` 是人工维护高质量 v0.2 seed 的预留入口；`docs/CURATED_SEEDS.md` 记录用法。
- `data/seeds/v0_3_semireal_items.csv` 已填充 120 条 semi-real 商品样本，并通过 `validate_items.py` 校验。
- `data/image_manifest_v0_3.csv` 已生成，v0.3 对应 120 条图片级记录和 114 张唯一占位图。
- `src/retrieval/embedding_text_search.py` 和 `scripts/run_embedding_text_retrieval.py` 已接入本地 dense embedding retrieval baseline。
- `scripts/run_embedding_text_retrieval.py` 已支持 `--backend auto|lsi_tfidf_svd|sentence_transformers`，可在有模型环境中使用真实语义 embedding，在当前本地环境中自动回退到 LSI。
- 本地 `.venv` 已安装 `sentence-transformers` 和 `torch`，并已用真实语义模型重跑 v0.3 文本 embedding retrieval。
- `scripts/confirm_semantic_retrieval.py` 已加入两阶段语义确认：semantic retrieval 先召回候选，只把已有同风险证据确认过的候选写入 audit evidence。
- `scripts/query_cli.py` 已支持 `--semantic-candidates`，可在 CLI demo 中展示语义候选与 confirmed semantic evidence 的区别。
- LLM-ready intent router 已接入：`configs/intent_router.yaml`、`src/agents/intent_router.py`、`scripts/evaluate_intent_router.py`、`data/eval/intent_router_v0_1.csv`、`docs/LLM_INTENT_ROUTER.md`。
- `docs/EMBEDDING_TEXT_RETRIEVAL.md` 记录了 embedding retrieval 的运行方式、缓存和 v0.3 指标。
- `docs/IMAGE_MANIFEST_AND_EMBEDDINGS.md` 记录了多图商品、图片级检索和 embedding cache 设计。
- `docs/CLOUD_SETUP.md` 已更新为当前云端 GPU 行动版：目标是 CLIP/SigLIP embedding inference，不是训练。
- `docs/OCR_PIPELINE.md` 记录了 OCR baseline、输出 schema 和当前 v0.1 smoke 结果。
- `requirements-cloud.txt`、`scripts/check_gpu_env.py`、`scripts/smoke_clip_image_encoder.py`、`scripts/compute_clip_image_embeddings.py`、`scripts/run_clip_image_retrieval.py` 已加入，用于云端依赖安装、GPU/CUDA 检查、CLIP 图片 embedding smoke、embedding cache 和 image-to-item 检索。
- `docs/DATASET_V0_4_CRAWLED.md` 和 `scripts/crawl_v0_4_items.py` 已加入，用于下一阶段小规模真实电商平台商品营销图数据集采集；当前只提供合规边界、通用 HTML/JSON-LD/OG 解析骨架和 items CSV 输出，不做平台反爬绕过。
- `docs/DATASET_PLAN.md`、`configs/synthetic_v0_4_generation.yaml`、`scripts/build_synthetic_platform_dataset.py` 已加入，用于生成 500 条平台风格合成商品数据计划，并可选择调用 OpenAI Image API 生成图片。
- v0.4 synthetic platform 数据已按“两阶段方法”生成完成：500 条 item、500 条图片引用、485 张唯一图片文件、缺失图片路径 0；`data/image_manifest_v0_4_synthetic_platform.csv` 已重建为 500 行。
- `scripts/run_v0_4_pipeline.sh` 已加入，用于一键跑 v0.4 baseline 回归；默认 OCR backend 为 `auto`，语义检索 backend 为 `lsi_tfidf_svd`，本地图片相似阈值为 `0.999999`。
- `docs/V0_4_BASELINE.md` 已记录 v0.4 baseline 流程、输出文件、第一轮指标、CLIP image baseline 和主要错误。
- `scripts/build_v0_5_image_retrieval_dataset.py`、`scripts/evaluate_group_image_retrieval.py` 和 `docs/DATASET_V0_5_IMAGE_RETRIEVAL.md` 已加入，用于构造和评估 near-duplicate / hard-negative 图搜数据。
- `data/seeds/v0_5_image_retrieval_items.csv`、`data/image_manifest_v0_5_image_retrieval.csv` 和 `data/generated/v0_5_image_retrieval/images/` 已生成第一版 v0.5 图搜难例集。
- `data/eval/v0_4_finetune_splits.csv` 已生成，用于合成数据 few-shot adapter / linear probe 实验。
- `docs/SYNTHETIC_FINETUNING.md` 已记录合成数据微调策略、命令和本地 LSI smoke 指标。
- 当前样例足够支撑 MVP 演示和 pipeline 回归，但不代表真实线上效果。

## Risk Labels

当前风险标签：

- `prohibited_goods`：违禁品、管制品、平台禁售商品。
- `counterfeit_brand`：疑似假货、仿牌、品牌侵权。
- `image_duplicate`：疑似盗图、重复铺货、近重复图片。
- `off_platform_contact`：站外导流、私下交易、加联系方式。
- `misleading_claim`：夸大宣传、绝对化承诺、虚假功效。
- `normal`：正常商品。

## Pipeline

当前完整 pipeline：

```bash
python3 scripts/validate_items.py --items data/items.csv --risk-labels configs/risk_labels.yaml
python3 scripts/expand_sample_items.py --base data/items.csv --output data/items.csv
python3 scripts/validate_items.py --items data/items.csv --risk-labels configs/risk_labels.yaml
python3 scripts/run_rules.py --items data/items.csv --rules configs/rules.yaml --risk-labels configs/risk_labels.yaml
python3 scripts/detect_duplicates.py --items data/items.csv --output outputs/evidence/duplicate_evidence.jsonl
python3 scripts/run_text_retrieval.py --items data/items.csv --queries configs/retrieval_queries.yaml --rules configs/rules.yaml
python3 scripts/evaluate_retrieval.py --items data/items.csv --results outputs/retrieval_results/text_retrieval.csv
python3 scripts/sweep_text_retrieval.py --items data/items.csv --queries configs/retrieval_queries.yaml --rules configs/rules.yaml
python3 scripts/generate_sample_images.py --items data/items.csv
python3 scripts/build_image_manifest.py --items data/items.csv --output data/image_manifest.csv
python3 scripts/run_image_similarity.py --items data/items.csv
python3 scripts/evaluate_image_similarity.py --items data/items.csv --results outputs/retrieval_results/image_similarity.csv
python3 scripts/sweep_image_similarity.py --items data/items.csv --results outputs/retrieval_results/image_similarity.csv
python3 scripts/build_evidence.py --items data/items.csv \
  --evidence outputs/evidence/rule_evidence.jsonl \
  --evidence outputs/evidence/duplicate_evidence.jsonl \
  --evidence outputs/evidence/retrieval_evidence.jsonl \
  --evidence outputs/evidence/image_similarity_evidence.jsonl \
  --include-clean
python3 scripts/evaluate_cases.py --items data/items.csv --cases outputs/evidence/audit_cases.jsonl --risk-labels configs/risk_labels.yaml
python3 scripts/analyze_errors.py --items data/items.csv --cases outputs/evidence/audit_cases.jsonl
```

如果只想快速看 CLI 效果：

```bash
python3 scripts/query_cli.py --query "找疑似电子烟商品" --only-risk
python3 scripts/query_cli.py --query "查一下加微信私聊的商品" --only-risk
python3 scripts/query_cli.py --query "查前10个疑似高仿商品" --only-risk
python3 scripts/query_cli.py --query "今天天气怎么样"
```

如果只想测试图片查询：

```bash
python3 scripts/query_image.py --query-image data/samples/dup_earbuds_main.jpg --exclude-item sku_000046 --only-risk
```

注意：CLI 依赖 `outputs/evidence/audit_cases.jsonl`。如果规则、检索、图片证据或数据有变化，需要先重新跑完整 pipeline。

如果想生成 v0.2 candidate 数据集：

```bash
python3 scripts/expand_sample_items_v0_2.py --base data/items.csv --output data/items_v0_2.csv
python3 scripts/validate_items.py --items data/items_v0_2.csv --risk-labels configs/risk_labels.yaml
python3 scripts/generate_sample_images.py --items data/items_v0_2.csv
python3 scripts/build_image_manifest.py --items data/items_v0_2.csv --output data/image_manifest_v0_2.csv
```

可选追加人工 curated seed：

```bash
python3 scripts/expand_sample_items_v0_2.py \
  --base data/items.csv \
  --output data/items_v0_2.csv \
  --curated-seeds data/seeds/v0_2_curated_items.csv
```

## Current Outputs

核心输出文件：

- `outputs/evidence/rule_evidence.jsonl`：规则命中的证据。
- `outputs/evidence/duplicate_evidence.jsonl`：基于 image_url/hash 的重复图证据。
- `outputs/evidence/retrieval_evidence.jsonl`：文本检索产生的证据。
- `outputs/evidence/image_similarity_evidence.jsonl`：图片相似检索产生的证据。
- `outputs/ocr/item_ocr.jsonl`：图片级 OCR 输出。
- `outputs/evidence/ocr_rule_evidence.jsonl`：OCR 文本规则命中证据。
- `outputs/evidence/ocr_rule_summary.csv`：OCR 规则证据摘要。
- `outputs/evidence/audit_cases_with_ocr.jsonl`：加入 OCR evidence 后的审核 case。
- `outputs/evidence/audit_cases_with_ocr.csv`：加入 OCR evidence 后的审核 case CSV。
- `outputs/evidence/audit_cases.jsonl`：聚合后的审核 case。
- `outputs/evidence/audit_cases.csv`：审核 case 的表格版本。
- `outputs/retrieval_results/text_retrieval.csv`：文本检索结果。
- `outputs/retrieval_results/image_similarity.csv`：图片相似结果。
- `data/image_manifest.csv`：从 item metadata 派生的图片级 manifest。
- `data/items_v0_2.csv`：536 条 v0.2 candidate 商品数据。
- `data/image_manifest_v0_2.csv`：v0.2 图片级 manifest。
- `outputs/evidence/v0_2_rule_evidence.jsonl`：v0.2 规则证据。
- `outputs/evidence/v0_2_duplicate_evidence.jsonl`：v0.2 exact duplicate 证据。
- `outputs/evidence/v0_2_audit_cases.jsonl`：v0.2 聚合后的审核 case。
- `outputs/evidence/v0_2_retrieval_evidence.jsonl`：v0.2 文本检索证据。
- `outputs/evidence/v0_2_image_similarity_evidence.jsonl`：v0.2 图片相似证据。
- `outputs/evidence/v0_2_audit_cases_full.jsonl`：v0.2 四路证据完整聚合 case。
- `outputs/metrics/v0_2_evaluation_summary.json`：v0.2 第一轮审核指标。
- `outputs/metrics/v0_2_label_metrics.csv`：v0.2 各标签指标。
- `outputs/metrics/v0_2_error_analysis.csv`：v0.2 误报/漏报分析。
- `outputs/metrics/v0_2_full_evaluation_summary.json`：v0.2 四路证据完整审核指标。
- `outputs/metrics/v0_2_full_error_analysis.csv`：v0.2 四路证据完整错误分析。
- `outputs/metrics/v0_2_retrieval_metrics.json`：v0.2 文本检索指标。
- `outputs/metrics/v0_2_text_retrieval_sweep.json`：v0.2 文本检索 TopK/阈值扫描。
- `outputs/metrics/v0_2_image_similarity_metrics.json`：v0.2 图片相似指标。
- `outputs/metrics/v0_2_image_similarity_sweep.json`：v0.2 图片相似阈值扫描。
- `outputs/metrics/evaluation_summary.json`：审核整体指标。
- `outputs/metrics/label_metrics.csv`：各标签指标。
- `outputs/metrics/error_analysis.csv`：误报/漏报分析。
- `outputs/metrics/retrieval_metrics.json`：检索指标。
- `outputs/metrics/image_similarity_metrics.json`：图片相似检索指标。
- `outputs/metrics/image_similarity_metrics.csv`：每个图片 query 的相似检索指标。
- `outputs/metrics/text_retrieval_sweep.json`：文本检索 TopK/阈值扫描。
- `outputs/metrics/image_similarity_sweep.json`：图片相似阈值扫描。

## Latest Metrics

最近一次完整 pipeline 已接入：

```text
rule evidence
duplicate evidence
retrieval evidence
image similarity evidence
```

OCR baseline 已接入并跑通：

```text
scripts/run_ocr.py
scripts/run_ocr_rules.py
src/ocr/backends.py
docs/OCR_PIPELINE.md
```

当前本地 `--backend auto` 因无可用 pytesseract，正常回退到 `metadata_ocr_text`。v0.1 smoke：

```text
OCR records written: 120
Records with text: 34
OCR evidence records: 13
Matches by risk type:
  off_platform_contact: 7
  prohibited_goods: 6
audit_cases_with_ocr errors found: 0
```

真实 OCR backend 清理：

```text
已移除失败的 macOS 系统 OCR helper 实验代码。
已移除未安装前暂不使用的其他真实 OCR 分支。
当前保留 backend: metadata, tesseract, auto。
```

Tesseract OCR 已安装并验证：

```text
brew install tesseract tesseract-lang
  tesseract 5.5.2: 34.9 MB
  tesseract-lang 4.1.0: 685.7 MB
.venv/bin/python -m pip install pytesseract
  pytesseract 0.3.13 wheel: 14 KB
  Pillow 12.2.0 wheel: 4.7 MB

tesseract --list-langs:
  163 languages, includes eng and chi_sim

重要：pytesseract 安装在项目 .venv；系统 python3/Anaconda 未安装 pytesseract。
真实 OCR 命令使用 .venv/bin/python。
```

Tesseract v0.1 smoke：

```text
.venv/bin/python scripts/run_ocr.py --items data/items.csv --backend tesseract --languages eng+chi_sim --output outputs/ocr/item_ocr_tesseract.jsonl
OCR backend: pytesseract
OCR records written: 120
Records with text: 38
records using pytesseract image OCR: 7

.venv/bin/python scripts/run_ocr_rules.py --ocr outputs/ocr/item_ocr_tesseract.jsonl --output outputs/evidence/ocr_rule_evidence_tesseract.jsonl --summary outputs/evidence/ocr_rule_summary_tesseract.csv
OCR evidence records: 10
Matches by risk type:
  off_platform_contact: 6
  prohibited_goods: 4

python3 scripts/build_evidence.py --items data/items.csv --evidence outputs/evidence/rule_evidence.jsonl --evidence outputs/evidence/duplicate_evidence.jsonl --evidence outputs/evidence/retrieval_evidence.jsonl --evidence outputs/evidence/image_similarity_evidence.jsonl --evidence outputs/evidence/ocr_rule_evidence_tesseract.jsonl --output outputs/evidence/audit_cases_with_tesseract_ocr.jsonl --summary outputs/evidence/audit_cases_with_tesseract_ocr.csv --include-clean
python3 scripts/analyze_errors.py --items data/items.csv --cases outputs/evidence/audit_cases_with_tesseract_ocr.jsonl
Errors found: 0
```

注意：当前 `data/samples/` 是合成占位图，Tesseract 对部分小字/合成字识别成噪声，OCR rule evidence 少于 metadata fallback 的 13 条。因此默认 `outputs/ocr/item_ocr.jsonl` 暂不覆盖，Tesseract 输出作为对比实验保留在 `outputs/ocr/item_ocr_tesseract.jsonl`。

## Cloud GPU Preparation For CLIP

当前判断：OCR 已作为旁路证据链跑通，下一步主线应转向 CLIP / SigLIP 图文 embedding，而不是继续深挖 OCR。

已完成云端准备：

- `docs/CLOUD_SETUP.md` 重写为当前行动版。
- `requirements-cloud.txt` 补充 `huggingface_hub`、`pytesseract`。
- 新增 `scripts/smoke_clip_image_encoder.py`，用于云端验证 `transformers + torch + CLIP/SigLIP + image loading` 是否跑通。
- 新增 `scripts/compute_clip_image_embeddings.py`，用于从 `data/image_manifest.csv` 批量生成 CLIP/SigLIP image embedding cache。
- 新增 `scripts/run_clip_image_retrieval.py`，用于从 embedding cache 跑 image-to-item 检索并输出 CSV/evidence。

建议云端第一批命令：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-cloud.txt
python scripts/check_gpu_env.py
python scripts/smoke_clip_image_encoder.py \
  --items data/items.csv \
  --model-name openai/clip-vit-base-patch32 \
  --device auto \
  --limit 6
```

期望 smoke 输出：

```text
Model: openai/clip-vit-base-patch32
Device: cuda
Images encoded: 6
Embedding shape: (6, 512)
Similarity matrix
```

RunPod 远程实测：

```text
Model: openai/clip-vit-base-patch32
Device: cuda
Images encoded: 6
Embedding shape: (6, 512)
```

下一批云端命令：

```bash
python scripts/compute_clip_image_embeddings.py \
  --manifest data/image_manifest.csv \
  --model-name openai/clip-vit-base-patch32 \
  --device auto \
  --batch-size 32 \
  --output outputs/embeddings/clip_image_embeddings.npz \
  --manifest-output outputs/embeddings/clip_image_embeddings_manifest.csv

python scripts/run_clip_image_retrieval.py \
  --embeddings outputs/embeddings/clip_image_embeddings.npz \
  --manifest outputs/embeddings/clip_image_embeddings_manifest.csv \
  --top-k 5 \
  --min-score 0.0 \
  --results outputs/retrieval_results/clip_image_similarity.csv \
  --output outputs/evidence/clip_image_similarity_evidence.jsonl
```

注意：第一轮 `--min-score 0.0` 是为了保留候选并观察 CLIP 相似度分布，不能复用 SimpleImageEncoder 的 `0.996` 阈值。

## Dataset v0.4 Crawled Platform Items

当前判断：公开商品实拍/包装数据集不能充分代表本项目场景，因为电商审核更需要平台商品营销图、标题、详情文案和图片中文字。下一阶段主线应构建 `v0.4` 小规模真实平台展示数据。

已新增：

```text
docs/DATASET_V0_4_CRAWLED.md
scripts/crawl_v0_4_items.py
.gitignore: data/crawled/ and outputs/crawl/
```

1688 first attempt 已准备：

```text
data/seeds/v0_4_1688_urls.example.txt
scripts/crawl_v0_4_items.py: 1688 title/shop/category/image URL 轻量解析增强
scripts/crawl_v0_4_items.py: --save-pages / --page-dir 页面诊断开关
```

注意：1688 可能有登录、验证码、频率限制和动态渲染。当前只做公开详情页小样本 smoke，不做代理、登录态复用、验证码绕过或签名接口逆向。

一次真实 1688 smoke：

```text
URL: https://detail.1688.com/offer/807952309703.html
结果: blocked
返回: _____tmd_____/punish 风控跳转页
结论: 不能直接拿到商品 title/image；后续不要走绕过路线，需换普通公开可访问 URL 或考虑其他平台。
```

京东 first attempt：

```text
URL: https://item.jd.com/100012326151.html
结果: blocked
返回: 京东验证 / JDR_shields 风控验证页
结论: 普通 Python 请求不能直接拿到商品 title/image；京东不适合作为第一批自动化采集主源。
```

手动保存页面解析已接入：

```text
scripts/parse_saved_pages_to_items.py
input: data/crawled/v0_4/pages_manual/*.html + sibling *_files/
output: data/seeds/v0_4_manual_items.csv
```

当前用户保存了一个京东商品页：

```text
title: 迪卡侬运动纯棉t恤男纯色圆领半袖打底跑步健身短袖2511132深蓝XL
source_url: https://item.jd.com/100022378624.html?...#switch-sku
canonical/mobile sku: 100022378608
local resources: 约 100 个本地文件引用，含商品/评论/推荐图片和页面组件
```

初步判断：可以解析出 title、source_url、规格/价格片段和本地图片候选；但页面会混入推荐商品和浏览器插件 DOM，图片需要抽查。

手动页解析器已做数据质量修正：

```text
source_url 优先使用 canonical URL，避免 pcdk/spmTag 等长参数污染。
推荐区图片硬排除。
评论区图片仅作为 fallback，parse_status 标记为 needs_review。
parse_notes 改为计数型摘要，避免长 CSV 噪声。
```

第一批目标：

```text
items: 约 200
images per item: 1-5
source: 公开可访问商品页
fields: title, description, category, shop_id, image_paths, source_url, source_platform
default label: normal，后续再人工/半自动标注风险
```

最小采集命令：

```bash
python3 scripts/crawl_v0_4_items.py \
  --input-urls data/seeds/v0_4_urls.txt \
  --output data/seeds/v0_4_crawled_items.csv \
  --image-dir data/crawled/v0_4/images \
  --limit 20 \
  --delay 2.0 \
  --download-images
```

后续回归：

```bash
python3 scripts/validate_items.py --items data/seeds/v0_4_crawled_items.csv --risk-labels configs/risk_labels.yaml
python3 scripts/build_image_manifest.py --items data/seeds/v0_4_crawled_items.csv --output data/image_manifest_v0_4.csv
```

合规边界：只采公开页面、小规模、限速、保留来源 URL；不绕过登录、验证码、签名接口或其他反自动化机制。

云端实例建议：

```text
RTX 4090 / RTX 3090 / L4 / A5000
显存 24GB 优先，16GB 可做最小 smoke
磁盘 80-150GB
Ubuntu 22.04
```

最近结果：

```text
Evidence records loaded: 176
Audit cases written: 120
```

审核二分类指标：

```text
precision: 1.0
recall: 1.0
f1: 1.0
false_positive_rate: 0.0
```

多标签指标：

```text
Macro F1: 1.0
Micro F1: 1.0
```

文本检索指标：

```text
macro precision@kept: 1.0
macro recall@kept: 0.285434
top1 accuracy: 1.0
```

图片相似检索指标：

```text
image queries: 120
duplicate queries: 17
relevant duplicate pairs: 26
kept rows: 26
pair precision@kept: 1.0
pair recall@kept: 1.0
duplicate query hit rate: 1.0
duplicate Top1 accuracy: 1.0
no false positive query rate: 1.0
```

当前错误统计：

```text
Errors found: 0
```

v0.2 candidate 当前已加入 36 条人工 curated seed。规则 + exact duplicate 阶段结果：

```text
items: 536
unique sample images: 510
image manifest rows: 536
rule evidence records: 209
duplicate evidence records: 49
audit cases: 536
binary precision: 1.0
binary recall: 1.0
binary f1: 1.0
macro f1: 1.0
micro f1: 1.0
errors found: 0
```

curated seed 初次加入后暴露过 1 个误报和 3 个漏报，已小范围修复：

- `off_platform_contact` 增加 `加微`、`WX`、`wx`。
- `counterfeit_brand` 增加 `大牌平替`、`1比1`，并加入 `非...同款/仿款/品牌` 否定语境排除。
- `misleading_claim` 增加 `肉眼可见`。
- v0.1 回归仍保持 Errors found: 0。

v0.2 完整 MVP pipeline 已接入：

```text
rule evidence
duplicate evidence
text retrieval evidence
image similarity evidence
```

完整 pipeline 结果：

```text
text retrieval evidence: 31
image similarity evidence: 58
full evidence records loaded: 347
full audit cases: 536
binary precision: 1.0
binary recall: 1.0
binary f1: 1.0
macro f1: 1.0
micro f1: 1.0
errors found: 0
```

解释：完整 pipeline 的 1.0 只代表当前 synthetic + curated v0.2 回归集，不代表真实线上效果。

v0.2 文本检索指标：

```text
macro precision@kept: 1.0
macro recall@kept: 0.216192
top1 accuracy: 1.0
best recall @ macro precision>=0.9: top_k=20 min_score=0.03 precision=0.944933 recall=0.394363
```

v0.2 图片相似指标：

```text
image queries: 536
duplicate queries: 49
relevant duplicate pairs: 58
kept rows: 58
pair precision@kept: 1.0
pair recall@kept: 1.0
best threshold: min_score=0.996
```

## Dataset v0.3 Semi-Real Seed

`data/seeds/v0_3_semireal_items.csv` 当前已从 filled 文件替换为正式 v0.3 seed，包含 120 条 semi-real 商品样本：

```text
items: 120
normal: 70
off_platform_contact: 15
counterfeit_brand: 15
image_duplicate: 12
prohibited_goods: 10
misleading_claim: 10
split: 70 test / 20 val / 30 train
```

已检查：

- `python3 scripts/validate_items.py --items data/seeds/v0_3_semireal_items.csv --risk-labels configs/risk_labels.yaml` 通过。
- 6 组 `image_duplicate` 样本已修正为每组 2 条商品共享同一个 `image_paths`。
- `data/seeds/v0_3_semireal_items_filled.csv` 已重命名替换为 `data/seeds/v0_3_semireal_items.csv`，当前 `data/seeds/` 只保留 v0.2 和 v0.3 seed 文件。

v0.3 第一轮完整 MVP pipeline 已跑通：

```text
rule evidence
duplicate evidence
text retrieval evidence
image similarity evidence
```

核心输出：

- `data/image_manifest_v0_3.csv`
- `outputs/evidence/v0_3_rule_evidence.jsonl`
- `outputs/evidence/v0_3_duplicate_evidence.jsonl`
- `outputs/evidence/v0_3_retrieval_evidence.jsonl`
- `outputs/evidence/v0_3_image_similarity_evidence.jsonl`
- `outputs/evidence/v0_3_audit_cases_full.jsonl`
- `outputs/metrics/v0_3_full_evaluation_summary.json`
- `outputs/metrics/v0_3_full_label_metrics.csv`
- `outputs/metrics/v0_3_full_error_analysis.csv`

v0.3 完整四路 evidence baseline：

```text
full evidence records loaded: 68
full audit cases: 120
binary precision: 1.0
binary recall: 0.62
binary f1: 0.765432
macro f1: 0.648148
micro f1: 0.757282
errors found: 44
```

v0.3 按标签表现：

```text
counterfeit_brand: precision=0.833333 recall=0.666667 f1=0.740741
image_duplicate: precision=1.0 recall=1.0 f1=1.0
misleading_claim: precision=0.0 recall=0.0 f1=0.0
off_platform_contact: precision=1.0 recall=0.866667 f1=0.928571
prohibited_goods: precision=1.0 recall=0.4 f1=0.571429
```

v0.3 检索表现：

```text
text retrieval macro precision@kept: 0.8
text retrieval macro recall@kept: 0.086667
text retrieval top1 accuracy: 0.8
image similarity pair precision@kept: 1.0
image similarity pair recall@kept: 1.0
```

v0.3 暴露的问题：

- `misleading_claim` 的自然表达基本漏掉，例如“明显变白”“快速瘦腰”“改善睡眠”“一次使用即可提升色阶”“30天长出新发”。
- `prohibited_goods` 对“户外折叠刀”“仿真手枪模型”“模型枪”“雪茄”“RX ONLY / RX SLEEP”等变体召回不足。
- `counterfeit_brand` 中“男女同款”被宽泛 `同款` 规则误报。
- TF-IDF query 模板在 v0.3 上召回弱，下一步需要 query 扩展或 embedding 检索。

建议：保留 v0.3 第一轮结果作为 semi-real baseline，不要立刻为了满分大幅改规则；下一步做小范围规则校准 + query 扩展，然后再评估是否接入 embedding 模型。

v0.3 calibration pass 1 已完成，小范围修复明确漏报/误报：

- `off_platform_contact` 增加 `号码联系`、`团购V`。
- `prohibited_goods` 增加 `折叠刀`、`弹簧开合小刀`、`开合小刀`、`手枪模型`、`模型枪`、`雪茄`、`CIGAR`、`RX` 等。
- `counterfeit_brand` 增加 `仿牌`、`仿奢`、`仿品牌`、`一比一`、`高版本`，并排除 `男女同款/儿童同款/亲子同款` 等日常语境。
- `misleading_claim` 增加 `明显变白`、`快速瘦`、`改善睡眠`、`一次使用`、`长出新发`、`抚平`、`提升代谢`、`无需运动`、`淡化斑点` 等表达。
- `configs/retrieval_queries.yaml` 新增 4 条 query，并扩展主 query 文案。

校准后回归：

```text
v0.1 audit errors: 0
v0.2 audit errors: 0
v0.3 rule+duplicate audit errors: 0
v0.3 full audit errors: 0
```

v0.3 校准后完整四路 evidence：

```text
full evidence records loaded: 157
full audit cases: 120
binary precision: 1.0
binary recall: 1.0
binary f1: 1.0
macro f1: 1.0
micro f1: 1.0
errors found: 0
```

v0.3 校准后文本检索：

```text
queries: 9
retrieval evidence: 43
macro precision@kept: 1.0
macro recall@kept: 0.374074
top1 accuracy: 1.0
best recall @ macro precision>=0.9: top_k=20 min_score=0.05 precision=1.0 recall=0.433333
```

CLI smoke tests 已通过：

- `查一下加微信私聊的商品`
- `找夸大宣传快速变白瘦腰的商品`

注意：v0.3 校准后的 1.0 仍只代表当前 semi-real seed 回归效果，不代表真实线上效果。下一步不要继续无限扩规则；应考虑 embedding 检索、OCR/VLM 标签和更真实图片。

## Text Embedding Retrieval Baseline

当前环境检查结果：

```text
numpy: available
sklearn: available
sentence_transformers: unavailable
```

项目本地 `.venv` 环境检查结果：

```text
python: .venv/bin/python
torch: 2.11.0
sentence-transformers: 5.4.1
transformers: 5.6.2
CUDA: unavailable on local Mac
```

因此先接入无需下载模型的 dense baseline：

```text
TF-IDF char n-gram -> TruncatedSVD -> L2 normalize -> cosine similarity
backend: lsi_tfidf_svd
```

当前脚本已预留真正语义模型 backend：

```text
--backend auto
--backend sentence_transformers
--backend lsi_tfidf_svd
```

`auto` 会优先尝试 `sentence-transformers`，如果当前环境没有依赖或模型不可用，则回退到 `lsi_tfidf_svd`。当前本地验证中，因为 `sentence_transformers` 不可用，`auto` 已正常 fallback 到 LSI。

默认 sentence-transformers 模型：

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

后续可在云端或本地新环境中尝试：

```text
BAAI/bge-m3
intfloat/multilingual-e5-base
```

注意：不同 embedding 模型的分数分布不同，接入后必须重新 sweep 阈值，不能复用 LSI 的高精度阈值。

新增文件：

- `src/retrieval/embedding_text_search.py`
- `scripts/run_embedding_text_retrieval.py`
- `scripts/sweep_retrieval_results.py`
- `docs/EMBEDDING_TEXT_RETRIEVAL.md`

本轮新增/更新：

- `src/retrieval/embedding_text_search.py` 新增 `SentenceTransformerTextEmbeddingRetriever` 和 `build_text_embedding_retriever`。
- `scripts/run_embedding_text_retrieval.py` 新增 `--backend`、`--model-name`、`--device`、`--batch-size`、`--local-files-only` 参数。
- embedding cache 的 `.npz` 和 manifest 已记录 `model_name`，方便区分不同模型实验。
- `docs/EMBEDDING_TEXT_RETRIEVAL.md` 和 `README.md` 已补充 backend 用法。

v0.3 embedding 输出：

- `outputs/evidence/v0_3_embedding_retrieval_evidence.jsonl`
- `outputs/evidence/v0_3_embedding_retrieval_high_precision_evidence.jsonl`
- `outputs/retrieval_results/v0_3_embedding_text_retrieval.csv`
- `outputs/retrieval_results/v0_3_embedding_text_retrieval_high_precision.csv`
- `outputs/embeddings/v0_3_text_item_embeddings.npz`
- `outputs/embeddings/v0_3_text_item_embeddings_manifest.csv`
- `outputs/metrics/v0_3_embedding_retrieval_metrics.json`
- `outputs/metrics/v0_3_embedding_retrieval_high_precision_metrics.json`
- `outputs/metrics/v0_3_embedding_retrieval_sweep.json`
- `outputs/metrics/v0_3_embedding_retrieval_sweep_high_threshold.json`
- `outputs/evidence/v0_3_audit_cases_embedding_full.jsonl`
- `outputs/metrics/v0_3_embedding_full_evaluation_summary.json`

v0.3 embedding default retrieval：

```text
embedding dim: 119
retrieval evidence: 85
macro precision@kept: 0.7
macro recall@kept: 0.537037
top1 accuracy: 1.0
```

本轮回归验证：

```text
python3 -m py_compile src/retrieval/embedding_text_search.py scripts/run_embedding_text_retrieval.py
--backend lsi_tfidf_svd: evidence=85, embedding_dim=119
--backend auto: fallback to lsi_tfidf_svd, evidence=85, embedding_dim=119
evaluate_retrieval: macro precision@kept=0.7, macro recall@kept=0.537037, top1 accuracy=1.0
```

真实 sentence-transformers backend 已验证：

```text
model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
embedding backend: sentence_transformers
embedding dim: 384
default evidence: 90
default retrieval macro precision@kept: 0.688889
default retrieval macro recall@kept: 0.585185
default top1 accuracy: 1.0
```

sentence-transformers wide sweep：

```text
best F1: top_k=10 min_score=0.25 precision=0.688889 recall=0.585185 f1=0.632817
best recall @ macro precision>=0.9: top_k=10 min_score=0.45 precision=0.9 recall=0.392593
```

聚合到 audit case 的结果：

```text
min_score=0.45:
  retrieval evidence: 51
  full audit binary precision: 0.943396
  full audit recall: 1.0
  errors found: 12

min_score=0.65:
  retrieval evidence: 8
  full audit binary precision: 1.0
  full audit recall: 1.0
  errors found: 0
```

结论：

- sentence-transformers 已接通，能作为真实语义 embedding backend 运行。
- 默认/低阈值更适合作为候选召回实验，会引入正常商品误报和跨标签误报。
- 当前如果把 sentence-transformers evidence 合并进最终 audit case，建议先使用 `--override-min-score 0.65`。
- 不建议用当前小模型直接替代规则证据；下一步应比较 BGE/multilingual-e5 或改成“语义召回候选、规则/证据确认”的两阶段流程。

两阶段语义确认已实现：

```text
script: scripts/confirm_semantic_retrieval.py
input semantic results: outputs/retrieval_results/v0_3_sentence_transformers_text_retrieval.csv
confirmation evidence:
  outputs/evidence/v0_3_rule_evidence.jsonl
  outputs/evidence/v0_3_duplicate_evidence.jsonl
  outputs/evidence/v0_3_image_similarity_evidence.jsonl
candidate min_score: 0.25
semantic retrieval rows: 90
candidates kept: 90
confirmed candidates: 62
confirmed semantic evidence: 62
```

新增输出：

- `outputs/evidence/v0_3_sentence_transformers_confirmed_evidence.jsonl`
- `outputs/retrieval_results/v0_3_sentence_transformers_confirmed_candidates.csv`
- `outputs/evidence/v0_3_audit_cases_semantic_confirmed_full.jsonl`
- `outputs/evidence/v0_3_audit_cases_semantic_confirmed_full.csv`
- `outputs/metrics/v0_3_semantic_confirmed_full_evaluation_summary.json`
- `outputs/metrics/v0_3_semantic_confirmed_full_label_metrics.csv`
- `outputs/metrics/v0_3_semantic_confirmed_full_error_analysis.jsonl`
- `outputs/metrics/v0_3_semantic_confirmed_full_error_analysis.csv`

两阶段确认聚合后：

```text
Evidence records loaded: 219
Audit cases written: 120
binary precision: 1.0
binary recall: 1.0
macro f1: 1.0
micro f1: 1.0
errors found: 0
```

解释：低阈值 semantic candidates 可以保留在 CSV 中供分析；只有被规则/重复图/图片相似等同风险证据确认的候选进入最终 audit evidence。

CLI 语义候选展示已接入：

```text
script: scripts/query_cli.py
new args:
  --semantic-candidates
  --show-unconfirmed-semantic
  --semantic-limit
```

已验证命令：

```bash
.venv/bin/python scripts/query_cli.py \
  --query "查一下加微信私聊的商品" \
  --items data/seeds/v0_3_semireal_items.csv \
  --cases outputs/evidence/v0_3_audit_cases_semantic_confirmed_full.jsonl \
  --semantic-candidates outputs/retrieval_results/v0_3_sentence_transformers_confirmed_candidates.csv \
  --only-risk

.venv/bin/python scripts/query_cli.py \
  --query "找疑似电子烟商品" \
  --items data/seeds/v0_3_semireal_items.csv \
  --cases outputs/evidence/v0_3_audit_cases_semantic_confirmed_full.jsonl \
  --semantic-candidates outputs/retrieval_results/v0_3_sentence_transformers_confirmed_candidates.csv \
  --only-risk \
  --show-unconfirmed-semantic
```

CLI 当前行为：

- 命中的商品如果存在语义候选记录，会显示 `semantic: confirmed/candidate score=... rank=... sources=...`。
- 底部会展示 semantic candidates section。
- 默认只展示 confirmed semantic candidates；加 `--show-unconfirmed-semantic` 后也展示未确认候选。
- 普通问题 `今天天气怎么样` 仍返回 no retrieval。
- 未传 `--semantic-candidates` 时，旧 CLI 行为保持不变。

## LLM Intent Router

当前意图识别已经从单一 `route_query()` 扩展为可替换 router 接口：

```text
TemplateIntentRouter
OpenAILlmIntentRouter
HybridIntentRouter
```

新增文件：

- `configs/intent_router.yaml`
- `src/agents/intent_router.py`
- `data/eval/intent_router_v0_1.csv`
- `scripts/evaluate_intent_router.py`
- `docs/LLM_INTENT_ROUTER.md`
- `.env.example`

CLI 新增参数：

```text
--router template|llm|hybrid
--intent-config configs/intent_router.yaml
--env-file .env
```

设计：

- LLM 只负责意图识别/路由，不直接判断商品是否违规。
- 输出仍然转换为现有 `RouteDecision`，所以后续检索、证据确认和 CLI 展示不用重写。
- `hybrid` 优先调用 LLM，失败时回退到 template router。
- API key 只从 `OPENAI_API_KEY` 或本地 `.env` 读取，不写入代码。
- 当前默认模型配置为 `gpt-5-nano`，后续可在配置里替换为账号可用的小模型或 OpenAI-compatible Qwen endpoint。

本地验证：

```bash
python3 -m py_compile src/agents/intent_router.py scripts/query_cli.py scripts/evaluate_intent_router.py
python3 scripts/query_cli.py --query "今天天气怎么样" --router template
python3 scripts/query_cli.py --query "找疑似电子烟商品" --router hybrid --only-risk
```

当前 shell 未检测到 `OPENAI_API_KEY`：

```text
OPENAI_API_KEY=missing
```

因此 hybrid eval 当前走 template fallback：

```text
rows: 30
need_accuracy: 1.0
risk_accuracy: 0.766667
retrieval_type_accuracy: 0.866667
strategy_accuracy: 1.0
top_k_accuracy: 1.0
exact_match_accuracy: 0.766667
```

主要 template 漏点：

- `image_duplicate` 图搜/盗图意图会误路由到 `prohibited_goods`。
- “假货 + 私聊交易”这类多风险表达会误路由。
- “站外交易/仿牌”等短表达在 template TF-IDF 下仍不够稳。

下一步：把 `OPENAI_API_KEY` 写入 `.env` 或 export 到 shell 后，运行：

```bash
python3 scripts/evaluate_intent_router.py --router llm
python3 scripts/evaluate_intent_router.py --router hybrid
```

目标是对比 template vs LLM vs hybrid 的 router accuracy，并确认 LLM 是否修复 image_duplicate 和多风险 query。

LLM router prompt calibration 已完成：

```text
router: llm
rows: 30
need_accuracy: 1.0
risk_accuracy: 1.0
retrieval_type_accuracy: 1.0
strategy_accuracy: 1.0
top_k_accuracy: 1.0
exact_match_accuracy: 1.0

router: hybrid
rows: 30
need_accuracy: 1.0
risk_accuracy: 1.0
retrieval_type_accuracy: 1.0
strategy_accuracy: 1.0
top_k_accuracy: 1.0
exact_match_accuracy: 1.0
```

本轮调整：

- `configs/intent_router.yaml` 中强化审核检索默认使用 `topk_threshold`。
- 增加 `相似图片/同图/盗图/重复铺货` -> `image_duplicate + image_to_item` 的规则说明。
- 增加 `图片里的联系方式/OCR联系方式` -> `off_platform_contact + text_to_item` 的规则说明。
- 增加 `美容/护肤/功效/美白/排毒/见效` -> `misleading_claim` 的规则说明。
- 补充 few-shot examples，修复上一轮 LLM eval 中的 strategy drift 和个别风险误分类。

CLI smoke tests：

```text
给我五个相似图片商品
  Route: duplicate_image / image_to_item / topk_threshold / image_duplicate / top_k=5

查一下联系方式在图片里的商品
  Route: text_policy_violation / text_to_item / topk_threshold / off_platform_contact
```

`image_to_item` CLI route 已接入图片查询流程：

- `src/agents/router.py` 的 template router 已能把 `相似图片/同图/盗图/重复铺货/这张图` 等表达路由到 `duplicate_image + image_to_item`。
- `scripts/query_cli.py --query "给我五个相似图片商品" --query-image data/samples/dup_earbuds_main.jpg --exclude-item sku_000046 --only-risk` 会调用 `ImageItemRetriever` 并返回同图/相似图商品。
- `scripts/query_cli.py` 已支持 `--query-item-id` 和 `--query-item-image-index`，可以直接使用库内商品图片做图搜图；如果未显式传 `--exclude-item`，会自动排除 query item 自身。
- `scripts/query_cli.py` 已支持 `--emit-evidence`，可把展示出的 image hits 写成 JSONL evidence；库内 item 查询时 evidence 挂到 query item，外部图片查询时 evidence 挂到命中的 item。
- `scripts/query_cli.py` 已支持 `--emit-cases` 和 `--emit-cases-summary`，可在同一次 CLI 图片查询中直接生成临时 audit cases JSONL/CSV；`--emit-cases` 需要同时传 `--emit-evidence`。
- 如果 route 需要图片但未传 `--query-image`，CLI 会提示提供参考图片路径，不再静默回退到文本检索。
- `查一下联系方式在图片里的商品` 仍保持 `off_platform_contact + text_to_item`，用于 OCR/text evidence 查询。
- 新增 `scripts/smoke_query_cli_routes.py`，用于固定 CLI 关键 route 行为。

本轮 smoke tests：

```text
python3 -m py_compile src/agents/router.py scripts/query_cli.py
python3 -m py_compile scripts/smoke_query_cli_routes.py
python3 scripts/smoke_query_cli_routes.py --router template
  All 5 route smoke checks passed.
python3 scripts/query_cli.py --query "给我五个相似图片商品" --router template --query-image data/samples/dup_earbuds_main.jpg --exclude-item sku_000046 --only-risk
  Route: duplicate_image / image_to_item / topk_threshold / image_duplicate
  Results: 2 kept / 5 considered
python3 scripts/query_cli.py --query "给我五个相似图片商品" --router template --query-item-id sku_000046 --only-risk
  Route: duplicate_image / image_to_item / topk_threshold / image_duplicate
  Results: 2 kept / 5 considered
python3 scripts/query_cli.py --query "给我五个相似图片商品" --router template --query-item-id sku_000046 --only-risk --emit-evidence /tmp/cli_image_query_evidence.jsonl
  Evidence output: /tmp/cli_image_query_evidence.jsonl  records=2
python3 scripts/build_evidence.py --items data/items.csv --evidence /tmp/cli_image_query_evidence.jsonl --output /tmp/cli_image_query_cases.jsonl --summary /tmp/cli_image_query_cases.csv
  Evidence records loaded: 2
  Audit cases written: 1
python3 scripts/query_cli.py --query "给我五个相似图片商品" --router template --query-item-id sku_000046 --only-risk --emit-evidence /tmp/cli_image_query_evidence.jsonl --emit-cases /tmp/cli_image_query_cases.jsonl --emit-cases-summary /tmp/cli_image_query_cases.csv
  Evidence output: /tmp/cli_image_query_evidence.jsonl  records=2
  Cases output: /tmp/cli_image_query_cases.jsonl  cases=1
  Cases summary output: /tmp/cli_image_query_cases.csv
python3 scripts/query_cli.py --query "给我五个相似图片商品" --router template --query-item-id sku_000046 --only-risk --emit-cases /tmp/should_require_evidence.jsonl
  ERROR: --emit-cases requires --emit-evidence. / exit code 2
python3 scripts/query_cli.py --query "给我五个相似图片商品" --router template --only-risk
  提示需要 --query-image
python3 scripts/query_cli.py --query "查一下联系方式在图片里的商品" --router template --only-risk
  Route: text_policy_violation / text_to_item / topk_threshold / off_platform_contact
```

v0.3 embedding high precision mode (`--override-min-score 0.4`)：

```text
retrieval evidence: 26
macro precision@kept: 1.0
macro recall@kept: 0.248148
top1 accuracy: 1.0
```

Sweep 观察：

```text
best F1: top_k=10 min_score=0.08 precision=0.767901 recall=0.503704 f1=0.608357
best recall @ macro precision>=0.9: top_k=10 min_score=0.4 precision=1.0 recall=0.248148
```

解释：

- LSI dense retrieval 比保守 TF-IDF evidence 模式召回更高，但低阈值会引入误报。
- 当前建议把 embedding high precision 证据作为 audit case 附加证据，而不是替代规则证据。
- `outputs/evidence/v0_3_audit_cases_embedding_full.jsonl` 已聚合 rule + duplicate + TF-IDF retrieval + high-precision embedding retrieval + image similarity，评估仍为 Errors found: 0。
- 下一阶段如果要真正提升语义召回，应接入 `sentence-transformers` / BGE / CLIP text encoder / remote embedding service。

本轮 v0.1 校准已修复：

- `sku_000034` 桌游战术卡牌套装：`战术` 被误报为 `prohibited_goods`。
- `sku_000035` 厨房开箱工具收纳盒：`开箱工具` 被误报为 `prohibited_goods`。
- `sku_000055` 售后客服联系卡：`不引导站外交易` 中的 `站外` 被误报为 `off_platform_contact`。
- `sku_000057` 桌游战术地图扩展包：`战术` 被误报为 `prohibited_goods`。
- `sku_000036` 茶具礼盒：`加V详聊` 漏报 `off_platform_contact`。
- `sku_000037` 潮流背包：`薇信同号` 漏报 `off_platform_contact`。
- `sku_000105`、`sku_000107`、`sku_000110`：SimpleImageEncoder 在合成图上误报 `image_duplicate`。
- `configs/rules.yaml` 中 `1:1` 未加引号时会被 YAML 解析为数字 `61`，导致 v0.2 批次号如 `V0.2-061` 被误判为 `counterfeit_brand`；已改为 `"1:1"`，v0.1 回归仍保持 Errors found: 0。

注意：当前 1.0 只代表 synthetic v0.1 回归集，不代表真实线上效果。

## Text Retrieval MVP

当前文本检索不是最终模型，而是轻量 baseline：

- 使用 `TfidfVectorizer` 做 char n-gram 检索。
- 检索字段来自商品标题、描述、店铺、类目、品牌等 metadata。
- `configs/retrieval_queries.yaml` 维护 query 模板、风险类型、`top_k`、`min_score`。
- `src/retrieval/filters.py` 复用 `configs/rules.yaml` 中的排除词，过滤明显白名单命中。

当前作用：

- 先让“自然语言查询 -> 商品召回 -> evidence -> audit case”跑通。
- 让后续替换 CLIP / Chinese CLIP / embedding service 时，只替换 retrieval 层，不推翻整体系统。
- 数据扩到 120 条后，已从 `top_k=5/min_score≈0.055` 调整为 `top_k=10/min_score=0.05`。
- 当前文本检索 macro recall@kept 为 `0.285434`，仍然不高，后续需要 embedding 检索增强。
- `scripts/sweep_text_retrieval.py` 显示更激进的 `top_k=20/min_score=0.03` 可以提升 recall，但当前为了避免 retrieval evidence 误伤正常商品，采用保守配置。

已验证查询：

- `找疑似电子烟商品`
- `查一下加微信私聊的商品`
- `查前10个疑似高仿商品`
- `今天天气怎么样`

当前行为：

- 电子烟查询路由到 `prohibited_goods`。
- 加微信/私聊查询路由到 `off_platform_contact`。
- 高仿查询路由到 `counterfeit_brand`。
- 天气类普通问题返回 `No retrieval needed`，不会乱触发商品检索。

## Query CLI MVP

当前 CLI：

```bash
python3 scripts/query_cli.py --query "找疑似电子烟商品" --only-risk
```

能力：

- 根据自然语言 query 做轻量路由。
- 推断 `audit_task`、`retrieval_type`、`strategy`、`risk_type`、`top_k`、`min_score`。
- 对短 query 拼接命中的 query template 做检索扩展。
- 支持 `--only-risk`，只展示当前风险类型相关商品。
- 展示商品命中分数、风险标签、已有 audit case、证据摘要。
- 对非审核检索问题返回 no retrieval。

当前位置：CLI 已经足够用于 MVP demo，但还不是完整 Agent。

后续可增强：

- 让 CLI 支持多轮追问。
- 支持按证据类型过滤。
- 支持导出某次查询的 case report。
- 接入 LLM 生成自然语言审核摘要。

## Image Retrieval MVP

当前图像侧已经跑通 image-to-item 检索和 image similarity evidence。

本地环境检查结论：

- 可用：`PIL`、`numpy`、`sklearn`、`transformers`
- 不可用：`torch`、`open_clip`、`clip`

因此当前没有直接跑 CLIP，而是实现了一个可替换的本地 baseline：

- `src/models/image_encoder.py`：`SimpleImageEncoder`
- `src/retrieval/image_search.py`：`ImageItemRetriever`
- `scripts/query_image.py`：单图查询 CLI
- `scripts/run_image_similarity.py`：批量生成图片相似证据
- `scripts/evaluate_image_similarity.py`：评估图片相似检索的重复图召回和误报

Image similarity metrics 已经接入，当前用共享 `image_paths` 推出重复图真值组，评估 item-level duplicate retrieval。
多图商品设计见 `docs/IMAGE_MANIFEST_AND_EMBEDDINGS.md`。当前 image hit / evidence 已保留 `image_id`、`image_role`、`image_path`，后续可直接接 embedding cache。
`scripts/query_image.py` 的输出也会展示命中的 `image_id` 和 `image_role`。

`SimpleImageEncoder` 使用：

- 颜色直方图
- 通道统计
- 灰度 sketch
- 低分辨率 thumbnail 特征

它只适合当前 synthetic sample 的 exact/near-exact duplicate 场景，不代表最终图片检索效果。

已验证：

```bash
python3 scripts/query_image.py --query-image data/samples/dup_earbuds_main.jpg --exclude-item sku_000046 --only-risk
```

能够找回同图商品：

- `sku_000047`
- `sku_000048`

当前默认图像相似度阈值：

```text
min_score = 0.996
```

这个阈值由 `scripts/sweep_image_similarity.py` 在当前 v0.1 合成图上校准，只适用于当前 synthetic image baseline。换成 CLIP / SigLIP / Chinese CLIP 后必须重新校准。

## Evidence Builder

Evidence Builder 已经接入多源证据：

- 规则证据
- duplicate 证据
- 文本检索证据
- 图片相似证据

聚合后的 `audit_cases.jsonl` 是当前 CLI 和评估脚本的核心数据源。

图片相似证据主要增强 `image_duplicate` 商品的证据链，例如：

- `sku_000046`
- `sku_000047`
- `sku_000048`

这些商品的 `evidence_count` 已经因为 image similarity evidence 增加。

## Design Decisions

当前明确采用的设计决策：

- 先做 MVP 广度优先，不继续按单模块深挖。
- 规则作为可解释 baseline，不作为最终智能能力的全部。
- 文本检索先用 TF-IDF 跑通接口，后面替换 embedding / CLIP。
- 图片检索先用本地 simple encoder 跑通接口，后面替换云端视觉模型。
- 数据集先用小规模 synthetic + 本地样例图，不下载 ImageNet。
- 不把大图片、大模型权重、embedding 缓存提交进 Git。
- 所有中间结果都落到 `outputs/`，方便回归和对比。

关于数据集：

- ImageNet 不适合作为主数据集，因为它是通用图像分类数据，不包含电商商品标题、描述、店铺、违规标签和审核证据链。
- 后续更适合构建小规模电商审核数据集，包括商品 metadata、图片、风险标签、证据字段。
- 可以用公开电商商品数据、人工构造样本、少量真实截图/商品图、规则合成样本组合起步。
- 大图和模型训练不适合全放本地，可以放云存储或云 GPU 环境处理。

关于本地 Mac M4：

- 本地适合做数据清洗、规则、pipeline、CLI、轻量检索、单元测试。
- 本地不适合做大规模 CLIP 微调或大 batch embedding。
- 后续可以用 VS Code Remote SSH 连接云 GPU，或者使用云 Notebook/Colab/AutoDL 等环境生成 embedding。
- 项目代码结构应保持“本地可跑小样本，云端可跑大模型”。

## Known Limitations

当前限制：

- 所有数据还是 synthetic，小样本指标偏乐观。
- 文本检索使用 TF-IDF，不具备真正语义理解能力。
- 图片检索使用 SimpleImageEncoder，只能验证接口和近重复图场景。
- 规则在当前 v0.1 回归集上已清零错误，但这是对 synthetic hard negatives 的校准，不代表真实数据也会稳定。
- OCR 已接入并在 v0.4 上跑通 Tesseract，但当前效果仍受合成图字体、叠字位置和规则词表覆盖影响。
- 没有真正的多轮 Agent，只是轻量 router + CLI。
- 没有接入真实电商图片、真实违规策略、真实人工审核反馈。
- 没有云端 embedding 缓存和向量库。
- 当前 v0.1 数据集已开始暴露规则和阈值问题，但还不是可用于严肃模型结论的真实评测集。

当前不能把指标解释成“真实线上准确率”，只能解释成“当前 MVP 回归样本上的 pipeline 指标”。

## Next Steps

推荐下一步仍然按 MVP 广度优先推进。

当前最推荐的下一步：基于 `docs/EXPERIMENT_SUMMARY.md` 写最终报告，把项目包装成“端到端合成数据闭环 + 可解释审核证据链 + SigLIP 图搜 / 轻量微调对比”的完整交付。

优先级 1：补齐多模态检索主线

- v0.4 CLIP / SigLIP image embedding 轻量微调已完成；SigLIP + Linear Probe 当前最强。
- v0.5 near-duplicate / hard-negative 第一版已生成；SimpleImageEncoder、CLIP ViT-B/32、Chinese-CLIP 和 SigLIP 均已完成对比，SigLIP 当前最强。
- `docs/EXPERIMENT_SUMMARY.md` 已整理核心指标；后续可以补一个自动从 metrics JSON 生成 summary table 的脚本。
- 下一阶段重点转为最终报告、demo 叙事和可复现实验命令整理。

优先级 2：增强 Agent 查询体验

- CLI 支持一次查询导出 case report。
- 增加 query history 或 session 概念。
- 支持“为什么这个商品被判违规”的证据解释输出。
- 支持按风险类型、证据类型、分数阈值筛选。

优先级 3：接入真实模型或云算力

- 在云 GPU 环境中安装 PyTorch + CLIP/SigLIP/Chinese CLIP。
- 对商品图片离线生成 image embedding。
- 对商品文本生成 text embedding。
- 用向量检索替换当前 TF-IDF/simple image encoder。
- 重新校准阈值、TopK 和评估指标。

优先级 4：回到规则优化

- 等新增真实样本后，再做下一轮规则误报/漏报分析。
- 增加更细的站外导流、夸大宣传和仿牌策略。
- 为真实样本暴露的新问题补充 regression cases。

## Resume Guide

如果下次打开项目不知道从哪里开始：

1. 读 `PROJECT_FLOW.md`，恢复项目整体设计。
2. 读 `STATUS.md`，恢复当前进度和下一步。
3. 运行完整 pipeline，确认当前环境还能复现。
4. 查看 `outputs/metrics/error_analysis.csv`，确认当前已知错误是否变化。
5. 从 `Next Steps` 的优先级 1 继续做。

最推荐的下一步具体任务：

```text
基于 docs/EXPERIMENT_SUMMARY.md 写最终报告。
```

原因：

- v0.4 500 条平台风格数据已经完成规则/OCR/文本/图片 baseline，CLIP 图搜也已跑通。
- 当前 v0.4 的 image_duplicate 基本是 exact duplicate，SimpleImageEncoder 和 CLIP 都能轻松达到满分。
- v0.5 已经让 SimpleImageEncoder 在无误报阈值下近重复召回降到 0.333333；SigLIP 在 hard_fp=0 时 recall 达到 0.916667，已经体现出更强视觉 embedding 优势。
- 真实数据不再作为当前目标；CLIP/SigLIP/Chinese-CLIP 图搜对比、轻量微调和核心指标汇总均已完成，下一步应把结果沉淀成最终交付文档。

## Maintenance Notes

每完成一个里程碑，都要更新本文档：

- 新增了什么模块。
- 新增了什么命令。
- 最新指标是多少。
- 有哪些已知问题。
- 下一步从哪里继续。

这样即使上下文窗口压缩，也不会丢掉项目脉络。
