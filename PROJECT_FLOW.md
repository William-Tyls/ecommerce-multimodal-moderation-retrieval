# E-Commerce Moderation Multimodal Retrieval Agent Project Flow

本文档记录本项目从 0 到 1 的整体设计、开发流程和阶段目标。后续如果上下文窗口不足，可以优先读取本文档来恢复项目方向。

## 1. Project Goal

本项目目标是：针对电商平台违规内容审核中“违禁词、盗图、品牌侵权、违禁商品定位效率低、人工排查耗时长”的问题，构建一套支持自然语言问答式交互的多模态商品图文检索系统，实现对疑似违规商品的精确定位、证据链构建与高效处理。

系统最终应具备以下能力：

- 商品文搜商品：审核员输入自然语言问题，系统检索相关商品图片、标题、详情文案和 OCR 文本。
- 图搜商品：审核员上传疑似盗图、侵权图或违禁商品图，系统返回相似商品和可疑来源。
- 图文联合检索：同时使用参考图和文本条件定位风险商品。
- 文案违规检索：定位违禁词、导流词、夸大宣传、敏感词及其上下文。
- 细粒度风险识别：识别商品图中较小的 logo、商标、包装文字、违禁物、联系方式等风险元素。
- 证据链构建：为每个疑似违规商品输出命中原因、相似度、命中文案、OCR 片段、模型标签和建议处理动作。
- 审核意图识别：判断用户是在查违禁品、查盗图、查侵权、查文案违规，还是普通问答，并路由到合适检索流程。
- 实验评估：系统性评估违规召回率、误判率、TopK 审核效率、证据命中率和基础检索指标。

一句话概括：

> 这个项目不是单纯调用 CLIP 做图像检索，而是构建一个面向电商违规审核场景的多模态检索 Agent，用商品图文向量检索、OCR、图像理解和意图路由帮助审核员快速定位可疑商品并生成可解释证据链。

## 2. Recommended Project Mainline

项目建议按以下优先级推进：

1. 构建固定的电商商品多模态审核数据集，第一版约 2000 个商品 item。
2. 建立商品数据 schema：商品图片、标题、详情文案、OCR 文本、风险标签、证据字段。
3. 跑通 CLIP 系列模型的文搜商品、图搜商品、图文联合检索。
4. 离线缓存图片 embedding、文本 embedding、OCR/text embedding，搭建基础检索和评估代码。
5. 对比不同 backbone：OpenAI CLIP、Chinese CLIP、Taiyi CLIP、SigLIP。
6. 加入 OCR 和规则词表，实现文案违规、图片中文字违规的定位。
7. 引入 RAM 或 Qwen2.5-VL，对商品图片生成风险元素标签，增强细粒度审核能力。
8. 构建审核意图识别数据集和审核 Agent，将自然语言问题路由到不同检索流程。
9. 输出商品级风险结果和证据链，做一个可交互 demo。
10. 主流程稳定后，再做 Tip-Adapter / CLIP-Adapter / Prompt Tuning 等面向业务类别的轻量微调。

不建议一开始就做微调或蒸馏。先把数据、检索、证据链、评估和 demo 主流程跑通。

## 3. Business Scope

第一版聚焦 5 类审核风险：

1. 违禁商品：如电子烟、管制刀具、仿真枪、处方药等。
2. 品牌侵权 / 假货风险：如疑似高仿、同款、A 货、品牌 logo 滥用。
3. 盗图 / 重复铺货：商品主图高度相似，或同图被多个商品使用。
4. 文案违规：违禁词、导流词、联系方式、夸大宣传、平台外交易暗示。
5. 正常商品：用于对照和误判率评估。

第一阶段建议具体落地为 5 个风险目标：

- vape / electronic cigarette：电子烟或相关配件。
- knife / tactical knife：刀具或危险器具。
- luxury logo / counterfeit brand：疑似品牌侵权。
- off-platform contact：微信、VX、手机号、二维码、私聊等导流。
- image duplicate / near duplicate：盗图或重复铺货。

## 4. Dataset Design

### 4.1 Final Dataset Size

