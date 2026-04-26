#!/usr/bin/env python3
"""Run VLM image understanding and write moderation evidence records."""

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

from src.vlm.qwen_vl import MetadataVLMAnalyzer, QwenVLAnalyzer, VLMResult  # noqa: E402


def split_multi_value(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


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


def iter_image_records(items: list[dict[str, str]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in items:
        item_id = item.get("item_id", "").strip()
        if not item_id:
            continue
        for image_index, image_path in enumerate(split_multi_value(item.get("image_paths", ""))):
            image_role = infer_image_role(image_path, image_index)
            records.append(
                {
                    "image_id": image_id_for(item_id, image_role, image_index),
                    "item_id": item_id,
                    "image_path": image_path,
                    "image_role": image_role,
                    "image_index": image_index,
                }
            )
    return records


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


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["item_id", "image_id", "image_path", "risk_types", "evidence_count", "model"]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def get_default_actions(risk_labels_config: dict[str, Any]) -> dict[str, str]:
    actions: dict[str, str] = {}
    labels = risk_labels_config.get("risk_labels", {})
    if not isinstance(labels, dict):
        return actions
    for risk_type, config in labels.items():
        if isinstance(config, dict):
            actions[str(risk_type)] = str(config.get("default_action", "manual_review"))
    return actions


def render_prompt(template: str, item: dict[str, str]) -> str:
    values = {
        "title": item.get("title", ""),
        "description": item.get("description", ""),
        "category": item.get("category", ""),
        "shop_id": item.get("shop_id", ""),
    }
    return template.format(**values)


def result_to_evidence(
    result: VLMResult,
    item_id: str,
    image_id: str,
    image_path: str,
    image_role: str,
    prompt_id: str,
    default_actions: dict[str, str],
    include_raw: bool,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for assessment in result.risk_assessments:
        evidence: dict[str, Any] = {
            "type": "vlm_visual_risk",
            "field": "image",
            "image_id": image_id,
            "image_path": image_path,
            "image_role": image_role,
            "caption": result.caption,
            "ocr_like_text": result.ocr_like_text,
            "risk_objects": assessment.risk_objects,
            "evidence_reason": assessment.evidence_reason,
            "bbox": assessment.bbox,
            "model": result.model_name,
            "prompt_id": prompt_id,
            "snippet": assessment.evidence_reason or result.caption,
        }
        if include_raw:
            evidence["raw_response"] = result.raw_response
        records.append(
            {
                "item_id": item_id,
                "risk_type": assessment.risk_type,
                "confidence": assessment.confidence,
                "evidence": evidence,
                "suggested_action": default_actions.get(assessment.risk_type, "manual_review"),
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Qwen2.5-VL-style image understanding evidence.")
    parser.add_argument("--items", default="data/items.csv", help="Path to item metadata CSV.")
    parser.add_argument("--prompts", default="configs/vlm_prompts.yaml", help="VLM prompt config YAML.")
    parser.add_argument("--risk-labels", default="configs/risk_labels.yaml", help="Risk labels YAML.")
    parser.add_argument("--prompt-id", default="ecommerce_visual_risk", help="Prompt ID in configs/vlm_prompts.yaml.")
    parser.add_argument("--backend", choices=["metadata", "qwen_vl"], default="qwen_vl", help="VLM backend.")
    parser.add_argument("--model-name", help="Override model name from prompt config.")
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, cuda:0, or mps.")
    parser.add_argument("--max-new-tokens", type=int, help="Override generation length.")
    parser.add_argument("--limit", type=int, help="Limit number of image records.")
    parser.add_argument("--include-missing", action="store_true", help="Run backend even when image files are missing.")
    parser.add_argument("--include-raw", action="store_true", help="Include raw VLM response in evidence JSONL.")
    parser.add_argument("--local-files-only", action="store_true", help="Do not download model files.")
    parser.add_argument("--output", default="outputs/evidence/vlm_evidence.jsonl", help="Evidence JSONL output path.")
    parser.add_argument("--summary", default="outputs/evidence/vlm_summary.csv", help="Summary CSV output path.")
    args = parser.parse_args()

    try:
        items = read_items(Path(args.items))
        items_by_id = {item.get("item_id", ""): item for item in items}
        prompt_config = load_yaml(Path(args.prompts))
        risk_labels_config = load_yaml(Path(args.risk_labels))
        default_actions = get_default_actions(risk_labels_config)

        prompts = prompt_config.get("prompts", {})
        prompt_entry = prompts.get(args.prompt_id, {}) if isinstance(prompts, dict) else {}
        prompt_template = prompt_entry.get("text", "") if isinstance(prompt_entry, dict) else ""
        if not isinstance(prompt_template, str) or not prompt_template.strip():
            raise ValueError(f"prompt not found or empty: {args.prompt_id}")

        model_config = prompt_config.get("model", {})
        model_name = args.model_name or str(model_config.get("name", "Qwen/Qwen2.5-VL-3B-Instruct"))
        max_new_tokens = args.max_new_tokens or int(model_config.get("max_new_tokens", 512))

        if args.backend == "metadata":
            analyzer = MetadataVLMAnalyzer()
        else:
            analyzer = QwenVLAnalyzer(
                model_name=model_name,
                device=args.device,
                max_new_tokens=max_new_tokens,
                local_files_only=args.local_files_only,
            )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    image_records = iter_image_records(items)
    if args.limit is not None:
        image_records = image_records[: args.limit]

    evidence_records: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    missing_images = 0
    processed_images = 0

    for image_record in image_records:
        image_path = Path(str(image_record["image_path"]))
        if not image_path.exists():
            missing_images += 1
            if not args.include_missing:
                continue

        item = items_by_id.get(str(image_record["item_id"]), {})
        prompt = render_prompt(prompt_template, item)
        try:
            result = analyzer.analyze(str(image_record["image_path"]), prompt, item=item)
        except Exception as exc:
            print(f"WARNING: failed to analyze {image_record['image_path']}: {exc}", file=sys.stderr)
            continue

        processed_images += 1
        records = result_to_evidence(
            result=result,
            item_id=str(image_record["item_id"]),
            image_id=str(image_record["image_id"]),
            image_path=str(image_record["image_path"]),
            image_role=str(image_record["image_role"]),
            prompt_id=args.prompt_id,
            default_actions=default_actions,
            include_raw=args.include_raw,
        )
        evidence_records.extend(records)
        summary_rows.append(
            {
                "item_id": image_record["item_id"],
                "image_id": image_record["image_id"],
                "image_path": image_record["image_path"],
                "risk_types": "|".join(sorted({record["risk_type"] for record in records})),
                "evidence_count": len(records),
                "model": result.model_name,
            }
        )

    write_jsonl(Path(args.output), evidence_records)
    write_summary(Path(args.summary), summary_rows)

    print(f"Items loaded: {len(items)}")
    print(f"Image records considered: {len(image_records)}")
    print(f"Images processed: {processed_images}")
    print(f"Missing images skipped: {missing_images}")
    print(f"Evidence records: {len(evidence_records)}")
    print(f"Evidence output: {args.output}")
    print(f"Summary output: {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
