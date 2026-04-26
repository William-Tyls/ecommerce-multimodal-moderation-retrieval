# 电商违规审核多模态检索系统

这是一个面向电商平台内容审核场景的多模态检索系统，用于帮助审核员从商品标题、详情文案、OCR 文本和商品图片中快速定位疑似违规商品，并生成可解释的审核证据链。

## 项目目标

本仓库只保留最终系统架构和可运行代码，不包含实验阶段的数据集、生成图片、模型权重、embedding 缓存或评估产物。

系统核心能力：

- 基于规则识别违禁商品、品牌侵权、站外导流、夸大宣传、重复铺货等风险。
- 对商品图片进行 OCR 识别，并对 OCR 文本继续执行违规规则检测。
- 使用 CLIP 兼容的视觉模型生成商品图片 embedding，推荐使用 SigLIP 作为主视觉 backbone。
- 基于离线图片 embedding 进行图搜商品、相似商品检索和近重复图片召回。
- 将规则、OCR、图片相似度等证据聚合成商品级 audit case。
- 提供命令行查询入口，支持自然语言审核查询和图片查询。

## 最终架构

```text
商品 metadata + 商品图片
  -> 商品字段校验
  -> 构建图片级 manifest
  -> 执行标题 / 描述规则检测
  -> 执行 OCR 与 OCR 规则检测
  -> 使用 SigLIP 生成图片 embedding
  -> 基于图片 embedding 检索相似商品
  -> 聚合多源证据
  -> 生成商品级审核 case
  -> 查询或导出审核结果
```

推荐的最终视觉检索配置：

```text
图片 backbone: google/siglip-base-patch16-224
检索方式: 基于离线 embedding cache 的 image-to-item nearest-neighbor search
证据阈值: 按业务数据重新校准；审核场景建议从保守阈值开始
```

这个系统不是生成式 RAG 聊天机器人，而是一个“检索 + 证据聚合 + 风险判断”的审核辅助系统。后续可以接入大语言模型用于总结证据，但核心审核判断应当尽量基于结构化证据，而不是自由生成文本。

## 仓库结构

```text
configs/
  intent_router.yaml          # 查询意图路由配置
  retrieval_queries.yaml      # 检索查询模板与默认参数
  risk_labels.yaml            # 风险标签与建议处理动作
  rules.yaml                  # 标题 / 描述 / OCR 文本规则

src/
  agents/                     # 意图识别与路由
  evidence/                   # 商品级证据聚合
  ocr/                        # OCR backend 抽象
  retrieval/                  # 文本 / 图片检索工具
  rules/                      # 规则匹配引擎

scripts/
  validate_items.py           # 校验商品 metadata
  build_image_manifest.py     # 构建图片级 manifest
  run_rules.py                # 执行文本规则检测
  run_ocr.py                  # 对商品图片执行 OCR
  run_ocr_rules.py            # 对 OCR 文本执行规则检测
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

## 数据格式

仓库不附带商品数据。使用时需要自行准备 `data/items.csv`，字段如下：

```csv
item_id,title,description,category,shop_id,image_paths,ocr_text,risk_labels,risk_objects,source,split
sku_000001,示例商品标题,示例商品详情,electronics,shop_001,data/images/sku_000001/main.jpg,,normal,,internal,test
```

字段说明：

- `item_id`：商品唯一 ID。
- `title`：商品标题。
- `description`：商品详情文案。
- `category`：商品类目。
- `shop_id`：店铺或卖家 ID。
- `image_paths`：商品图片路径，多个路径使用 `|` 分隔。
- `ocr_text`：可选的预置 OCR 文本，多个片段使用 `|` 分隔。
- `risk_labels`：可选的风险标签，多个标签使用 `|` 分隔。
- `risk_objects`：可选的图片风险元素或策略对象，多个对象使用 `|` 分隔。
- `source`：数据来源。
- `split`：可选的数据划分，例如 `train`、`val`、`test`。

当前支持的风险标签配置在 `configs/risk_labels.yaml`：

```text
prohibited_goods       违禁商品
counterfeit_brand      品牌侵权或假货风险
image_duplicate        盗图或重复铺货
off_platform_contact   导流或平台外交易
misleading_claim       夸大宣传
normal                 正常商品
```

## 环境安装

创建 Python 环境并安装依赖：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements-cloud.txt
```

