"""Lightweight moderation intent router for the CLI MVP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True)
class RouteDecision:
    need_retrieval: bool
    audit_task: str
    retrieval_type: str
    strategy: str
    query_id: str
    query_text: str
    retrieval_query_text: str
    risk_type: str
    top_k: int
    min_score: float
    confidence: float
    reason: str
    needs_reference_image: bool = False
    fallback_retrieval_type: str = "text_to_item"


NEGATIVE_PATTERNS = [
    "你好",
    "hello",
    "天气",
    "讲个笑话",
    "项目进度",
    "怎么使用",
]

TASK_BY_RISK = {
    "prohibited_goods": "prohibited_goods",
    "counterfeit_brand": "counterfeit_or_infringement",
    "image_duplicate": "duplicate_image",
    "off_platform_contact": "text_policy_violation",
    "misleading_claim": "misleading_claim",
}

IMAGE_TO_ITEM_PATTERNS = [
    "相似图片",
    "类似图片",
    "相似图",
    "同图",
    "盗图",
    "重复铺货",
    "近重复",
    "这张图",
    "参考图",
    "图片商品",
    "以图搜",
    "图搜",
    "被别的店铺盗用",
    "被其他店铺盗用",
]


def looks_non_retrieval(query_text: str) -> bool:
    normalized = query_text.strip().lower()
    if not normalized:
        return True
    return any(pattern.lower() in normalized for pattern in NEGATIVE_PATTERNS)


def looks_image_to_item(query_text: str) -> bool:
    normalized = query_text.strip().lower()
    return any(pattern.lower() in normalized for pattern in IMAGE_TO_ITEM_PATTERNS)


def infer_top_k(query_text: str, default_top_k: int) -> int:
    for marker, value in [("前10", 10), ("10个", 10), ("十个", 10), ("前5", 5), ("5个", 5), ("五个", 5)]:
        if marker in query_text:
            return value
    return default_top_k


def route_query(query_text: str, query_configs: list[dict[str, Any]]) -> RouteDecision:
    if looks_non_retrieval(query_text):
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
            reason="matched_non_retrieval_pattern",
        )

    if looks_image_to_item(query_text):
        top_k = infer_top_k(query_text, 10)
        return RouteDecision(
            need_retrieval=True,
            audit_task="duplicate_image",
            retrieval_type="image_to_item",
            strategy="topk_threshold",
            query_id="q_image_duplicate",
            query_text=query_text,
            retrieval_query_text=query_text,
            risk_type="image_duplicate",
            top_k=top_k,
            min_score=0.996,
            confidence=1.0,
            reason="matched_image_to_item_pattern",
            needs_reference_image=True,
            fallback_retrieval_type="none",
        )

    documents = [str(config.get("text", "")) for config in query_configs]
    if not documents:
        return RouteDecision(
            need_retrieval=True,
            audit_task="prohibited_goods",
            retrieval_type="text_to_item",
            strategy="topk_threshold",
            query_id="cli_query",
            query_text=query_text,
            retrieval_query_text=query_text,
            risk_type="prohibited_goods",
            top_k=5,
            min_score=0.05,
            confidence=0.0,
            reason="fallback_no_query_templates",
        )

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    matrix = vectorizer.fit_transform(documents + [query_text])
    scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
    best_idx = max(range(len(scores)), key=lambda idx: float(scores[idx]))
    best = query_configs[best_idx]

    risk_type = str(best.get("risk_type", "prohibited_goods"))
    template_text = str(best.get("text", ""))
    top_k = infer_top_k(query_text, int(best.get("top_k", 5)))
    min_score = float(best.get("min_score", 0.05))
    confidence = float(scores[best_idx])

    return RouteDecision(
        need_retrieval=True,
        audit_task=TASK_BY_RISK.get(risk_type, risk_type),
        retrieval_type="text_to_item",
        strategy="topk_threshold",
        query_id=str(best.get("query_id", "cli_query")),
        query_text=query_text,
        retrieval_query_text=f"{query_text} {template_text}".strip(),
        risk_type=risk_type,
        top_k=top_k,
        min_score=min_score,
        confidence=confidence,
        reason="matched_query_template",
    )
