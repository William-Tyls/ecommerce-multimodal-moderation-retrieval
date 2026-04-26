#!/usr/bin/env python3
"""Run image-to-item retrieval from a CLIP/SigLIP image embedding cache."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"manifest has no header: {path}")
        return [dict(row) for row in reader]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "query_item_id",
        "query_image_id",
        "query_image",
        "query_image_role",
        "matched_item_id",
        "matched_image_id",
        "matched_image",
        "matched_image_role",
        "rank",
        "score",
        "kept",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def to_evidence(query_row: dict[str, str], hit_row: dict[str, str], score: float, rank: int, model_name: str) -> dict[str, Any]:
    return {
        "item_id": query_row.get("item_id", ""),
        "risk_type": "image_duplicate",
        "confidence": round(score, 6),
        "evidence": {
            "type": "clip_image_to_item_similarity",
            "field": "image_similarity",
            "query_image": query_row.get("image_path", ""),
            "query_image_id": query_row.get("image_id", ""),
            "matched_item_id": hit_row.get("item_id", ""),
            "matched_image_id": hit_row.get("image_id", ""),
            "matched_image": hit_row.get("image_path", ""),
            "matched_image_path": hit_row.get("image_path", ""),
            "matched_image_role": hit_row.get("image_role", ""),
            "rank": rank,
            "score": round(score, 6),
            "rule": f"{model_name}_image_embedding_cosine",
            "snippet": (
                f"{query_row.get('image_path', '')} similar to "
                f"{hit_row.get('item_id', '')}:{hit_row.get('image_role', '')}:{hit_row.get('image_path', '')}"
            ),
        },
        "suggested_action": "merge_duplicate",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CLIP/SigLIP image-to-item retrieval.")
    parser.add_argument("--embeddings", default="outputs/embeddings/clip_image_embeddings.npz", help="Embedding NPZ.")
    parser.add_argument(
        "--manifest",
        default="outputs/embeddings/clip_image_embeddings_manifest.csv",
        help="Embedding manifest CSV.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Candidate item hits per query image.")
    parser.add_argument("--min-score", type=float, default=0.0, help="Evidence threshold.")
    parser.add_argument("--results", default="outputs/retrieval_results/clip_image_similarity.csv", help="CSV result output.")
    parser.add_argument("--output", default="outputs/evidence/clip_image_similarity_evidence.jsonl", help="Evidence JSONL output.")
    args = parser.parse_args()

    try:
        data = np.load(args.embeddings)
        embeddings = data["embeddings"].astype(np.float32)
        model_name = str(data.get("model_name", np.array(["clip"]))[0])
        rows = read_manifest(Path(args.manifest))
        if len(rows) != embeddings.shape[0]:
            raise ValueError(f"manifest rows ({len(rows)}) != embeddings rows ({embeddings.shape[0]})")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    scores = embeddings @ embeddings.T
    result_rows: list[dict[str, Any]] = []
    evidence_records: list[dict[str, Any]] = []

    for query_idx, query_row in enumerate(rows):
        ranked_indices = sorted(range(len(rows)), key=lambda idx: (-float(scores[query_idx, idx]), rows[idx].get("item_id", "")))
        seen_items: set[str] = set()
        rank = 0
        for idx in ranked_indices:
            hit_row = rows[idx]
            if idx == query_idx:
                continue
            if hit_row.get("item_id", "") == query_row.get("item_id", ""):
                continue
            if hit_row.get("item_id", "") in seen_items:
                continue
            seen_items.add(hit_row.get("item_id", ""))
            rank += 1
            score = float(scores[query_idx, idx])
            kept = score >= args.min_score
            result_rows.append(
                {
                    "query_item_id": query_row.get("item_id", ""),
                    "query_image_id": query_row.get("image_id", ""),
                    "query_image": query_row.get("image_path", ""),
                    "query_image_role": query_row.get("image_role", ""),
                    "matched_item_id": hit_row.get("item_id", ""),
                    "matched_image_id": hit_row.get("image_id", ""),
                    "matched_image": hit_row.get("image_path", ""),
                    "matched_image_role": hit_row.get("image_role", ""),
                    "rank": rank,
                    "score": round(score, 6),
                    "kept": int(kept),
                }
            )
            if kept:
                evidence_records.append(to_evidence(query_row, hit_row, score, rank, model_name))
            if rank >= args.top_k:
                break

    write_csv(Path(args.results), result_rows)
    write_jsonl(Path(args.output), evidence_records)

    print(f"Embeddings loaded: {embeddings.shape[0]}")
    print(f"Embedding dim: {embeddings.shape[1]}")
    print(f"Model: {model_name}")
    print(f"Candidate rows: {len(result_rows)}")
    print(f"Evidence records: {len(evidence_records)}")
    print(f"Results output: {args.results}")
    print(f"Evidence output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
