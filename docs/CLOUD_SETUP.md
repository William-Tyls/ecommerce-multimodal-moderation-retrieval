# Cloud GPU Setup

本文档记录下一阶段云端 GPU 环境准备。当前项目已经完成本地 MVP、OCR 旁路、CLI demo 和 evidence/case 闭环；下一步云端目标是 **CLIP / SigLIP 图文 embedding inference**，不是训练。

## Current Goal

第一批云端实验只做：

```text
GPU environment check
  -> CLIP/SigLIP model load
  -> sample image embedding smoke
  -> image embedding cache design validation
  -> text-to-image / image-to-item retrieval prototype
```

暂不做：

```text
fine-tuning
large VLM batch inference
expensive multi-model sweep
```

## Recommended Instance

优先选一张 24GB 左右的 GPU：

```text
RTX 4090 24GB
RTX 3090 24GB
NVIDIA L4 24GB
RTX A5000 24GB
```

最低也可以：

```text
T4 16GB
A10 24GB
```

建议磁盘：

```text
80-150 GB
```

原因：

- CLIP / SigLIP inference 不需要 H100/A100。
- 模型权重、Python wheel、embedding cache 会占用磁盘。
- 24GB 显存足够做第一阶段 embedding 和小批量 VLM smoke。

## Provider Choice

短实验优先：

```text
RunPod
Vast.ai
AutoDL
Lambda Cloud
```

稳定可复现实验：

```text
AWS / GCP / Azure
```

如果使用竞价/低价实例，建议用 persistent volume 保存模型缓存，否则每次重启都要重新下载权重。

## Bootstrap

拿到 Ubuntu GPU 机器后：

```bash
git clone <your-repo-url> Multimodal_Retrieval
cd Multimodal_Retrieval

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-cloud.txt

python scripts/check_gpu_env.py
```

如果暂时没有 Git remote，用本地 Mac 同步：

```bash
rsync -av \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.DS_Store' \
  --exclude 'models' \
  --exclude 'checkpoints' \
  ./ user@server:~/work/Multimodal_Retrieval/
```

## PyTorch CUDA Note

`requirements-cloud.txt` 里保留了通用 `torch` / `torchvision`。如果装出来是 CPU-only，按云实例 CUDA 版本使用 PyTorch 官方 selector 重装，例如：

```bash
pip uninstall -y torch torchvision torchaudio
# Example only; choose the command that matches the instance CUDA runtime.
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

验证：

```bash
python - <<'PY'
import torch
print(torch.__version__)
print(torch.version.cuda)
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no cuda")
PY
```

## First Smoke Tests

基础项目回归：

```bash
python scripts/validate_items.py --items data/items.csv --risk-labels configs/risk_labels.yaml
python scripts/run_rules.py --items data/items.csv --rules configs/rules.yaml --risk-labels configs/risk_labels.yaml
```

CLIP image embedding smoke：

```bash
python scripts/smoke_clip_image_encoder.py \
  --items data/items.csv \
  --model-name openai/clip-vit-base-patch32 \
  --device auto \
  --limit 6
```

成功时应看到：

```text
Model: openai/clip-vit-base-patch32
Device: cuda
Images encoded: 6
Embedding shape: (6, 512)
Similarity matrix
```

如果模型下载太慢或失败，先确认：

```bash
python -c "import transformers, huggingface_hub; print(transformers.__version__)"
```

## First CLIP Cache Run

CLIP smoke 通过后，计算 v0.1 图片 embedding cache：

```bash
python scripts/compute_clip_image_embeddings.py \
  --manifest data/image_manifest.csv \
  --model-name openai/clip-vit-base-patch32 \
  --device auto \
  --batch-size 32 \
  --output outputs/embeddings/clip_image_embeddings.npz \
  --manifest-output outputs/embeddings/clip_image_embeddings_manifest.csv
```

然后跑 image-to-item 检索：

```bash
python scripts/run_clip_image_retrieval.py \
  --embeddings outputs/embeddings/clip_image_embeddings.npz \
  --manifest outputs/embeddings/clip_image_embeddings_manifest.csv \
  --top-k 5 \
  --min-score 0.0 \
  --results outputs/retrieval_results/clip_image_similarity.csv \
  --output outputs/evidence/clip_image_similarity_evidence.jsonl
```

第一轮先用 `--min-score 0.0` 保留完整候选，后续再扫阈值。CLIP/SigLIP 的相似度分布和当前 `SimpleImageEncoder` 不同，不能复用 `0.996` 阈值。

## Candidate Models

第一批按这个顺序：

```text
openai/clip-vit-base-patch32
google/siglip-base-patch16-224
```

后续中文/多语言再考虑：

```text
Chinese-CLIP variants
multilingual CLIP variants
```

不要一开始就做大规模模型对比。先把统一接口、cache、retrieval、metrics 跑通。

## Artifacts To Bring Back

云端生成后只同步小文件：

```text
outputs/retrieval_results/*.csv
outputs/evidence/*.jsonl if small
outputs/metrics/*.json
outputs/metrics/*.csv
docs experiment notes
```

不要同步：

```text
models/
checkpoints/
large embedding .npy/.npz
raw downloaded images
```

如果 embedding cache 很小可以临时带回；变大后保留在云端 persistent volume。

## Budget Guardrails

- 先按小时租，不要长期包月。
- 第一次只跑 1-2 小时环境和 smoke。
- 模型下载完成后记录磁盘占用。
- 每次结束前确认实例是否停止或释放。
- 如果用 AWS/GCP/Azure，先设 billing alert。

## Next Coding Step After Cloud Is Ready

云环境 smoke 通过后，回到代码层做：

```text
src/models/image_encoder.py
  -> add CLIP image encoder backend

scripts/compute_image_embeddings.py
  -> write image-level embedding cache

scripts/run_clip_image_retrieval.py
  -> image-to-item / text-to-image retrieval
```

先用 `data/items.csv` 做小规模 smoke，再跑 v0.3。
