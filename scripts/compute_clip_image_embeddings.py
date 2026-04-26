#!/usr/bin/env python3
"""Compute CLIP/SigLIP image embeddings from an image manifest."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"manifest has no header: {path}")
        return [dict(row) for row in reader]


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "embedding_index",
        "image_id",
        "item_id",
        "image_path",
        "image_role",
        "image_index",
        "title",
        "category",
        "shop_id",
        "risk_labels",
        "risk_objects",
        "source",
        "split",
        "model_name",
        "device",
        "embedding_dim",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_model(model_name: str, device: str, local_files_only: bool) -> tuple[Any, Any]:
    try:
        from transformers import AutoImageProcessor, AutoModel  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("transformers is required. Install requirements-cloud.txt first.") from exc

    processor = AutoImageProcessor.from_pretrained(model_name, local_files_only=local_files_only)
    model = AutoModel.from_pretrained(model_name, local_files_only=local_files_only)
    model.to(device)
    model.eval()
    return processor, model


def extract_embedding_tensor(output: Any) -> Any:
    if hasattr(output, "ndim"):
        return output
    for attr in ("image_embeds", "pooler_output", "last_hidden_state"):
        value = getattr(output, attr, None)
        if value is None:
            continue
        if attr == "last_hidden_state":
            return value[:, 0]
        return value
    if isinstance(output, (tuple, list)) and output:
        first = output[0]
        if hasattr(first, "ndim"):
            return first[:, 0] if getattr(first, "ndim", 0) == 3 else first
    raise TypeError(f"could not extract image embedding tensor from {type(output).__name__}")


def encode_batch(model: Any, processor: Any, image_paths: list[str], device: str) -> np.ndarray:
    try:
        import torch
        from PIL import Image
    except ModuleNotFoundError as exc:
        raise RuntimeError("torch and Pillow are required. Install requirements-cloud.txt first.") from exc

    images = [Image.open(path).convert("RGB") for path in image_paths]
    inputs = processor(images=images, return_tensors="pt")
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        if hasattr(model, "get_image_features"):
            output = model.get_image_features(**inputs)
        else:
            output = model(**inputs)
        embeddings = extract_embedding_tensor(output)
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
    return embeddings.cpu().numpy().astype(np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute CLIP/SigLIP image embeddings.")
    parser.add_argument("--manifest", default="data/image_manifest.csv", help="Image manifest CSV.")
    parser.add_argument("--model-name", default="openai/clip-vit-base-patch32", help="Hugging Face model name.")
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, cuda:0, or mps.")
    parser.add_argument("--batch-size", type=int, default=32, help="Image batch size.")
    parser.add_argument("--output", default="outputs/embeddings/clip_image_embeddings.npz", help="Embedding NPZ output.")
    parser.add_argument(
        "--manifest-output",
        default="outputs/embeddings/clip_image_embeddings_manifest.csv",
        help="Embedding manifest CSV output.",
    )
    parser.add_argument("--local-files-only", action="store_true", help="Do not download model files.")
    args = parser.parse_args()

    try:
        import torch
    except ModuleNotFoundError:
        print("ERROR: torch is required. Install requirements-cloud.txt first.", file=sys.stderr)
        return 2

    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    try:
        rows = [row for row in read_manifest(Path(args.manifest)) if Path(row.get("image_path", "")).exists()]
        if not rows:
            raise ValueError("no existing image paths found in manifest")
        processor, model = load_model(args.model_name, device=device, local_files_only=args.local_files_only)

        batches: list[np.ndarray] = []
        for start in range(0, len(rows), args.batch_size):
            batch_rows = rows[start : start + args.batch_size]
            batch_paths = [row["image_path"] for row in batch_rows]
            batches.append(encode_batch(model, processor, batch_paths, device=device))
        embeddings = np.vstack(batches)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        embeddings=embeddings,
        model_name=np.array([args.model_name]),
        image_ids=np.array([row.get("image_id", "") for row in rows]),
    )

    manifest_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        manifest_rows.append(
            {
                "embedding_index": idx,
                "image_id": row.get("image_id", ""),
                "item_id": row.get("item_id", ""),
                "image_path": row.get("image_path", ""),
                "image_role": row.get("image_role", ""),
                "image_index": row.get("image_index", ""),
                "title": row.get("title", ""),
                "category": row.get("category", ""),
                "shop_id": row.get("shop_id", ""),
                "risk_labels": row.get("risk_labels", ""),
                "risk_objects": row.get("risk_objects", ""),
                "source": row.get("source", ""),
                "split": row.get("split", ""),
                "model_name": args.model_name,
                "device": device,
                "embedding_dim": embeddings.shape[1],
            }
        )
    write_manifest(Path(args.manifest_output), manifest_rows)

    metadata = {
        "model_name": args.model_name,
        "device": device,
        "images_encoded": len(rows),
        "embedding_dim": int(embeddings.shape[1]),
        "embedding_output": args.output,
        "manifest_output": args.manifest_output,
    }
    metadata_path = output_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Model: {args.model_name}")
    print(f"Device: {device}")
    print(f"Images encoded: {len(rows)}")
    print(f"Embedding shape: {tuple(embeddings.shape)}")
    print(f"Embedding output: {args.output}")
    print(f"Manifest output: {args.manifest_output}")
    print(f"Metadata output: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
