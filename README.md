# E-Commerce Multimodal Moderation Retrieval

An explainable multimodal retrieval system for e-commerce content moderation.

The system helps reviewers find suspicious product listings from text, OCR, and product images, then aggregates the matched evidence into item-level moderation cases.

## What It Does

This repository keeps the final system architecture only. It does not include experimental datasets, generated images, model checkpoints, embedding caches, or evaluation artifacts.

Core capabilities:

- Rule-based detection for prohibited goods, counterfeit risk, off-platform contact, misleading claims, and duplicate-image risk.
- OCR extraction over product images, followed by moderation rules on detected text.
- Image embedding generation with CLIP-compatible Hugging Face vision models, with SigLIP as the recommended backbone.
- Image-to-item retrieval from cached image embeddings.
- Evidence aggregation into item-level audit cases.
- A CLI for natural-language moderation queries and image-based lookup.

## Final Architecture

```text
Product metadata + product images
  -> validate item schema
  -> build image manifest
  -> run text rules
  -> run OCR and OCR rules
  -> compute image embeddings with SigLIP
  -> retrieve visually similar items
  -> aggregate evidence
  -> query or export moderation cases
```

For image retrieval, the recommended final configuration is:

```text
Image backbone: google/siglip-base-patch16-224
Retrieval mode: image-to-item nearest-neighbor search over cached embeddings
Evidence threshold: tune per dataset; start from a conservative threshold for moderation review
```

The system is not a generative RAG chatbot. It is a retrieval and evidence-building pipeline. A language model can be added later to summarize evidence, but the moderation decision surface should stay grounded in structured evidence records.

## Repository Structure

```text
configs/
  intent_router.yaml          # query intent routing config
  retrieval_queries.yaml      # query templates and route defaults
  risk_labels.yaml            # moderation labels and actions
  rules.yaml                  # text/OCR moderation rules

src/
  agents/                     # intent routing
  evidence/                   # item-level case builder
  ocr/                        # OCR backend abstraction
  retrieval/                  # text/image retrieval utilities
  rules/                      # rule matching engine

scripts/
  validate_items.py           # validate product metadata
  build_image_manifest.py     # convert item metadata into image-level manifest
  run_rules.py                # run text rules
  run_ocr.py                  # OCR product images
  run_ocr_rules.py            # run rules over OCR output
  compute_clip_image_embeddings.py
  run_clip_image_retrieval.py
  build_evidence.py
  query_cli.py
  check_gpu_env.py

docs/
  CLOUD_SETUP.md
  IMAGE_MANIFEST_AND_EMBEDDINGS.md
  OCR_PIPELINE.md
```

## Data Format

The repository does not ship with product data. Prepare your own `data/items.csv` with the following columns:

```csv
item_id,title,description,category,shop_id,image_paths,ocr_text,risk_labels,risk_objects,source,split
sku_000001,Example product title,Example product description,electronics,shop_001,data/images/sku_000001/main.jpg,,normal,,internal,test
```

Column notes:

- `item_id`: unique product ID.
- `title`: product title.
- `description`: product detail text.
- `category`: product category.
- `shop_id`: seller or shop identifier.
- `image_paths`: one or more image paths separated by `|`.
- `ocr_text`: optional precomputed OCR text, also separated by `|`.
- `risk_labels`: optional labels separated by `|`.
- `risk_objects`: optional visual or policy objects separated by `|`.
- `source`: data source name.
- `split`: optional dataset split such as `train`, `val`, or `test`.

Supported risk labels are configured in `configs/risk_labels.yaml`:

```text
prohibited_goods
counterfeit_brand
image_duplicate
off_platform_contact
misleading_claim
normal
```

## Installation

Create a Python environment and install the runtime dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements-cloud.txt
```

Check the local or cloud GPU environment:

```bash
.venv/bin/python scripts/check_gpu_env.py
```

OCR support depends on your local Tesseract installation when using the `tesseract` backend. See `docs/OCR_PIPELINE.md` for details.

## Offline Index Build

Validate item metadata:

```bash
.venv/bin/python scripts/validate_items.py \
  --items data/items.csv \
  --risk-labels configs/risk_labels.yaml