最终固定一个约 2000 个商品 item 的数据集。每个 item 可以包含 1-5 张商品图片，以及标题、详情文案、OCR 文本和风险标签。

建议第一版规模：

- 商品 item：2000 个。
- 风险商品：约 400 个。
- 正常商品：约 1600 个。
- 风险 / 正常比例：约 1:4。
- 每类风险商品：约 80 个。
- 每个商品图片数：1-5 张。

如果早期数据构建困难，可以先做 500 个 item 的 mini dataset，跑通后再扩展到 2000。

### 4.2 Item Schema

商品级数据应以 item 为中心，而不是以单张图片为中心。

示例：

```json
{
  "item_id": "sku_000001",
  "title": "潮流同款电子雾化器配件",
  "description": "支持私聊咨询，量大优惠",
  "category": "electronics",
  "shop_id": "shop_001",
  "image_paths": [
    "data/images/sku_000001/main.jpg",
    "data/images/sku_000001/detail_1.jpg"
  ],
  "ocr_text": ["VAPE", "加 VX 详聊"],
  "risk_labels": ["prohibited_goods", "off_platform_contact"],
  "risk_objects": ["vape"],
  "source": "synthetic_public",
  "split": "test"
}
```

### 4.3 Metadata Format

建议使用 `data/items.csv` 或 `data/items.jsonl` 管理商品级数据。

CSV 简化字段：

```csv
item_id,title,description,category,shop_id,image_paths,ocr_text,risk_labels,risk_objects,source,split
sku_000001,潮流同款电子雾化器配件,支持私聊咨询,electronics,shop_001,data/images/sku_000001/main.jpg|data/images/sku_000001/detail_1.jpg,VAPE|加 VX 详聊,prohibited_goods|off_platform_contact,vape,synthetic_public,test
```

推荐字段说明：

- `item_id`: 商品唯一 ID。
- `title`: 商品标题。
- `description`: 商品详情或模拟详情文案。
- `category`: 商品类目。
- `shop_id`: 店铺 ID，用于模拟重复铺货、盗图聚合。
- `image_paths`: 商品图片路径，多个图片用分隔符或 JSON 数组。
- `ocr_text`: 图片 OCR 文本。
- `risk_labels`: 商品风险标签，可多标签。
- `risk_objects`: 图片中出现的风险物体或风险元素。
- `source`: 数据来源。
- `split`: train / val / test。

### 4.4 Data Sources

真实平台审核数据通常拿不到，所以本项目采用“公开图片 + 模拟商品文案 + 可控风险标签”的方式构建实验集。

推荐混合数据源：

- COCO / Open Images / ImageNet 子集：补充通用商品、背景、正常商品和部分风险物体。
- 网络图片 API：补充电商风格商品图片、包装图、场景图。
- 公开电商商品数据集：如果可获得，用于标题、描述、类目结构。
- 合成文案：用模板或 LLM 生成商品标题、详情、导流词、违规词和正常商品文案。
- 手工抽查：保证风险标签、商品图文关系和边界样本质量。

不要下载完整 ImageNet 到本地。最终只保存固定的商品实验集和必要的样例图。

### 4.5 Risk Label Design

建议第一版使用以下标签：

```text
prohibited_goods        # 违禁商品
counterfeit_brand       # 品牌侵权 / 假货
image_duplicate         # 盗图 / 重复铺货
off_platform_contact    # 导流 / 私下交易
misleading_claim        # 夸大宣传
normal                  # 正常商品
```

每个商品允许多标签，例如一个商品可以同时是 `prohibited_goods` 和 `off_platform_contact`。

### 4.6 Evidence Schema

证据链是本项目区别于普通检索项目的核心。

示例：

```json
{
  "item_id": "sku_000123",
  "risk_type": "off_platform_contact",
  "confidence": 0.91,
  "evidence": [
    {
      "type": "text_rule_match",
      "field": "description",
      "matched_text": "加 VX 详聊",
      "rule": "off_platform_contact_keywords"
    },
    {
      "type": "ocr_rule_match",
      "image": "main.jpg",
      "matched_text": "微信 138****0000",
      "rule": "phone_or_wechat_pattern"
    },
    {
      "type": "image_similarity",
      "image": "main.jpg",
      "matched_item_id": "sku_000088",
      "similarity": 0.94
    },
    {
      "type": "vlm_tag",
      "image": "detail_1.jpg",
      "tag": "vape device"
    }
  ],
  "suggested_action": "manual_review"
}
```

