#!/usr/bin/env python3
"""Build an image-level manifest from item metadata."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


FIELDNAMES = [
    "image_id",
    "item_id",
    "image_index",
    "image_role",
    "image_path",
    "is_primary",
    "title",
    "category",
    "shop_id",
    "risk_labels",
    "risk_objects",
    "source",
    "split",
]


def split_multi_value(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


def read_items(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"items file has no header: {path}")
        return [dict(row) for row in reader]


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


def build_manifest_rows(items: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        item_id = item.get("item_id", "").strip()
        if not item_id:
            continue
        for image_index, image_path in enumerate(split_multi_value(item.get("image_paths", ""))):
            image_role = infer_image_role(image_path, image_index)
            rows.append(
                {
                    "image_id": image_id_for(item_id, image_role, image_index),
                    "item_id": item_id,
                    "image_index": str(image_index),
                    "image_role": image_role,
                    "image_path": image_path,
                    "is_primary": "1" if image_index == 0 else "0",
                    "title": item.get("title", ""),
                    "category": item.get("category", ""),
                    "shop_id": item.get("shop_id", ""),
                    "risk_labels": item.get("risk_labels", ""),
                    "risk_objects": item.get("risk_objects", ""),
                    "source": item.get("source", ""),
                    "split": item.get("split", ""),
                }
            )
    return rows


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an image-level manifest from item metadata.")
    parser.add_argument("--items", default="data/items.csv", help="Path to item metadata CSV.")
    parser.add_argument("--output", default="data/image_manifest.csv", help="Output image manifest CSV.")
    args = parser.parse_args()

    try:
        items = read_items(Path(args.items))
        rows = build_manifest_rows(items)
        write_manifest(Path(args.output), rows)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    primary_count = sum(1 for row in rows if row["is_primary"] == "1")
    print(f"Items loaded: {len(items)}")
    print(f"Image rows written: {len(rows)}")
    print(f"Primary images: {primary_count}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
