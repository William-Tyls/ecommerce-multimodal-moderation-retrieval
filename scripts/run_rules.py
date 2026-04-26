#!/usr/bin/env python3
"""Run rule-based moderation checks and write evidence records."""

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
        raise RuntimeError("PyYAML is required for rule detection. Install with `pip install pyyaml`.") from exc

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return data


def read_items(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"items file has no header: {path}")
        return [dict(row) for row in reader]


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
    fieldnames = [
        "item_id",
        "risk_types",
        "evidence_count",
        "matched_fields",
        "suggested_actions",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rule-based moderation checks.")
    parser.add_argument("--items", default="data/items.csv", help="Path to item metadata CSV.")
    parser.add_argument("--rules", default="configs/rules.yaml", help="Path to rules YAML.")
    parser.add_argument("--risk-labels", default="configs/risk_labels.yaml", help="Path to risk labels YAML.")
    parser.add_argument("--output", default="outputs/evidence/rule_evidence.jsonl", help="Evidence JSONL output path.")
    parser.add_argument("--summary", default="outputs/evidence/rule_summary.csv", help="Item-level summary CSV path.")
    args = parser.parse_args()

    items_path = Path(args.items)
    rules_path = Path(args.rules)
    risk_labels_path = Path(args.risk_labels)
    output_path = Path(args.output)
    summary_path = Path(args.summary)

    try:
        items = read_items(items_path)
        rules_config = load_yaml(rules_path)
        risk_labels_config = load_yaml(risk_labels_path)

        rule_groups = rules_config.get("rule_groups", {})
        if not isinstance(rule_groups, dict) or not rule_groups:
            raise ValueError("rules config must contain a non-empty `rule_groups` mapping")

        default_actions = get_default_actions(risk_labels_config)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    evidence_records: list[dict[str, Any]] = []
    summary_by_item: dict[str, dict[str, set[str] | int]] = {}
    match_counter: Counter[str] = Counter()
    field_counter: Counter[str] = Counter()

    for item in items:
        matches = match_item(item, rule_groups)
        for match in matches:
            suggested_action = default_actions.get(match.risk_type, "manual_review")
            record = match.to_evidence(suggested_action=suggested_action)
            evidence_records.append(record)
            match_counter[match.risk_type] += 1
            field_counter[match.field] += 1

            item_summary = summary_by_item.setdefault(
                match.item_id,
                {
                    "risk_types": set(),
                    "matched_fields": set(),
                    "suggested_actions": set(),
                    "evidence_count": 0,
                },
            )
            item_summary["risk_types"].add(match.risk_type)  # type: ignore[union-attr]
            item_summary["matched_fields"].add(match.field)  # type: ignore[union-attr]
            item_summary["suggested_actions"].add(suggested_action)  # type: ignore[union-attr]
            item_summary["evidence_count"] = int(item_summary["evidence_count"]) + 1

    summary_rows: list[dict[str, Any]] = []
    for item_id, summary in sorted(summary_by_item.items()):
        summary_rows.append(
            {
                "item_id": item_id,
                "risk_types": "|".join(sorted(summary["risk_types"])),  # type: ignore[arg-type]
                "evidence_count": summary["evidence_count"],
                "matched_fields": "|".join(sorted(summary["matched_fields"])),  # type: ignore[arg-type]
                "suggested_actions": "|".join(sorted(summary["suggested_actions"])),  # type: ignore[arg-type]
            }
        )

    write_jsonl(output_path, evidence_records)
    write_summary_csv(summary_path, summary_rows)

    print(f"Items scanned: {len(items)}")
    print(f"Evidence records: {len(evidence_records)}")
    print(f"Items with evidence: {len(summary_rows)}")
    print(f"Evidence output: {output_path}")
    print(f"Summary output: {summary_path}")

    print("\nMatches by risk type")
    if match_counter:
        for risk_type, count in match_counter.most_common():
            print(f"  {risk_type}: {count}")
    else:
        print("  (none)")

    print("\nMatches by field")
    if field_counter:
        for field, count in field_counter.most_common():
            print(f"  {field}: {count}")
    else:
        print("  (none)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
