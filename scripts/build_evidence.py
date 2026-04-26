#!/usr/bin/env python3
"""Aggregate evidence records into item-level audit cases."""

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

from src.evidence.builder import build_audit_case, summarize_cases  # noqa: E402


def read_items(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise ValueError(f"items file has no header: {path}")
        return [dict(row) for row in reader]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
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


def group_records_by_item(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        item_id = str(record.get("item_id", "")).strip()
        if not item_id:
            continue
        grouped.setdefault(item_id, []).append(record)
    return grouped


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_cases_csv(path: Path, cases: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "item_id",
        "status",
        "risk_score",
        "risk_types",
        "evidence_count",
        "suggested_action",
        "title",
        "category",
        "shop_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            item = case.get("item", {})
            writer.writerow(
                {
                    "item_id": case.get("item_id", ""),
                    "status": case.get("status", ""),
                    "risk_score": case.get("risk_score", 0.0),
                    "risk_types": "|".join(case.get("risk_types", [])),
                    "evidence_count": case.get("evidence_count", 0),
                    "suggested_action": case.get("suggested_action", ""),
                    "title": item.get("title", ""),
                    "category": item.get("category", ""),
                    "shop_id": item.get("shop_id", ""),
                }
            )


def print_counter(title: str, counter: Any) -> None:
    print(f"\n{title}")
    if not counter:
        print("  (none)")
        return
    for key, count in counter.most_common():
        print(f"  {key}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build item-level audit cases from evidence records.")
    parser.add_argument("--items", default="data/items.csv", help="Path to item metadata CSV.")
    parser.add_argument(
        "--evidence",
        action="append",
        default=None,
        help="Evidence JSONL path. Can be passed multiple times.",
    )
    parser.add_argument("--output", default="outputs/evidence/audit_cases.jsonl", help="Audit cases JSONL output path.")
    parser.add_argument("--summary", default="outputs/evidence/audit_cases.csv", help="Audit cases CSV summary path.")
    parser.add_argument(
        "--include-clean",
        action="store_true",
        help="Include items without evidence as pass/no_evidence cases.",
    )
    args = parser.parse_args()

    try:
        items = read_items(Path(args.items))
        evidence_records: list[dict[str, Any]] = []
        evidence_paths = args.evidence or ["outputs/evidence/rule_evidence.jsonl"]
        for evidence_path in evidence_paths:
            evidence_records.extend(read_jsonl(Path(evidence_path)))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    grouped_records = group_records_by_item(evidence_records)
    cases: list[dict[str, Any]] = []

    for item in items:
        item_id = item.get("item_id", "").strip()
        records = grouped_records.get(item_id, [])
        if records or args.include_clean:
            cases.append(build_audit_case(item, records))

    cases.sort(key=lambda case: (-float(case.get("risk_score", 0.0)), str(case.get("item_id", ""))))

    write_jsonl(Path(args.output), cases)
    write_cases_csv(Path(args.summary), cases)

    summary = summarize_cases(cases)

    print(f"Items loaded: {len(items)}")
    print(f"Evidence records loaded: {len(evidence_records)}")
    print(f"Audit cases written: {len(cases)}")
    print(f"Audit cases output: {args.output}")
    print(f"Summary output: {args.summary}")

    print_counter("Cases by status", summary["status"])
    print_counter("Cases by suggested action", summary["actions"])
    print_counter("Cases by risk type", summary["risk_types"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