建议处理动作：

- `pass`: 暂无明显风险。
- `manual_review`: 进入人工复核。
- `remove_or_block`: 高风险，建议下架或拦截。
- `merge_duplicate`: 疑似重复铺货或盗图，建议聚合处理。

## 5. Dataset Storage Strategy

本地 Mac 不需要保存大数据集。推荐三层存储：

```text
Local Mac:
  code
  configs
  metadata
  small samples
  reports

Cloud GPU Server:
  final item images
  model weights
  image embeddings
  text embeddings
  OCR outputs
  VLM/RAM outputs
  retrieval outputs

Optional Object Storage:
  raw candidate images
  dataset backup
  training data
```

Git 中不提交图片和大模型文件，只提交：

- 数据构建脚本。
- 风险类别配置。
- items metadata。
- 规则词表。
- 实验配置。
- 评估代码。
- 小规模样例和实验摘要。

## 6. Compute Strategy

### 6.1 Local Mac M4

Mac M4 适合：

- 写代码。
- 整理配置。
- 构建和校验 metadata。
- 少量商品样例调试。
- 小批量 CLIP 推理。
- 规则词表和评估逻辑开发。
- 写报告和 demo 前端。

Mac M4 不适合作为主力：

- Qwen2.5-VL 批量推理。
- OCR 大批量处理。
- 多模型全量 embedding 提取。
- CLIP Adapter 微调。
- 大规模 few-shot 实验。

### 6.2 Cloud GPU

正式推理和微调建议放到云 GPU。

推荐方式：

```text
Mac VS Code
  -> VS Code Remote SSH
  -> Cloud GPU Server
  -> Run PyTorch / Jupyter / Training / Inference
```

可选平台：

- RunPod
- Lambda Cloud
- AutoDL
- Vast.ai
- Paperspace
- AWS / GCP / Azure

第一阶段只需要一张中等 GPU，例如 RTX 4090、A5000、A10、L4。Qwen2.5-VL 和微调阶段再根据显存需求升级。

### 6.3 Development Workflow

推荐工作流：

1. 本地维护 Git 仓库。
2. 云端 clone 同一仓库。
3. 用 VS Code Remote SSH 连接云 GPU。
4. 在云端安装依赖和下载模型。
5. 在云端生成 embeddings、OCR/VLM 输出、实验结果。
6. 将小结果文件、配置、代码同步回 Git。
7. 图片、模型权重、大 embedding 文件不进 Git。

## 7. System Architecture

整体系统分为六层：

```text
Auditor Query
  -> Moderation Intent Agent
  -> Retrieval / Risk Router
  -> Multimodal Retrieval Pipelines
  -> Evidence Builder
  -> Risk Ranking / Action Suggestion
  -> Item Results + Evidence Chain
```

### 7.1 Moderation Intent Agent

输入：

- 审核员文本问题。
- 或参考图片 + 文本问题。

输出：

- 是否需要检索。
- 审核任务类型：违禁商品、盗图、品牌侵权、文案违规、普通问答。
- 检索类型：text-to-item / image-to-item / multimodal / text-rule / OCR-rule。
- 检索策略：TopK / threshold。
- query 文本。
- TopK 中的 K 值。
- 需要调用的证据模块。

示例：

```json
{
  "need_retrieval": true,
  "audit_task": "prohibited_goods",
  "retrieval_type": "text_to_item",
  "query": "疑似售卖电子烟的商品",
  "strategy": "topk",
  "top_k": 20,
  "evidence_modules": ["image_similarity", "vlm_tag", "ocr_rule"]
}
```

### 7.2 Retrieval / Risk Router

根据意图识别结果选择流程：

