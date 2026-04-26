#!/usr/bin/env python3
"""Run OCR over item images and write image-level OCR records."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ocr.backends import build_ocr_backend  # noqa: E402
from src.retrieval.image_search import iter_image_records, split_multi_value  # noqa: E402


def read_items(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"items file has no header: {path}")
        return [dict(row) for row in reader]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def fallback_text_for_image(item: dict[str, str], image_index: int) -> str:
    parts = split_multi_value(item.get("ocr_text", ""))
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if image_index < len(parts):
        return parts[image_index]
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local OCR over item images.")
    parser.add_argument("--items", default="data/items.csv", help="Path to item metadata CSV.")
    parser.add_argument("--output", default="outputs/ocr/item_ocr.jsonl", help="OCR JSONL output path.")
    parser.add_argument(
        "--backend",
        choices=["auto", "metadata", "tesseract"],
        default="auto",
        help="OCR backend. auto tries tesseract and falls back to metadata ocr_text.",
    )
    parser.add_argument("--languages", default="eng+chi_sim", help="Tesseract language list.")
    args = parser.parse_args()

    try:
        items = read_items(Path(args.items))
        items_by_id = {item.get("item_id", ""): item for item in items}
        backend = build_ocr_backend(args.backend, languages=args.languages)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    records: list[dict[str, Any]] = []
    missing_images = 0
    records_with_text = 0

    for image_record in iter_image_records(items):
        item = items_by_id.get(image_record.item_id, {})
        fallback_text = fallback_text_for_image(item, image_record.image_index)
        image_exists = Path(image_record.image_path).exists()
        if not image_exists:
            missing_images += 1
        result = backend.extract_text(image_record.image_path, fallback_text=fallback_text)
        text = result.text.strip()
        if text:
            records_with_text += 1
        records.append(
            {
                "item_id": image_record.item_id,
                "image_id": image_record.image_id,
                "image_index": image_record.image_index,
                "image_role": image_record.image_role,
                "image_path": image_record.image_path,
                "image_exists": int(image_exists),
                "ocr_text": text,
                "backend": result.backend,
                "source": result.source,
                "confidence": round(result.confidence, 6),
            }
        )

    write_jsonl(Path(args.output), records)

    print(f"Items loaded: {len(items)}")
    print(f"OCR backend: {backend.name}")
    print(f"OCR records written: {len(records)}")
    print(f"Records with text: {records_with_text}")
    print(f"Missing images: {missing_images}")
    print(f"OCR output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
