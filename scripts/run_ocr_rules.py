#!/usr/bin/env python3
"""Run moderation rules over OCR JSONL output and write evidence records."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rules.engine import match_item  # noqa: E402


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("PyYAML is required. Install with `pip install pyyaml`.") from exc

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return data


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"JSONL record must be an object at {path}:{line_number}")
            records.append(record)
    return records


def get_default_actions(risk_labels_config: dict[str, Any]) -> dict[str, str]:
    actions: dict[str, str] = {}
    labels = risk_labels_config.get("risk_labels", {})
    if not isinstance(labels, dict):
        return actions
    for risk_type, config in labels.items():
        if isinstance(config, dict):
            actions[str(risk_type)] = str(config.get("default_action", "manual_review"))
    return actions


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["item_id", "image_id", "risk_types", "evidence_count", "matched_texts"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rules over image-level OCR output.")
    parser.add_argument("--ocr", default="outputs/ocr/item_ocr.jsonl", help="OCR JSONL input path.")
    parser.add_argument("--rules", default="configs/rules.yaml", help="Rules YAML path.")
    parser.add_argument("--risk-labels", default="configs/risk_labels.yaml", help="Risk labels YAML path.")
    parser.add_argument("--output", default="outputs/evidence/ocr_rule_evidence.jsonl", help="Evidence JSONL output path.")
    parser.add_argument("--summary", default="outputs/evidence/ocr_rule_summary.csv", help="Summary CSV output path.")
    args = parser.parse_args()

    try:
        ocr_records = read_jsonl(Path(args.ocr))
        rules_config = load_yaml(Path(args.rules))
        risk_labels_config = load_yaml(Path(args.risk_labels))
        rule_groups = rules_config.get("rule_groups", {})
        if not isinstance(rule_groups, dict) or not rule_groups:
            raise ValueError("rules config must contain a non-empty `rule_groups` mapping")
        default_actions = get_default_actions(risk_labels_config)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    evidence_records: list[dict[str, Any]] = []
    summary: dict[tuple[str, str], dict[str, Any]] = {}
    risk_counter: Counter[str] = Counter()

    for ocr_record in ocr_records:
        text = str(ocr_record.get("ocr_text", "")).strip()
        if not text:
            continue
        item = {
            "item_id": str(ocr_record.get("item_id", "")),
            "title": "",
            "description": "",
            "ocr_text": text,
        }
        for match in match_item(item, rule_groups):
            suggested_action = default_actions.get(match.risk_type, "manual_review")
            record = match.to_evidence(suggested_action=suggested_action)
            evidence = record.get("evidence", {})
            if isinstance(evidence, dict):
                evidence["type"] = evidence.get("type", "ocr_text_match")
                evidence["field"] = "ocr_text"
                evidence["image_id"] = ocr_record.get("image_id", "")
                evidence["image_path"] = ocr_record.get("image_path", "")
                evidence["image_role"] = ocr_record.get("image_role", "")
                evidence["ocr_backend"] = ocr_record.get("backend", "")
                evidence["ocr_source"] = ocr_record.get("source", "")
            record["confidence"] = min(float(record.get("confidence", 1.0)), float(ocr_record.get("confidence", 1.0)))
            evidence_records.append(record)
            risk_counter[match.risk_type] += 1

            key = (str(ocr_record.get("item_id", "")), str(ocr_record.get("image_id", "")))
            row = summary.setdefault(
                key,
                {
                    "item_id": key[0],
                    "image_id": key[1],
                    "risk_types": set(),
                    "matched_texts": set(),
                    "evidence_count": 0,
                },
            )
            row["risk_types"].add(match.risk_type)
            row["matched_texts"].add(match.matched_text)
            row["evidence_count"] += 1

    summary_rows = [
        {
            "item_id": row["item_id"],
            "image_id": row["image_id"],
            "risk_types": "|".join(sorted(row["risk_types"])),
            "evidence_count": row["evidence_count"],
            "matched_texts": "|".join(sorted(row["matched_texts"])),
        }
        for row in sorted(summary.values(), key=lambda value: (value["item_id"], value["image_id"]))
    ]

    write_jsonl(Path(args.output), evidence_records)
    write_summary_csv(Path(args.summary), summary_rows)

    print(f"OCR records loaded: {len(ocr_records)}")
    print(f"OCR evidence records: {len(evidence_records)}")
    print(f"Images with evidence: {len(summary_rows)}")
    print(f"Evidence output: {args.output}")
    print(f"Summary output: {args.summary}")
    print("\nMatches by risk type")
    if risk_counter:
        for risk_type, count in risk_counter.most_common():
            print(f"  {risk_type}: {count}")
    else:
        print("  (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
