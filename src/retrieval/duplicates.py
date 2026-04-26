"""Exact duplicate image-path detection for item metadata."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def split_multi_value(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


def build_image_index(items: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    image_index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in items:
        item_id = item.get("item_id", "").strip()
        if not item_id:
            continue
        for image_path in split_multi_value(item.get("image_paths", "")):
            image_index[image_path].append(item)
    return dict(image_index)


def find_exact_duplicate_groups(items: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    image_index = build_image_index(items)
    return {image_path: group for image_path, group in image_index.items() if len(group) > 1}


def make_duplicate_evidence(items: list[dict[str, str]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    duplicate_groups = find_exact_duplicate_groups(items)

    for image_path, group in sorted(duplicate_groups.items()):
        group_item_ids = sorted(item.get("item_id", "").strip() for item in group if item.get("item_id", "").strip())
        group_shops = sorted(item.get("shop_id", "").strip() for item in group if item.get("shop_id", "").strip())

        for item in group:
            item_id = item.get("item_id", "").strip()
            if not item_id:
                continue
            matched_item_ids = [other_id for other_id in group_item_ids if other_id != item_id]
            records.append(
                {
                    "item_id": item_id,
                    "risk_type": "image_duplicate",
                    "confidence": 1.0,
                    "evidence": {
                        "type": "image_duplicate_exact_path",
                        "field": "image",
                        "image_path": image_path,
                        "matched_item_ids": matched_item_ids,
                        "matched_shop_ids": group_shops,
                        "duplicate_group_size": len(group_item_ids),
                        "rule": "exact_same_image_path",
                        "snippet": f"{image_path} shared by {len(group_item_ids)} items",
                    },
                    "suggested_action": "merge_duplicate",
                }
            )

    return records