```

Build an image manifest:

```bash
.venv/bin/python scripts/build_image_manifest.py \
  --items data/items.csv \
  --output data/image_manifest.csv
```

Run text rules:

```bash
.venv/bin/python scripts/run_rules.py \
  --items data/items.csv \
  --rules configs/rules.yaml \
  --risk-labels configs/risk_labels.yaml \
  --output outputs/evidence/rule_evidence.jsonl \
  --summary outputs/evidence/rule_summary.csv
```

Run OCR and OCR rules:

```bash
.venv/bin/python scripts/run_ocr.py \
  --items data/items.csv \
  --backend auto \
  --output outputs/ocr/item_ocr.jsonl

.venv/bin/python scripts/run_ocr_rules.py \
  --ocr outputs/ocr/item_ocr.jsonl \
  --rules configs/rules.yaml \
  --risk-labels configs/risk_labels.yaml \
  --output outputs/evidence/ocr_rule_evidence.jsonl \
  --summary outputs/evidence/ocr_rule_summary.csv
```

Compute image embeddings with SigLIP:

```bash
.venv/bin/python scripts/compute_clip_image_embeddings.py \
  --manifest data/image_manifest.csv \
  --model-name google/siglip-base-patch16-224 \
  --device auto \
  --batch-size 32 \
  --output outputs/embeddings/siglip_image_embeddings.npz \
  --manifest-output outputs/embeddings/siglip_image_embeddings_manifest.csv
```

Run image-to-item retrieval:

```bash
.venv/bin/python scripts/run_clip_image_retrieval.py \
  --embeddings outputs/embeddings/siglip_image_embeddings.npz \
  --manifest outputs/embeddings/siglip_image_embeddings_manifest.csv \
  --top-k 5 \
  --min-score 0.97 \
  --results outputs/retrieval_results/siglip_image_similarity.csv \
  --output outputs/evidence/siglip_image_similarity_evidence.jsonl
```

Build item-level audit cases:

```bash
.venv/bin/python scripts/build_evidence.py \
  --items data/items.csv \
  --evidence outputs/evidence/rule_evidence.jsonl \
  --evidence outputs/evidence/ocr_rule_evidence.jsonl \
  --evidence outputs/evidence/siglip_image_similarity_evidence.jsonl \
  --output outputs/evidence/audit_cases.jsonl \
  --summary outputs/evidence/audit_cases.csv \
  --include-clean
```

## Query CLI

Run a text query over the prepared audit cases:

```bash
.venv/bin/python scripts/query_cli.py \
  --query "查一下加微信私聊的商品" \
  --items data/items.csv \
  --cases outputs/evidence/audit_cases.jsonl \
  --queries configs/retrieval_queries.yaml \
  --intent-config configs/intent_router.yaml \
  --only-risk
```

Run an image-based query with a reference image:

```bash
.venv/bin/python scripts/query_cli.py \
  --query "查找相似商品图片" \
  --items data/items.csv \
  --cases outputs/evidence/audit_cases.jsonl \
  --query-image path/to/reference.jpg \
  --top-k 5 \
  --image-min-score 0.97
```

The CLI supports template and hybrid routing. If you enable LLM routing, configure `configs/intent_router.yaml` and set API keys through environment variables or a local `.env` file.

## Evidence Output

Evidence records are JSONL objects. Audit cases aggregate evidence by item and contain:

- `item_id`
- risk labels and confidence scores
- matched rule/OCR snippets
- similar image matches and similarity scores
- suggested moderation action

The recommended moderation actions are configured in `configs/risk_labels.yaml`:

```text
pass
manual_review
remove_or_block
merge_duplicate
```

## What Is Not Included

The clean release intentionally excludes:

- generated or crawled product images
- synthetic dataset generation configs
- experiment outputs and metrics
- embedding caches
- model weights
- local virtual environments
- development logs

This keeps the repository focused on the final architecture and runnable system components.

## Documentation

- `docs/CLOUD_SETUP.md`: cloud GPU setup and model inference notes.
- `docs/IMAGE_MANIFEST_AND_EMBEDDINGS.md`: image manifest and embedding cache design.
- `docs/OCR_PIPELINE.md`: OCR backend and OCR evidence flow.

## License

Add a license before publishing or reusing this project in a public setting.
