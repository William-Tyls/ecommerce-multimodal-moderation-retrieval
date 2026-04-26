# E-Commerce Moderation Multimodal Retrieval

面向电商违规内容审核的多模态商品图文检索 Agent 项目。

本项目目标是构建一套支持自然语言问答式交互的审核检索系统，帮助审核员定位疑似违规商品、查找盗图/重复铺货、发现违禁词和导流文案，并生成可解释证据链。

## Current Stage

当前阶段已经进入 MVP 广度优先阶段，先用轻量 baseline 跑通审核检索、证据链和评估闭环：

- 风险标签配置：`configs/risk_labels.yaml`
- 规则词表配置：`configs/rules.yaml`
- 商品数据模板：`data/items.csv`
- 数据校验脚本：`scripts/validate_items.py`
- 样本扩充脚本：`scripts/expand_sample_items.py`
- 文本检索入口：`scripts/run_text_retrieval.py`
- 文本检索扫描入口：`scripts/sweep_text_retrieval.py`
- v0.2 数据集生成入口：`scripts/expand_sample_items_v0_2.py`
- 图片相似检索入口：`scripts/run_image_similarity.py`
- 图片相似评估入口：`scripts/evaluate_image_similarity.py`
- 图片阈值扫描入口：`scripts/sweep_image_similarity.py`
- 图片 manifest 入口：`scripts/build_image_manifest.py`
- OCR 入口：`scripts/run_ocr.py`
- OCR 规则证据入口：`scripts/run_ocr_rules.py`
- CLIP/SigLIP 图片 embedding smoke：`scripts/smoke_clip_image_encoder.py`
- CLIP/SigLIP 图片 embedding cache：`scripts/compute_clip_image_embeddings.py`
- CLIP/SigLIP 图片检索：`scripts/run_clip_image_retrieval.py`
- 查询 CLI：`scripts/query_cli.py`
- 项目整体流程：`PROJECT_FLOW.md`
- 当前进度记录：`STATUS.md`
- v0.2 数据集说明：`docs/DATASET_V0_2.md`
- 人工 seed 说明：`docs/CURATED_SEEDS.md`
- embedding 文本检索说明：`docs/EMBEDDING_TEXT_RETRIEVAL.md`
- 云端 GPU 环境说明：`docs/CLOUD_SETUP.md`
- LLM 意图识别说明：`docs/LLM_INTENT_ROUTER.md`
- OCR pipeline 说明：`docs/OCR_PIPELINE.md`
- v0.4 真实平台爬取数据方案：`docs/DATASET_V0_4_CRAWLED.md`