- 不需要检索：直接回答或返回普通问答结果。
- 违禁商品检索：调用文本到图片、文本到标签、图像理解标签检索。
- 盗图 / 重复铺货：调用图搜商品、近重复检测、商品聚类。
- 品牌侵权：调用 logo/品牌文本检索、OCR、图文联合检索。
- 文案违规：调用规则词表、文本 embedding 检索、OCR 文本检索。
- 综合审核：多路检索结果融合后生成证据链。

### 7.3 Retrieval Pipelines

商品文搜商品：

```text
auditor query
  -> text encoder
  -> query embedding
  -> search image embeddings + title/description embeddings + OCR embeddings
  -> aggregate scores by item
  -> ranked suspicious items
```

图搜商品：

```text
reference image
  -> image encoder
  -> reference embedding
  -> search item image embedding index
  -> aggregate image-level matches to item-level results
  -> near-duplicate / similar item list
```

文案违规：

```text
title / description / OCR text
  -> keyword rules + regex rules
  -> matched snippets
  -> evidence records
```

细粒度风险增强：

```text
Offline:
  item images
  -> OCR + RAM / Qwen2.5-VL
  -> object tags / brand text / scene description / risk elements
  -> text encoder
  -> tag embedding index

Online:
  audit query
  -> text encoder
  -> search tag embedding index
  -> ranked suspicious items + tag evidence
```

图文融合：

```text
query text + reference image
  -> text embedding + image embedding
  -> feature fusion or score fusion
  -> item-level ranking
```

### 7.4 Evidence Builder

Evidence Builder 将检索结果转为审核可读证据：

- 哪个商品命中。
- 命中哪张图片或哪个文本字段。
- 命中风险类型是什么。
- 相似度或规则命中分数是多少。
- 是否有 OCR/VLM/规则多证据交叉支持。
- 建议人工复核、下架、放行或聚合处理。

## 8. Experiment Plan

### 8.1 Stage 1: Project Skeleton and Data Schema

目标：

- 创建项目目录结构。
- 定义 item schema、risk labels、evidence schema。
- 建立 `items.csv` / `items.jsonl` 模板。
- 实现 metadata 校验和数据统计脚本。

产出：

- `PROJECT_FLOW.md`
- `configs/risk_labels.yaml`
- `configs/rules.yaml`
- `data/items.csv`
- `scripts/validate_items.py`

### 8.2 Stage 2: Moderation Dataset Construction

目标：

- 构建 mini dataset，先 500 个商品 item。
- 扩展到 2000 个商品 item。
- 完成商品图片、标题、详情、OCR 文本、风险标签。
- 构造正常商品、风险商品、难负样本和边界样本。

产出：

- 商品级 metadata。
- 数据集统计报告。
- 风险类别分布。
- 样例证据标注。

### 8.3 Stage 3: Basic Multimodal Retrieval

目标：

- 跑通单个 CLIP 模型。
- 支持 image embedding、text embedding、similarity search。
- 将 image-level 结果聚合为 item-level 结果。
- 支持 TopK 和 threshold 两种返回方式。

产出：

- embedding 缓存。
- 文搜商品脚本。
- 图搜商品脚本。
- item-level 检索结果。

### 8.4 Stage 4: Text and OCR Risk Detection

目标：

- 建立违禁词、导流词、联系方式、夸大宣传规则词表。
- 对 title、description、OCR 文本执行规则匹配。
- 输出命中文案片段和 evidence records。

产出：

- `configs/rules.yaml`
- 文本规则检测结果。
- OCR 规则检测结果。
- 文案违规评估结果。

### 8.5 Stage 5: Backbone Comparison

候选模型：

- OpenAI CLIP。
- Chinese CLIP。
- Taiyi CLIP。
- SigLIP。

目标：

- 使用统一接口封装不同模型。
- 比较不同模型在电商审核任务上的表现。
- 选择后续主干模型。

关键点：

- 所有 embedding 需要 normalize。
- 不同模型的相似度分布不同，阈值不能共用。
- 中文/英文 prompt template 要公平设计。
- 评估以 item-level 风险召回为主，而不是只看 image-level 命中。

### 8.6 Stage 6: Image-to-Item Duplicate and Infringement Retrieval

实验：

