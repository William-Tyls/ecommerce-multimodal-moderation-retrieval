"""Image-to-item retrieval helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from src.models.image_encoder import SimpleImageEncoder


def split_multi_value(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


@dataclass(frozen=True)
class ImageRecord:
    image_id: str
    item_id: str
    image_path: str
    image_role: str
    image_index: int


@dataclass(frozen=True)
class ImageHit:
    image_id: str
    item_id: str
    image_path: str
    image_role: str
    score: float
    rank: int

    def to_evidence(self, query_image: str, query_item_id: str | None = None) -> dict[str, Any]:
        evidence_item_id = query_item_id or self.item_id
        return {
            "item_id": evidence_item_id,
            "risk_type": "image_duplicate",
            "confidence": round(self.score, 6),
            "evidence": {
                "type": "image_to_item_similarity",
                "field": "image_similarity",
                "query_image": query_image,
                "matched_item_id": self.item_id,
                "matched_image_id": self.image_id,
                "matched_image": self.image_path,
                "matched_image_path": self.image_path,
                "matched_image_role": self.image_role,
                "rank": self.rank,
                "score": round(self.score, 6),
                "rule": "simple_image_embedding_cosine",
                "snippet": f"{query_image} similar to {self.item_id}:{self.image_role}:{self.image_path}",
            },
            "suggested_action": "merge_duplicate",
        }


def infer_image_role(image_path: str, image_index: int) -> str:
    stem = Path(image_path).stem.lower()
    if image_index == 0:
        return "main"
    if "main" in stem:
        return "main"
    if "detail" in stem:
        return f"detail_{image_index}"
    if "package" in stem or "packaging" in stem:
        return "package"
    if "ocr" in stem or "text" in stem:
        return "text_or_ocr"
    return f"detail_{image_index}"


def image_id_for(item_id: str, image_role: str, image_index: int) -> str:
    if image_role == "main":
        return f"{item_id}_img_main"
    return f"{item_id}_img_{image_index:02d}_{image_role}"


def iter_image_records(items: list[dict[str, str]]) -> list[ImageRecord]:
    records: list[ImageRecord] = []
    for item in items:
        item_id = item.get("item_id", "").strip()
        if not item_id:
            continue
        for image_index, image_path in enumerate(split_multi_value(item.get("image_paths", ""))):
            image_role = infer_image_role(image_path, image_index)
            records.append(
                ImageRecord(
                    image_id=image_id_for(item_id, image_role, image_index),
                    item_id=item_id,
                    image_path=image_path,
                    image_role=image_role,
                    image_index=image_index,
                )
            )
    return records


class ImageItemRetriever:
    def __init__(self, items: list[dict[str, str]], encoder: SimpleImageEncoder | None = None) -> None:
        self.items = items
        self.encoder = encoder or SimpleImageEncoder()
        self.records: list[ImageRecord] = []
        vectors: list[np.ndarray] = []

        for record in iter_image_records(items):
            if not Path(record.image_path).exists():
                continue
            self.records.append(record)
            vectors.append(self.encoder.encode_path(record.image_path))

        if vectors:
            self.matrix = np.vstack(vectors)
        else:
            self.matrix = np.empty((0, 0), dtype=np.float32)

    def search(self, query_image: str, top_k: int = 5, exclude_item_id: str | None = None) -> list[ImageHit]:
        if self.matrix.size == 0:
            return []

        query_vector = self.encoder.encode_path(query_image)
        scores = self.matrix @ query_vector
        ranked_indices = sorted(range(len(scores)), key=lambda idx: (-float(scores[idx]), self.records[idx].item_id))

        hits: list[ImageHit] = []
        seen_items: set[str] = set()
        for idx in ranked_indices:
            record = self.records[idx]
            if exclude_item_id and record.item_id == exclude_item_id:
                continue
            if record.item_id in seen_items:
                continue
            seen_items.add(record.item_id)
            hits.append(
                ImageHit(
                    image_id=record.image_id,
                    item_id=record.item_id,
                    image_path=record.image_path,
                    image_role=record.image_role,
                    score=float(scores[idx]),
                    rank=len(hits) + 1,
                )
            )
            if len(hits) >= top_k:
                break
        return hits
