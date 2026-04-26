"""Dense text embedding retrieval baselines for item search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import normalize

from src.retrieval.text_search import item_document


@dataclass(frozen=True)
class EmbeddingRetrievalHit:
    query_id: str
    query_text: str
    risk_type: str
    item_id: str
    score: float
    rank: int
    document: str
    backend: str

    def to_evidence(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "risk_type": self.risk_type,
            "confidence": round(self.score, 6),
            "evidence": {
                "type": "text_embedding_retrieval",
                "field": "retrieval",
                "query_id": self.query_id,
                "query": self.query_text,
                "rank": self.rank,
                "score": round(self.score, 6),
                "matched_text": self.document[:240],
                "rule": f"{self.backend}_cosine_similarity",
                "snippet": self.document[:240],
            },
            "suggested_action": "manual_review",
        }


class TextEmbeddingRetriever(Protocol):
    """Common contract for dense text embedding retrievers."""

    items: list[dict[str, str]]
    documents: list[str]
    item_embeddings: np.ndarray
    backend: str
    model_name: str

    @property
    def embedding_dim(self) -> int: ...

    def encode_queries(self, query_texts: list[str]) -> np.ndarray: ...

    def search(self, query_id: str, query_text: str, risk_type: str, top_k: int) -> list[EmbeddingRetrievalHit]: ...


def _rank_hits(
    *,
    items: list[dict[str, str]],
    documents: list[str],
    scores: np.ndarray,
    query_id: str,
    query_text: str,
    risk_type: str,
    top_k: int,
    backend: str,
) -> list[EmbeddingRetrievalHit]:
    ranked_indices = sorted(range(len(scores)), key=lambda idx: (-float(scores[idx]), items[idx]["item_id"]))

    hits: list[EmbeddingRetrievalHit] = []
    for rank, idx in enumerate(ranked_indices[:top_k], start=1):
        hits.append(
            EmbeddingRetrievalHit(
                query_id=query_id,
                query_text=query_text,
                risk_type=risk_type,
                item_id=items[idx]["item_id"],
                score=float(scores[idx]),
                rank=rank,
                document=documents[idx],
                backend=backend,
            )
        )
    return hits


class LsiTextEmbeddingRetriever:
    """Local dense embedding baseline using TF-IDF + truncated SVD.

    This is an engineering bridge before model embeddings are available. It
    produces dense normalized item/query vectors, supports cache export, and
    keeps the same retrieval result contract as the TF-IDF baseline.
    """

    backend = "lsi_tfidf_svd"
    model_name = "tfidf_char_wb_truncated_svd"

    def __init__(self, items: list[dict[str, str]], components: int = 128) -> None:
        self.items = items
        self.documents = [item_document(item) for item in items]
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=1)
        self.tfidf_matrix = self.vectorizer.fit_transform(self.documents)

        max_components = max(1, min(self.tfidf_matrix.shape[0] - 1, self.tfidf_matrix.shape[1] - 1, components))
        self.svd: TruncatedSVD | None = None
        if max_components >= 2:
            self.svd = TruncatedSVD(n_components=max_components, random_state=42)
            dense = self.svd.fit_transform(self.tfidf_matrix)
        else:
            dense = self.tfidf_matrix.toarray()
        self.item_embeddings = normalize(dense, norm="l2").astype(np.float32)

    @property
    def embedding_dim(self) -> int:
        return int(self.item_embeddings.shape[1]) if self.item_embeddings.ndim == 2 else 0

    def encode_queries(self, query_texts: list[str]) -> np.ndarray:
        matrix = self.vectorizer.transform(query_texts)
        if self.svd is not None:
            dense = self.svd.transform(matrix)
        else:
            dense = matrix.toarray()
        return normalize(dense, norm="l2").astype(np.float32)

    def search(self, query_id: str, query_text: str, risk_type: str, top_k: int) -> list[EmbeddingRetrievalHit]:
        query_embedding = self.encode_queries([query_text])
        scores = cosine_similarity(query_embedding, self.item_embeddings).ravel()
        return _rank_hits(
            items=self.items,
            documents=self.documents,
            scores=scores,
            query_id=query_id,
            query_text=query_text,
            risk_type=risk_type,
            top_k=top_k,
            backend=self.backend,
        )


class SentenceTransformerTextEmbeddingRetriever:
    """True semantic text embedding retriever using sentence-transformers."""

    backend = "sentence_transformers"

    def __init__(
        self,
        items: list[dict[str, str]],
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        device: str | None = None,
        batch_size: int = 32,
        local_files_only: bool = False,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. Install it or use backend `lsi_tfidf_svd`."
            ) from exc

        self.items = items
        self.documents = [item_document(item) for item in items]
        self.model_name = model_name
        self.batch_size = batch_size

        model_kwargs: dict[str, Any] = {}
        if device:
            model_kwargs["device"] = device
        if local_files_only:
            model_kwargs["local_files_only"] = True

        self.model = SentenceTransformer(model_name, **model_kwargs)
        self.item_embeddings = self._encode(self.documents)

    @property
    def embedding_dim(self) -> int:
        return int(self.item_embeddings.shape[1]) if self.item_embeddings.ndim == 2 else 0

    def _encode(self, texts: list[str]) -> np.ndarray:
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def encode_queries(self, query_texts: list[str]) -> np.ndarray:
        return self._encode(query_texts)

    def search(self, query_id: str, query_text: str, risk_type: str, top_k: int) -> list[EmbeddingRetrievalHit]:
        query_embedding = self.encode_queries([query_text])
        scores = cosine_similarity(query_embedding, self.item_embeddings).ravel()
        return _rank_hits(
            items=self.items,
            documents=self.documents,
            scores=scores,
            query_id=query_id,
            query_text=query_text,
            risk_type=risk_type,
            top_k=top_k,
            backend=self.backend,
        )


def build_text_embedding_retriever(
    *,
    items: list[dict[str, str]],
    backend: str,
    components: int = 128,
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    device: str | None = None,
    batch_size: int = 32,
    local_files_only: bool = False,
) -> TextEmbeddingRetriever:
    """Build a dense text retriever.

    `auto` prefers a true sentence-transformers model when available and falls
    back to the local LSI baseline when the optional dependency/model is not
    ready yet.
    """

    if backend == "lsi_tfidf_svd":
        return LsiTextEmbeddingRetriever(items, components=components)

    if backend == "sentence_transformers":
        return SentenceTransformerTextEmbeddingRetriever(
            items,
            model_name=model_name,
            device=device,
            batch_size=batch_size,
            local_files_only=local_files_only,
        )

    if backend == "auto":
        try:
            return SentenceTransformerTextEmbeddingRetriever(
                items,
                model_name=model_name,
                device=device,
                batch_size=batch_size,
                local_files_only=local_files_only,
            )
        except Exception:
            return LsiTextEmbeddingRetriever(items, components=components)

    raise ValueError(f"unsupported embedding backend: {backend}")