- 单张参考图查相似商品。
- 多张商品图特征聚合。
- 近重复图片检索。
- 商品级聚类发现重复铺货。
- 图文联合定位品牌侵权。

评估：

- TopK duplicate recall。
- 相似商品命中率。
- 人工审查前 K 个结果的风险覆盖率。

注意：

- 检索库中必须排除 query item 本身。
- 需要做重复图片去重，否则指标会虚高。
- 图搜商品要聚合到 item 级，不要只输出相似图片。

### 8.7 Stage 7: Fine-Grained Risk Understanding

候选方法：

- OCR：识别图片中的品牌名、联系方式、敏感文字。
- RAM：输出图片标签。
- Qwen2.5-VL：输出商品主体、品牌元素、风险物体、场景描述。

流程：

- 离线对商品图片生成 OCR 和 VLM 标签。
- 规范化输出。
- 用文本编码器编码标签。
- 建立 tag embedding index。
- 在线用审核 query 检索 tag embedding index。
- 将标签命中转为证据链。

Qwen-VL 输出需要固定 JSON 格式，例如：

```json
{
  "main_product": "electronic cigarette",
  "visible_text": ["VAPE", "加 VX"],
  "brand_or_logo": ["unknown logo"],
  "risk_elements": ["vape device", "off-platform contact"],
  "scene": "product display"
}
```

需要单独评估：

- OCR / VLM 是否识别出风险元素。
- 标签检索是否能找对商品。
- 最终是否提升细粒度风险召回。

### 8.8 Stage 8: Moderation Intent Agent

构建审核意图识别数据集：

- 总量约 2000 条。
- 需要审核检索：约 1500 条。
- 不需要检索或普通问答：约 500 条。
- 覆盖违禁商品、盗图、品牌侵权、文案违规、综合查询。

需要识别：

- 是否需要检索。
- 审核任务类型。
- 文搜商品、图搜商品、图文联合还是规则检索。
- TopK 还是 threshold。
- query/category/risk_type。
- K 值。

示例问题：

```text
帮我找疑似卖电子烟的商品
这张图有没有被别的店铺盗用
查一下标题里带微信导流的商品
找 20 个疑似高仿品牌鞋的商品
这批结果里哪些需要人工复核
```

评估：

- 是否需要检索的 Precision、Recall、F1。
- 审核任务类型识别准确率。
- 检索方式识别准确率。
- query / risk_type 抽取准确率。

### 8.9 Stage 9: Evidence Chain and Demo

目标：

- 提供一个可交互 demo。
- 输入自然语言问题或参考图片。
- 自动识别审核意图。
- 自动路由到对应检索流程。
- 展示商品列表、风险标签、命中字段、相似度、证据链和建议动作。

可选形式：

- CLI demo。
- Streamlit demo。
- Gradio demo。
- 简单 Web UI。

推荐展示字段：

- item_id
- 商品标题
- 商品图片
- 风险类型
- 风险分数
- 命中文案 / OCR 片段
- 相似商品
- VLM 标签
- suggested_action

### 8.10 Stage 10: Fine-Tuning Extension

在主流程稳定后再做。

候选方法：

- Tip-Adapter。
- CLIP-Adapter。
- CoOp。
- MaPLe。

实验：

- 每个风险类型 10、100、200、500 个 few-shot 样本。
- 与 training-free CLIP 方法对比。
- 评估违规召回率、误判率、F1 和 TopK 审核效率。

注意：

- 训练集和测试集必须尽量不重合。
- 微调可能不升反降，需要控制数据质量。
- 微调目标应围绕业务风险类别，而不是泛化图像分类类别。

## 9. Evaluation Principles

### 9.1 Core Metrics

基础检索指标：

- Precision
- Recall
- F1
- TopK Precision
- TopK Recall

审核业务指标：

- 违规召回率：系统能找出多少真实违规商品。
- 误判率：正常商品被误判为风险商品的比例。
- TopK 审核覆盖率：人工查看前 K 个结果时覆盖多少违规商品。
- 证据命中率：返回的风险商品中有多少包含可解释证据。
- 商品级命中率：item-level 是否命中，而不是单图命中。
- 平均定位时间：相比人工搜索节省多少时间，可在 demo 或模拟实验中估算。