## Quick Check

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
python3 scripts/run_ocr.py --items data/items.csv --backend auto --output outputs/ocr/item_ocr.jsonl
python3 scripts/run_ocr_rules.py --ocr outputs/ocr/item_ocr.jsonl --output outputs/evidence/ocr_rule_evidence.jsonl --summary outputs/evidence/ocr_rule_summary.csv
.venv/bin/python scripts/run_ocr.py --items data/items.csv --backend tesseract --languages eng+chi_sim --output outputs/ocr/item_ocr_tesseract.jsonl
.venv/bin/python scripts/run_ocr_rules.py --ocr outputs/ocr/item_ocr_tesseract.jsonl --output outputs/evidence/ocr_rule_evidence_tesseract.jsonl --summary outputs/evidence/ocr_rule_summary_tesseract.csv
python3 scripts/build_evidence.py --items data/items.csv --evidence outputs/evidence/rule_evidence.jsonl --evidence outputs/evidence/duplicate_evidence.jsonl --evidence outputs/evidence/retrieval_evidence.jsonl --evidence outputs/evidence/image_similarity_evidence.jsonl --include-clean
python3 scripts/build_evidence.py --items data/items.csv --evidence outputs/evidence/rule_evidence.jsonl --evidence outputs/evidence/duplicate_evidence.jsonl --evidence outputs/evidence/retrieval_evidence.jsonl --evidence outputs/evidence/image_similarity_evidence.jsonl --evidence outputs/evidence/ocr_rule_evidence.jsonl --output outputs/evidence/audit_cases_with_ocr.jsonl --summary outputs/evidence/audit_cases_with_ocr.csv --include-clean
python3 scripts/build_evidence.py --items data/items.csv --evidence outputs/evidence/rule_evidence.jsonl --evidence outputs/evidence/duplicate_evidence.jsonl --evidence outputs/evidence/retrieval_evidence.jsonl --evidence outputs/evidence/image_similarity_evidence.jsonl --evidence outputs/evidence/ocr_rule_evidence_tesseract.jsonl --output outputs/evidence/audit_cases_with_tesseract_ocr.jsonl --summary outputs/evidence/audit_cases_with_tesseract_ocr.csv --include-clean
python3 scripts/evaluate_cases.py --items data/items.csv --cases outputs/evidence/audit_cases.jsonl --risk-labels configs/risk_labels.yaml
python3 scripts/analyze_errors.py --items data/items.csv --cases outputs/evidence/audit_cases.jsonl
python3 scripts/query_cli.py --query "找疑似电子烟商品"
python3 scripts/query_cli.py --query "查一下加微信私聊的商品" --only-risk
python3 scripts/query_cli.py --query "今天天气怎么样"
python3 scripts/query_cli.py --query "给我五个相似图片商品" --query-image data/samples/dup_earbuds_main.jpg --exclude-item sku_000046 --only-risk
python3 scripts/query_cli.py --query "给我五个相似图片商品" --query-item-id sku_000046 --only-risk
python3 scripts/query_cli.py --query "给我五个相似图片商品" --query-item-id sku_000046 --only-risk --emit-evidence outputs/evidence/cli_image_query_evidence.jsonl --emit-cases outputs/evidence/cli_image_query_cases.jsonl --emit-cases-summary outputs/evidence/cli_image_query_cases.csv
python3 scripts/query_image.py --query-image data/samples/dup_earbuds_main.jpg --exclude-item sku_000046 --only-risk
python3 scripts/smoke_query_cli_routes.py --router template
```

## Cloud CLIP Smoke

云端 GPU 环境准备见 `docs/CLOUD_SETUP.md`。第一条 CLIP/SigLIP smoke 命令：

```bash
python scripts/check_gpu_env.py
python scripts/smoke_clip_image_encoder.py \
  --items data/items.csv \
  --model-name openai/clip-vit-base-patch32 \
  --device auto \
  --limit 6
python scripts/compute_clip_image_embeddings.py \
  --manifest data/image_manifest.csv \
  --model-name openai/clip-vit-base-patch32 \
  --device auto \
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

## Dataset v0.4 Crawled Platform Items

v0.4 的目标是采集小规模真实电商平台商品营销图、标题和详情文案，用来替代当前生成图/占位图对 CLIP、OCR 和 image-to-item 检索造成的分布偏差。方案说明见 `docs/DATASET_V0_4_CRAWLED.md`。

最小采集骨架：

```bash
python3 scripts/crawl_v0_4_items.py \
  --input-urls data/seeds/v0_4_urls.txt \
  --output data/seeds/v0_4_crawled_items.csv \
  --image-dir data/crawled/v0_4/images \
  --limit 20 \
  --delay 2.0 \
  --download-images
```

生成 manifest 和校验：

```bash
python3 scripts/validate_items.py --items data/seeds/v0_4_crawled_items.csv --risk-labels configs/risk_labels.yaml
python3 scripts/build_image_manifest.py --items data/seeds/v0_4_crawled_items.csv --output data/image_manifest_v0_4.csv
```

## Synthetic Platform Dataset

当前为了先跑通完整流程，可以用 API 生成平台风格合成数据。数据计划见 `docs/DATASET_PLAN.md`，配置见 `configs/synthetic_v0_4_generation.yaml`。

生成策略是两段式：图片模型只负责生成干净商品底图，脚本再统一叠加平台主图 UI 和清晰 OCR 风险文字，避免生图模型直接生成中文、伪文字或奇怪图标。

先生成 metadata 和 prompt plan，不调用 API：

```bash
python3 scripts/build_synthetic_platform_dataset.py \
  --config configs/synthetic_v0_4_generation.yaml \
  --plan-only
```

确认后先小批量 smoke，确认图片风格和字段都正常：

```bash
python3 scripts/build_synthetic_platform_dataset.py \
  --config configs/synthetic_v0_4_generation.yaml \
  --generate-images \
  --limit 5
```

再生成全量图片：

```bash
python3 scripts/build_synthetic_platform_dataset.py \
  --config configs/synthetic_v0_4_generation.yaml \
  --generate-images
```

