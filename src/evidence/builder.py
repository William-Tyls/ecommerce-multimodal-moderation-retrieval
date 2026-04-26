"""Build item-level audit cases from evidence records."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


ACTION_PRIORITY = {
    "pass": 0,
    "merge_duplicate": 1,
    "manual_review": 2,
    "remove_or_block": 3,
}

FIELD_WEIGHTS = {
    "title": 0.18,
    "description": 0.14,
    "ocr_text": 0.22,
    "image": 0.25,
    "image_similarity": 0.25,
    "vlm_tag": 0.2,
}

RISK_WEIGHTS = {
    "prohibited_goods": 0.36,
    "counterfeit_brand": 0.30,
    "image_duplicate": 0.32,
    "off_platform_contact": 0.34,
    "misleading_claim": 0.24,
}


def split_multi_value(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


def normalize_item(item: dict[str, str]) -> dict[str, Any]:
    return {
        "item_id": item.get("item_id", ""),
        "title": item.get("title", ""),
        "description": item.get("description", ""),
        "category": item.get("category", ""),
        "shop_id": item.get("shop_id", ""),
        "image_paths": split_multi_value(item.get("image_paths", "")),
        "ocr_text": split_multi_value(item.get("ocr_text", "")),
        "risk_labels": split_multi_value(item.get("risk_labels", "")),
        "risk_objects": split_multi_value(item.get("risk_objects", "")),
        "source": item.get("source", ""),
        "split": item.get("split", ""),
    }


def choose_action(actions: Iterable[str]) -> str:
    best = "pass"
    best_priority = ACTION_PRIORITY[best]
    for action in actions:
        priority = ACTION_PRIORITY.get(action, 1)
        if priority > best_priority:
            best = action
            best_priority = priority
    return best


def evidence_field(record: dict[str, Any]) -> str:
    evidence = record.get("evidence", {})
    if isinstance(evidence, dict):
        field = evidence.get("field")
        if isinstance(field, str) and field:
            return field
        evidence_type = evidence.get("type")
        if isinstance(evidence_type, str):
            if evidence_type.startswith("image_similarity"):
                return "image_similarity"
            if evidence_type.startswith("vlm"):
                return "vlm_tag"
    return "unknown"


def score_risk(risk_type: str, records: list[dict[str, Any]]) -> float:
    if not records:
        return 0.0

    base = RISK_WEIGHTS.get(risk_type, 0.22)
    fields = {evidence_field(record) for record in records}
    field_score = sum(FIELD_WEIGHTS.get(field, 0.08) for field in fields)
    evidence_bonus = min(len(records) * 0.08, 0.32)
    confidence_bonus = min(
        sum(float(record.get("confidence", 0.0)) for record in records) / max(len(records), 1) * 0.12,
        0.12,
    )

    return round(min(base + field_score + evidence_bonus + confidence_bonus, 1.0), 4)


def build_risk_assessments(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_risk: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        risk_type = str(record.get("risk_type", "unknown"))
        by_risk.setdefault(risk_type, []).append(record)

    assessments: list[dict[str, Any]] = []
    for risk_type, risk_records in sorted(by_risk.items()):
        actions = [str(record.get("suggested_action", "manual_review")) for record in risk_records]
        fields = sorted({evidence_field(record) for record in risk_records})
        assessments.append(
            {
                "risk_type": risk_type,
                "risk_score": score_risk(risk_type, risk_records),
                "evidence_count": len(risk_records),
                "matched_fields": fields,
                "suggested_action": choose_action(actions),
                "evidence": [record.get("evidence", {}) for record in risk_records],
            }
        )

    assessments.sort(key=lambda item: (-float(item["risk_score"]), str(item["risk_type"])))
    return assessments


def build_audit_case(item: dict[str, str], records: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_item = normalize_item(item)
    risk_assessments = build_risk_assessments(records)
    actions = [assessment["suggested_action"] for assessment in risk_assessments]
    risk_types = [assessment["risk_type"] for assessment in risk_assessments]
    risk_score = max([float(assessment["risk_score"]) for assessment in risk_assessments], default=0.0)

    if not risk_assessments:
        action = "pass"
        status = "no_evidence"
    else:
        action = choose_action(actions)
        status = "risk_detected"

    return {
        "item_id": normalized_item["item_id"],
        "item": normalized_item,
        "status": status,
        "risk_score": round(risk_score, 4),
        "risk_types": risk_types,
        "evidence_count": sum(int(assessment["evidence_count"]) for assessment in risk_assessments),
        "suggested_action": action,
        "risk_assessments": risk_assessments,
    }


def summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    risk_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()

    for case in cases:
        action_counter[str(case.get("suggested_action", "unknown"))] += 1
        status_counter[str(case.get("status", "unknown"))] += 1
        for risk_type in case.get("risk_types", []):
            risk_counter[str(risk_type)] += 1

    return {
        "risk_types": risk_counter,
        "actions": action_counter,
        "status": status_counter,
    }