推荐使用 macro average：

```text
先计算每个风险类型的 P/R/F1，再对风险类型取平均。
```

### 9.2 Threshold Evaluation

阈值扫描：

```text
threshold = 0.10, 0.15, 0.20, ..., 0.90
```

更严谨的做法：

```text
calibration/validation set: select threshold
test set: final report
```

如果数据量不足，允许先做 oracle threshold，但报告中要明确说明。

### 9.3 TopK Evaluation

TopK 设置：

```text
TopK@1
TopK@5
TopK@10
TopK@20
TopK@50
```

TopK 适合审核员明确要求“找前 K 个可疑商品”的场景。Threshold 适合批量巡检或自动过滤。

### 9.4 Evidence Evaluation

证据链需要单独评估：

- 是否包含命中字段。
- 是否包含可读的风险原因。
- 是否能指向具体图片、标题、详情或 OCR 片段。
- 多证据是否一致。
- 证据是否足以支持人工复核。

## 10. Known Risks

### 10.1 Dataset Risks

- 真实电商审核数据难以获取。
- 模拟商品文案可能过于模板化。
- 风险标签和真实平台规则存在差距。
- 图片与商品文案可能不匹配。
- 盗图 / 重复铺货样本构造容易过于简单。
- 品牌侵权样本涉及商标和版权风险，公开展示时需要谨慎。
- 多标签商品边界模糊。

### 10.2 Model Risks

- 不同 CLIP 模型接口差异大。
- 中文/英文 prompt 会影响公平对比。
- 商品图片细节小，CLIP 可能被背景或主视觉误导。
- OCR 可能漏识别、错识别。
- Qwen-VL 输出不稳定，需要 JSON 约束和解析兜底。
- VLM 可能幻觉风险元素。

### 10.3 Evaluation Risks

- 在测试集上选阈值会高估效果。
- 图搜图未排除 query item 会造成数据泄漏。
- 重复图会使盗图检索指标虚高。
- image-level 和 item-level 指标混用会导致结果不可比。
- macro/micro average 混用会导致结果不可比。
- 证据链质量如果只靠模型自评，会不可靠。

### 10.4 Engineering Risks

- 云端环境和本地环境不一致。
- 模型权重、OCR 输出、embedding 文件过大。
- 在线调用大模型太慢。
- 未缓存 embeddings 导致每次实验重复计算。
- 多模型实验数量过多，容易做散。
- 规则词表容易变成硬编码，需要配置化管理。

## 11. Suggested Repository Structure

后续建议搭建如下目录：

```text
Multimodal_Retrieval/
  PROJECT_FLOW.md
  README.md
  configs/
    risk_labels.yaml
    rules.yaml
    models.yaml
    experiments.yaml
  data/
    items.csv
    samples/
  scripts/
    build_dataset.py
    validate_items.py
    compute_embeddings.py
    run_retrieval.py
    run_rules.py
    build_evidence.py
    evaluate.py
  src/
    datasets/
    models/
    retrieval/
    rules/
    ocr/
    evidence/
    evaluation/
    agents/
    utils/
  notebooks/
  outputs/
    metrics/
    retrieval_results/
    evidence/
    figures/
  docs/
  项目介绍文件/
```

大文件不提交 Git：

- `data/images/`
- `data/raw/`
- `features/`
- `checkpoints/`
- `models/`
- 大型 `outputs/`

## 12. Immediate Next Steps

下一步从工程骨架开始：

1. 创建基础目录结构。
2. 创建 `README.md`。
3. 创建 `configs/risk_labels.yaml`，明确风险类型和动作类型。
4. 创建 `configs/rules.yaml`，放入第一版违禁词、导流词和联系方式规则。
5. 创建 `data/items.csv` 的空模板。
6. 创建 `.gitignore`，忽略图片、模型权重、embedding 和大输出文件。
7. 创建最小 Python 包结构。
8. 先实现商品 metadata 校验和数据集统计脚本。

第一阶段目标不是马上跑大模型，而是先把商品数据规范、风险标签体系和证据链格式搭起来。
