"""Lightweight text-to-item retrieval baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def split_multi_value(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split("|") if part.strip()]


def item_document(item: dict[str, str]) -> str:
    parts = [
        item.get("title", ""),
        item.get("description", ""),
        item.get("category", ""),
        item.get("ocr_text", "").replace("|", " "),
        item.get("risk_objects", "").replace("|", " "),
    ]
    return " ".join(part.strip() for part in parts if part and part.strip())


@dataclass(frozen=True)
class RetrievalHit:
    query_id: str
    query_text: str
    risk_type: str
    item_id: str
    score: float
    rank: int
    document: str

    def to_evidence(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "risk_type": self.risk_type,
            "confidence": round(self.score, 6),
            "evidence": {
                "type": "text_to_item_retrieval",
                "field": "retrieval",
                "query_id": self.query_id,
                "query": self.query_text,
                "rank": self.rank,
                "score": round(self.score, 6),
                "matched_text": self.document[:240],
                "rule": "tfidf_cosine_similarity",
                "snippet": self.document[:240],
            },
            "suggested_action": "manual_review",
        }


class TfidfItemRetriever:
    """A CPU-friendly retrieval baseline used before CLIP is available."""

    def __init__(self, items: list[dict[str, str]]) -> None:
        self.items = items
        self.documents = [item_document(item) for item in items]
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self.item_matrix = self.vectorizer.fit_transform(self.documents)

    def search(self, query_id: str, query_text: str, risk_type: str, top_k: int) -> list[RetrievalHit]:
        query_matrix = self.vectorizer.transform([query_text])
        scores = cosine_similarity(query_matrix, self.item_matrix).ravel()
        ranked_indices = sorted(range(len(scores)), key=lambda idx: (-float(scores[idx]), self.items[idx]["item_id"]))

        hits: list[RetrievalHit] = []
        for rank, idx in enumerate(ranked_indices[:top_k], start=1):
            score = float(scores[idx])
            hits.append(
                RetrievalHit(
                    query_id=query_id,
                    query_text=query_text,
                    risk_type=risk_type,
                    item_id=self.items[idx]["item_id"],
                    score=score,
                    rank=rank,
                    document=self.documents[idx],
                )
            )
        return hits
