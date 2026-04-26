"""LLM-ready intent routing for moderation queries."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import replace
from typing import Any, Protocol

from src.agents.router import RouteDecision, route_query


DEFAULT_ALLOWED_RISK_TYPES = {
    "prohibited_goods",
    "counterfeit_brand",
    "image_duplicate",
    "off_platform_contact",
    "misleading_claim",
    "none",
}
DEFAULT_ALLOWED_RETRIEVAL_TYPES = {"text_to_item", "image_to_item", "multimodal", "none"}
DEFAULT_ALLOWED_STRATEGIES = {"topk", "threshold", "topk_threshold", "none"}
DEFAULT_ALLOWED_AUDIT_TASKS = {
    "prohibited_goods",
    "counterfeit_or_infringement",
    "duplicate_image",
    "text_policy_violation",
    "misleading_claim",
    "none",
}

TASK_BY_RISK = {
    "prohibited_goods": "prohibited_goods",
    "counterfeit_brand": "counterfeit_or_infringement",
    "image_duplicate": "duplicate_image",
    "off_platform_contact": "text_policy_violation",
    "misleading_claim": "misleading_claim",
    "none": "none",
}


class IntentRouter(Protocol):
    def route(self, query_text: str, query_configs: list[dict[str, Any]]) -> RouteDecision: ...


class TemplateIntentRouter:
    """Current local TF-IDF template router."""

    def route(self, query_text: str, query_configs: list[dict[str, Any]]) -> RouteDecision:
        return route_query(query_text, query_configs)


def _as_str_set(config: dict[str, Any], key: str, fallback: set[str]) -> set[str]:
    raw_values = config.get(key)
    if not isinstance(raw_values, list):
        return set(fallback)
    values = {str(value).strip() for value in raw_values if str(value).strip()}
    return values or set(fallback)


def _route_schema(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "need_retrieval",
            "audit_task",
            "retrieval_type",
            "strategy",
            "risk_type",
            "top_k",
            "min_score",
            "reason",
            "needs_reference_image",
            "fallback_retrieval_type",
        ],
        "properties": {
            "need_retrieval": {"type": "boolean"},
            "audit_task": {"type": "string", "enum": sorted(_as_str_set(config, "allowed_audit_tasks", DEFAULT_ALLOWED_AUDIT_TASKS))},
            "retrieval_type": {
                "type": "string",
                "enum": sorted(_as_str_set(config, "allowed_retrieval_types", DEFAULT_ALLOWED_RETRIEVAL_TYPES)),
            },
            "strategy": {"type": "string", "enum": sorted(_as_str_set(config, "allowed_strategies", DEFAULT_ALLOWED_STRATEGIES))},
            "risk_type": {"type": "string", "enum": sorted(_as_str_set(config, "allowed_risk_types", DEFAULT_ALLOWED_RISK_TYPES))},
            "top_k": {"type": "integer", "minimum": 0, "maximum": 100},
            "min_score": {"type": "number", "minimum": 0, "maximum": 1},
            "reason": {"type": "string"},
            "needs_reference_image": {"type": "boolean"},
            "fallback_retrieval_type": {
                "type": "string",
                "enum": sorted(_as_str_set(config, "allowed_retrieval_types", DEFAULT_ALLOWED_RETRIEVAL_TYPES)),
            },
        },
    }


def _extract_response_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    for output in response.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text") or content.get("content")
            if isinstance(text, str) and text.strip():
                return text
    raise RuntimeError("OpenAI response did not contain text output")


def _query_template_summary(query_configs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for query in query_configs:
        summary.append(
            {
                "query_id": str(query.get("query_id", "")),
                "text": str(query.get("text", "")),
                "risk_type": str(query.get("risk_type", "")),
                "top_k": int(query.get("top_k", 10)),
                "min_score": float(query.get("min_score", 0.05)),
            }
        )
    return summary


class OpenAILlmIntentRouter:
    """OpenAI Responses API router using Structured Outputs."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.model = str(config.get("model", "gpt-5-nano"))
        self.api_key_env = str(config.get("api_key_env", "OPENAI_API_KEY"))
        self.base_url = str(config.get("base_url", "https://api.openai.com/v1")).rstrip("/")
        self.timeout_seconds = float(config.get("timeout_seconds", 30))

    def route(self, query_text: str, query_configs: list[dict[str, Any]]) -> RouteDecision:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"missing API key env var: {self.api_key_env}")

        payload = self._build_payload(query_text, query_configs)
        request = urllib.request.Request(
            f"{self.base_url}/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI API request failed: {exc}") from exc

        response_data = json.loads(raw)
        route_data = json.loads(_extract_response_text(response_data))
        return route_decision_from_llm_data(query_text, route_data, query_configs, self.config)

    def _build_payload(self, query_text: str, query_configs: list[dict[str, Any]]) -> dict[str, Any]:
        user_payload = {
            "user_query": query_text,
            "default_top_k": int(self.config.get("default_top_k", 10)),
            "default_min_score": float(self.config.get("default_min_score", 0.05)),
            "query_templates": _query_template_summary(query_configs),
        }
        return {
            "model": self.model,
            "input": [
                {"role": "system", "content": str(self.config.get("system_prompt", ""))},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "moderation_intent_route",
                    "strict": True,
                    "schema": _route_schema(self.config),
                }
            },
        }