检查本地或云端 GPU 环境：

```bash
.venv/bin/python scripts/check_gpu_env.py
```

如果使用 `tesseract` OCR backend，需要本地或服务器已安装 Tesseract。OCR 说明见 `docs/OCR_PIPELINE.md`。

## 离线索引构建流程

校验商品 metadata：

```bash
.venv/bin/python scripts/validate_items.py \
  --items data/items.csv \
  --risk-labels configs/risk_labels.yaml
```

构建图片级 manifest：

```bash
.venv/bin/python scripts/build_image_manifest.py \
  --items data/items.csv \
  --output data/image_manifest.csv
```

执行标题 / 描述规则检测：

```bash
.venv/bin/python scripts/run_rules.py \
  --items data/items.csv \
  --rules configs/rules.yaml \
  --risk-labels configs/risk_labels.yaml \
  --output outputs/evidence/rule_evidence.jsonl \
  --summary outputs/evidence/rule_summary.csv
```

执行 OCR 与 OCR 规则检测：

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

使用 SigLIP 生成图片 embedding：

```bash
.venv/bin/python scripts/compute_clip_image_embeddings.py \
  --manifest data/image_manifest.csv \
  --model-name google/siglip-base-patch16-224 \
  --device auto \
  --batch-size 32 \
  --output outputs/embeddings/siglip_image_embeddings.npz \
  --manifest-output outputs/embeddings/siglip_image_embeddings_manifest.csv
```

基于 embedding 执行图搜商品：

```bash
.venv/bin/python scripts/run_clip_image_retrieval.py \
  --embeddings outputs/embeddings/siglip_image_embeddings.npz \
  --manifest outputs/embeddings/siglip_image_embeddings_manifest.csv \
  --top-k 5 \
  --min-score 0.97 \
  --results outputs/retrieval_results/siglip_image_similarity.csv \
  --output outputs/evidence/siglip_image_similarity_evidence.jsonl
```

聚合多源证据，生成商品级审核 case：

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

## 查询 CLI

基于已生成的 audit cases 执行自然语言查询：

```bash
.venv/bin/python scripts/query_cli.py \
  --query "查一下加微信私聊的商品" \
  --items data/items.csv \
  --cases outputs/evidence/audit_cases.jsonl \
  --queries configs/retrieval_queries.yaml \
  --intent-config configs/intent_router.yaml \
  --only-risk
```

使用参考图片执行相似商品查询：

```bash
.venv/bin/python scripts/query_cli.py \
  --query "查找相似商品图片" \
  --items data/items.csv \
  --cases outputs/evidence/audit_cases.jsonl \
  --query-image path/to/reference.jpg \
  --top-k 5 \
  --image-min-score 0.97
```

CLI 支持 template 和 hybrid 路由。如果启用 LLM routing，需要配置 `configs/intent_router.yaml`，并通过环境变量或本地 `.env` 提供 API key。

## 输出格式

Evidence records 使用 JSONL 格式。Audit case 会按商品聚合证据，主要包含：

- `item_id`
- 风险类型和置信度
- 规则命中文本
- OCR 命中文本
- 相似图片匹配结果和相似度
- 建议处理动作

建议处理动作配置在 `configs/risk_labels.yaml`：

```text
pass              放行
manual_review     人工复核
remove_or_block   下架或拦截
merge_duplicate   聚合处理
```

## 本仓库不包含的内容

为了保持 GitHub 版本干净，本仓库刻意不包含：

- 生成或爬取的商品图片
- 合成数据生成配置
- 实验输出和评估指标
- embedding 缓存
- 模型权重
- 本地虚拟环境
- 开发过程日志

仓库只保留最终架构、核心代码、配置和必要文档。

## 文档

- `docs/CLOUD_SETUP.md`：云端 GPU 环境和模型推理说明。
- `docs/IMAGE_MANIFEST_AND_EMBEDDINGS.md`：图片 manifest 与 embedding cache 设计。
- `docs/OCR_PIPELINE.md`：OCR backend 与 OCR evidence 流程。

## License

公开发布或复用前，请补充合适的开源协议。
