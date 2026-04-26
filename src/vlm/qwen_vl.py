"""Qwen2.5-VL image understanding wrapper for moderation evidence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_RISK_TYPES = {
    "prohibited_goods",
    "counterfeit_brand",
    "image_duplicate",
    "off_platform_contact",
    "misleading_claim",
}


@dataclass(frozen=True)
class VLMRiskAssessment:
    risk_type: str
    risk_objects: list[str]
    evidence_reason: str
    confidence: float
    bbox: list[float] | None


@dataclass(frozen=True)
class VLMResult:
    caption: str
    ocr_like_text: list[str]
    risk_assessments: list[VLMRiskAssessment]
    raw_response: str
    model_name: str


def clamp_confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(score, 1.0)), 6)


def clean_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(part).strip() for part in value if str(part).strip()]


def clean_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        return [round(float(part), 3) for part in value]
    except (TypeError, ValueError):
        return None


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("VLM response JSON must be an object")
    return parsed


def parse_vlm_result(text: str, model_name: str) -> VLMResult:
    parsed = extract_json_object(text)
    assessments: list[VLMRiskAssessment] = []
    raw_assessments = parsed.get("risk_assessments", [])
    if isinstance(raw_assessments, list):
        for item in raw_assessments:
            if not isinstance(item, dict):
                continue
            risk_type = str(item.get("risk_type", "")).strip()
            if risk_type not in VALID_RISK_TYPES:
                continue
            assessments.append(
                VLMRiskAssessment(
                    risk_type=risk_type,
                    risk_objects=clean_text_list(item.get("risk_objects", [])),
                    evidence_reason=str(item.get("evidence_reason", "")).strip(),
                    confidence=clamp_confidence(item.get("confidence", 0.0)),
                    bbox=clean_bbox(item.get("bbox")),
                )
            )

    return VLMResult(
        caption=str(parsed.get("caption", "")).strip(),
        ocr_like_text=clean_text_list(parsed.get("ocr_like_text", [])),
        risk_assessments=assessments,
        raw_response=text,
        model_name=model_name,
    )


class MetadataVLMAnalyzer:
    """A lightweight dry-run backend that creates visual-risk-like records from item metadata."""

    def __init__(self, model_name: str = "metadata_vlm_dry_run") -> None:
        self.model_name = model_name

    def analyze(self, image_path: str, prompt: str, item: dict[str, str] | None = None) -> VLMResult:
        del prompt
        item = item or {}
        labels = [part.strip() for part in item.get("risk_labels", "").split("|") if part.strip()]
        objects = [part.strip() for part in item.get("risk_objects", "").split("|") if part.strip()]
        ocr_text = [part.strip() for part in item.get("ocr_text", "").split("|") if part.strip()]

        assessments = [
            VLMRiskAssessment(
                risk_type=label,
                risk_objects=objects,
                evidence_reason=f"metadata dry-run evidence for {label}",
                confidence=0.5,
                bbox=None,
            )
            for label in labels
            if label in VALID_RISK_TYPES
        ]

        return VLMResult(
            caption=f"metadata dry-run for {Path(image_path).name}",
            ocr_like_text=ocr_text,
            risk_assessments=assessments,
            raw_response="",
            model_name=self.model_name,
        )


class QwenVLAnalyzer:
    """Qwen2.5-VL backend loaded lazily through transformers."""

    def __init__(
        self,
        model_name: str,
        device: str = "auto",
        max_new_tokens: int = 512,
        local_files_only: bool = False,
    ) -> None:
        try:
            import torch  # type: ignore
            import transformers  # type: ignore
            from qwen_vl_utils import process_vision_info  # type: ignore
            from transformers import AutoProcessor  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Qwen2.5-VL backend requires torch, transformers, and qwen-vl-utils. "
                "Install cloud dependencies before using --backend qwen_vl."
            ) from exc

        model_cls = getattr(transformers, "Qwen2_5_VLForConditionalGeneration", None)
        if model_cls is None:
            raise RuntimeError("Installed transformers does not expose Qwen2_5_VLForConditionalGeneration.")

        self.torch = torch
        self.process_vision_info = process_vision_info
        self.model_name = model_name
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.processor = AutoProcessor.from_pretrained(model_name, local_files_only=local_files_only)

        load_kwargs: dict[str, Any] = {
            "torch_dtype": "auto",
            "local_files_only": local_files_only,
        }
        if device == "auto":
            load_kwargs["device_map"] = "auto"
        self.model = model_cls.from_pretrained(model_name, **load_kwargs)
        if device != "auto":
            self.model.to(device)

    def analyze(self, image_path: str, prompt: str, item: dict[str, str] | None = None) -> VLMResult:
        del item
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": str(image_path)},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = self.process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        target_device = self.device
        if target_device == "auto" and hasattr(self.model, "device"):
            target_device = str(self.model.device)
        if hasattr(inputs, "to"):
            inputs = inputs.to(target_device)

        with self.torch.no_grad():
            generated_ids = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens)

        input_length = int(inputs["input_ids"].shape[1])
        generated_ids = generated_ids[:, input_length:]
        decoded = self.processor.batch_decode(generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
        return parse_vlm_result(decoded[0], self.model_name)
