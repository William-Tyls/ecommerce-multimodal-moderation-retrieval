#!/usr/bin/env python3
"""Validate item metadata for the moderation retrieval project."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = [
    "item_id",
    "title",
    "description",
    "category",
    "shop_id",
    "image_paths",
    "ocr_text",
    "risk_labels",
    "risk_objects",
    "source",
    "split",
]

VALID_SPLITS = {"train", "val", "test"}


def load_yaml_light(path: Path) -> dict[str, Any]:
    """Load a small YAML file, using PyYAML when available.

    The project only needs `risk_labels` keys for this validator. If PyYAML is
    unavailable, fall back to a tiny parser for the current config shape.
    """
    try:
        import yaml  # type: ignore

        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
        if not isinstance(data, dict):
            raise ValueError("risk label config must be a mapping")
        return data
    except ModuleNotFoundError:
        labels: dict[str, dict[str, Any]] = {}
        in_risk_labels = False
        label_pattern = re.compile(r"^  ([A-Za-z0-9_]+):\s*$")
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if line.startswith("risk_labels:"):
                    in_risk_labels = True
                    continue
                if line.startswith("actions:"):
                    in_risk_labels = False
                if in_risk_labels:
                    match = label_pattern.match(line)
                    if match:
                        labels[match.group(1)] = {}
        return {"risk_labels": labels}


def split_multi_value(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


def read_items(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError("items file has no header")

        missing_columns = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
        if missing_columns:
            raise ValueError(f"missing required columns: {', '.join(missing_columns)}")

        return [dict(row) for row in reader]


def validate_items(items: list[dict[str, str]], valid_labels: set[str]) -> tuple[list[str], dict[str, Counter[str]]]:
    errors: list[str] = []
    stats = {
        "risk_labels": Counter(),
        "split": Counter(),
        "category": Counter(),
        "source": Counter(),
    }

    seen_ids: set[str] = set()

    for row_number, item in enumerate(items, start=2):
        item_id = item.get("item_id", "").strip()
        if not item_id:
            errors.append(f"row {row_number}: item_id is empty")
        elif item_id in seen_ids:
            errors.append(f"row {row_number}: duplicate item_id '{item_id}'")
        seen_ids.add(item_id)

        split = item.get("split", "").strip()
        if split not in VALID_SPLITS:
            errors.append(f"row {row_number}: invalid split '{split}', expected one of {sorted(VALID_SPLITS)}")
        else:
            stats["split"][split] += 1

        labels = split_multi_value(item.get("risk_labels", ""))
        if not labels:
            errors.append(f"row {row_number}: risk_labels is empty")

        for label in labels:
            if label not in valid_labels:
                errors.append(f"row {row_number}: unknown risk label '{label}'")
            stats["risk_labels"][label] += 1

        image_paths = split_multi_value(item.get("image_paths", ""))
        if not image_paths:
            errors.append(f"row {row_number}: image_paths is empty")

        category = item.get("category", "").strip()
        source = item.get("source", "").strip()
        if category:
            stats["category"][category] += 1
        if source:
            stats["source"][source] += 1

        if "normal" in labels and len(labels) > 1:
            errors.append(f"row {row_number}: 'normal' cannot be combined with other risk labels")

    return errors, stats


def print_counter(title: str, counter: Counter[str]) -> None:
    print(f"\n{title}")
    if not counter:
        print("  (none)")
        return
    for key, value in counter.most_common():
        print(f"  {key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate e-commerce moderation item metadata.")
    parser.add_argument("--items", default="data/items.csv", help="Path to items CSV metadata.")
    parser.add_argument("--risk-labels", default="configs/risk_labels.yaml", help="Path to risk labels YAML.")
    args = parser.parse_args()

    items_path = Path(args.items)
    risk_labels_path = Path(args.risk_labels)

    if not items_path.exists():
        print(f"ERROR: items file not found: {items_path}", file=sys.stderr)
        return 2
    if not risk_labels_path.exists():
        print(f"ERROR: risk labels file not found: {risk_labels_path}", file=sys.stderr)
        return 2

    try:
        label_config = load_yaml_light(risk_labels_path)
        valid_labels = set(label_config.get("risk_labels", {}).keys())
        if not valid_labels:
            raise ValueError("no risk labels found in config")

        items = read_items(items_path)
        errors, stats = validate_items(items, valid_labels)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Items file: {items_path}")
    print(f"Total items: {len(items)}")
    print(f"Valid risk labels: {', '.join(sorted(valid_labels))}")

    print_counter("Split distribution", stats["split"])
    print_counter("Risk label distribution", stats["risk_labels"])
    print_counter("Category distribution", stats["category"])
    print_counter("Source distribution", stats["source"])

    if errors:
        print("\nValidation errors")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("\nValidation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