class HybridIntentRouter:
    """Prefer LLM routing, then safely fall back to the template router."""

    def __init__(self, llm_router: IntentRouter, template_router: IntentRouter | None = None) -> None:
        self.llm_router = llm_router
        self.template_router = template_router or TemplateIntentRouter()

    def route(self, query_text: str, query_configs: list[dict[str, Any]]) -> RouteDecision:
        try:
            route = self.llm_router.route(query_text, query_configs)
            return replace(route, reason=f"llm:{route.reason}")
        except Exception as exc:
            fallback = self.template_router.route(query_text, query_configs)
            return replace(fallback, reason=f"hybrid_fallback:{exc.__class__.__name__}:{fallback.reason}")


def query_id_for_risk(risk_type: str, query_configs: list[dict[str, Any]]) -> tuple[str, str]:
    for query in query_configs:
        if str(query.get("risk_type", "")) == risk_type:
            return str(query.get("query_id", "cli_query")), str(query.get("text", ""))
    return "cli_query", ""


def route_decision_from_llm_data(
    query_text: str,
    data: dict[str, Any],
    query_configs: list[dict[str, Any]],
    config: dict[str, Any],
) -> RouteDecision:
    risk_type = str(data.get("risk_type", "none"))
    retrieval_type = str(data.get("retrieval_type", "none"))
    strategy = str(data.get("strategy", "none"))
    need_retrieval = bool(data.get("need_retrieval", False))
    needs_reference_image = bool(data.get("needs_reference_image", retrieval_type == "image_to_item"))
    fallback_retrieval_type = str(data.get("fallback_retrieval_type", "text_to_item"))

    if risk_type == "none" or retrieval_type == "none":
        need_retrieval = False
        risk_type = "none"
        retrieval_type = "none"
        strategy = "none"

    query_id, template_text = query_id_for_risk(risk_type, query_configs)
    try:
        top_k = int(data.get("top_k", config.get("default_top_k", 10)))
    except (TypeError, ValueError):
        top_k = int(config.get("default_top_k", 10))
    try:
        min_score = float(data.get("min_score", config.get("default_min_score", 0.05)))
    except (TypeError, ValueError):
        min_score = float(config.get("default_min_score", 0.05))

    top_k = max(0, min(top_k, 100))
    min_score = max(0.0, min(min_score, 1.0))
    audit_task = str(data.get("audit_task") or TASK_BY_RISK.get(risk_type, risk_type))
    reason = str(data.get("reason", "llm_structured_output")).strip() or "llm_structured_output"

    if not need_retrieval:
        return RouteDecision(
            need_retrieval=False,
            audit_task="none",
            retrieval_type="none",
            strategy="none",
            query_id="none",
            query_text=query_text,
            retrieval_query_text=query_text,
            risk_type="none",
            top_k=0,
            min_score=0.0,
            confidence=1.0,
            reason=reason,
            needs_reference_image=False,
            fallback_retrieval_type="none",
        )

    return RouteDecision(
        need_retrieval=True,
        audit_task=audit_task,
        retrieval_type=retrieval_type,
        strategy=strategy,
        query_id=query_id,
        query_text=query_text,
        retrieval_query_text=f"{query_text} {template_text}".strip(),
        risk_type=risk_type,
        top_k=top_k,
        min_score=min_score,
        confidence=1.0,
        reason=reason,
        needs_reference_image=needs_reference_image,
        fallback_retrieval_type=fallback_retrieval_type,
    )


def build_intent_router(kind: str, config: dict[str, Any]) -> IntentRouter:
    if kind == "template":
        return TemplateIntentRouter()
    if kind == "llm":
        return OpenAILlmIntentRouter(config)
    if kind == "hybrid":
        return HybridIntentRouter(OpenAILlmIntentRouter(config))
    raise ValueError(f"unsupported router kind: {kind}")
