"""Evaluation metrics for item-level moderation results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LabelMetrics:
    label: str
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        denominator = self.tp + self.fp
        return self.tp / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.tp + self.fn
        return self.tp / denominator if denominator else 0.0

    @property
    def f1(self) -> float:
        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "f1": round(self.f1, 6),
        }


def split_labels(value: str) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.split("|") if part.strip()}


def risk_only(labels: set[str]) -> set[str]:
    return {label for label in labels if label and label != "normal"}


def compute_label_metrics(
    y_true: dict[str, set[str]],
    y_pred: dict[str, set[str]],
    labels: list[str],
) -> list[LabelMetrics]:
    metrics: list[LabelMetrics] = []
    item_ids = set(y_true) | set(y_pred)

    for label in labels:
        tp = fp = fn = 0
        for item_id in item_ids:
            true_has = label in y_true.get(item_id, set())
            pred_has = label in y_pred.get(item_id, set())
            if true_has and pred_has:
                tp += 1
            elif not true_has and pred_has:
                fp += 1
            elif true_has and not pred_has:
                fn += 1
        metrics.append(LabelMetrics(label=label, tp=tp, fp=fp, fn=fn))

    return metrics


def compute_macro_average(metrics: list[LabelMetrics]) -> dict[str, float]:
    if not metrics:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    return {
        "precision": round(sum(metric.precision for metric in metrics) / len(metrics), 6),
        "recall": round(sum(metric.recall for metric in metrics) / len(metrics), 6),
        "f1": round(sum(metric.f1 for metric in metrics) / len(metrics), 6),
    }


def compute_micro_average(metrics: list[LabelMetrics]) -> dict[str, float]:
    tp = sum(metric.tp for metric in metrics)
    fp = sum(metric.fp for metric in metrics)
    fn = sum(metric.fn for metric in metrics)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def compute_binary_detection(y_true: dict[str, set[str]], y_pred: dict[str, set[str]]) -> dict[str, float | int]:
    item_ids = set(y_true) | set(y_pred)
    tp = fp = tn = fn = 0

    for item_id in item_ids:
        true_risky = bool(y_true.get(item_id, set()))
        pred_risky = bool(y_pred.get(item_id, set()))
        if true_risky and pred_risky:
            tp += 1
        elif not true_risky and pred_risky:
            fp += 1
        elif not true_risky and not pred_risky:
            tn += 1
        elif true_risky and not pred_risky:
            fn += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    false_positive_rate = fp / (fp + tn) if fp + tn else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "false_positive_rate": round(false_positive_rate, 6),
    }