如果已经有图片，只想给现有图片重新叠加 OCR 文字，不调用 API：

```bash
python3 scripts/build_synthetic_platform_dataset.py \
  --config configs/synthetic_v0_4_generation.yaml \
  --apply-overlays-only \
  --limit 5
```

## Cloud GPU Preparation

当前不需要立刻租云 GPU。后续接入 CLIP/SigLIP/OCR/VLM 或更大规模 embedding 时，可按 `docs/CLOUD_SETUP.md` 准备云端环境。

```bash
pip install -r requirements-cloud.txt
python3 scripts/check_gpu_env.py
```

## Text Embedding Backend

`scripts/run_embedding_text_retrieval.py` 默认使用 `--backend auto`：有 `sentence-transformers` 时优先使用真实语义模型，否则回退到本地 LSI baseline。

```bash
python3 scripts/run_embedding_text_retrieval.py \
  --backend lsi_tfidf_svd \
  --items data/seeds/v0_3_semireal_items.csv
```

本地已验证的真实语义 backend：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install sentence-transformers
.venv/bin/python scripts/run_embedding_text_retrieval.py \
  --backend sentence_transformers \
  --model-name sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
  --items data/seeds/v0_3_semireal_items.csv
```

语义候选进入审核证据前，建议先做同风险证据确认：

```bash
.venv/bin/python scripts/confirm_semantic_retrieval.py \
  --items data/seeds/v0_3_semireal_items.csv \
  --results outputs/retrieval_results/v0_3_sentence_transformers_text_retrieval.csv \
  --confirmation-evidence outputs/evidence/v0_3_rule_evidence.jsonl \
  --confirmation-evidence outputs/evidence/v0_3_duplicate_evidence.jsonl \
  --confirmation-evidence outputs/evidence/v0_3_image_similarity_evidence.jsonl
```

CLI 可以展示语义候选和已确认语义证据：

```bash
.venv/bin/python scripts/query_cli.py \
  --query "找疑似电子烟商品" \
  --items data/seeds/v0_3_semireal_items.csv \
  --cases outputs/evidence/v0_3_audit_cases_semantic_confirmed_full.jsonl \
  --semantic-candidates outputs/retrieval_results/v0_3_sentence_transformers_confirmed_candidates.csv \
  --only-risk \
  --show-unconfirmed-semantic
```

## LLM Intent Router

当前 CLI 支持 template / LLM / hybrid 三种意图识别入口：

```bash
python3 scripts/query_cli.py --query "查一下加微信私聊的商品" --router template
python3 scripts/query_cli.py --query "查一下加微信私聊的商品" --router hybrid
```

LLM router 从 `configs/intent_router.yaml` 读取模型和 schema 配置，API key 从 `OPENAI_API_KEY` 或本地 `.env` 读取。
可参考 `.env.example` 创建本地 `.env`。

```bash
python3 scripts/evaluate_intent_router.py --router template
python3 scripts/evaluate_intent_router.py --router hybrid
```

## Dataset v0.2 Candidate

当前 v0.1 主数据文件仍是 `data/items.csv`。如果要生成 v0.2 候选数据集：

```bash
python3 scripts/expand_sample_items_v0_2.py --base data/items.csv --output data/items_v0_2.csv
python3 scripts/validate_items.py --items data/items_v0_2.csv --risk-labels configs/risk_labels.yaml
python3 scripts/generate_sample_images.py --items data/items_v0_2.csv
python3 scripts/build_image_manifest.py --items data/items_v0_2.csv --output data/image_manifest_v0_2.csv
```

如果要追加人工维护的高质量 seed：

```bash
python3 scripts/expand_sample_items_v0_2.py \
  --base data/items.csv \
  --output data/items_v0_2.csv \
  --curated-seeds data/seeds/v0_2_curated_items.csv
```

当前 v0.2 加入了 `data/seeds/v0_2_curated_items.csv` 中的人工 seed 后共 536 条。v0.2 用于下一阶段数据扩展、规则校准和模型接入准备；在确认质量前，不直接替换 v0.1 回归集。

## Data Principle

大文件不提交到 Git，包括：

- 原始图片
- 商品图片集
- 模型权重
- embedding 缓存
- 大型实验输出

Git 中只保留代码、配置、metadata、规则和小规模样例。
