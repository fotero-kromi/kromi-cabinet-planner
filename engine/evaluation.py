"""kromi_app.engine.evaluation — pure classifier-quality metrics.

Given predicted labels, ground-truth labels, and (optionally) the confidence the
classifier reported, this computes the standard evaluation signals a reviewer
asks for: overall accuracy, per-class precision / recall / F1, a confusion
matrix, and confidence calibration (do the rows the classifier called
"high confidence" actually score better than the "low" ones?).

This is the measurement half of the validation framework. It is pure: no
pandas, no Streamlit, no I/O — just labels in, metrics out — so it is trivial to
unit-test and reuse. The page layer is responsible for sourcing the labels (for
example, technician overrides are human-verified ground truth) and for display.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClassMetrics:
    """Precision / recall / F1 for a single class label."""

    label: str
    support: int  # ground-truth instances of this class
    predicted: int  # times this class was predicted
    true_positives: int
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True)
class EvalReport:
    n: int
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    per_class: list[ClassMetrics] = field(default_factory=list)
    # confusion[(true_label, predicted_label)] = count
    confusion: dict[tuple[str, str], int] = field(default_factory=dict)

    def top_confusions(self, limit: int = 10) -> list[tuple[str, str, int]]:
        """Most frequent (true, predicted) mismatches, descending by count."""
        wrong = [(t, p, c) for (t, p), c in self.confusion.items() if t != p and c > 0]
        wrong.sort(key=lambda x: x[2], reverse=True)
        return wrong[:limit]


@dataclass(frozen=True)
class ConfidenceBucket:
    bucket: str
    n: int
    correct: int
    accuracy: float


def _norm(v: object) -> str:
    return ("" if v is None else str(v)).strip()


def evaluate_classification(y_true: list, y_pred: list) -> EvalReport:
    """Compute accuracy, per-class precision/recall/F1, and a confusion matrix.

    Labels are compared as normalized strings. Inputs must be the same length.
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")

    yt = [_norm(v) for v in y_true]
    yp = [_norm(v) for v in y_pred]
    n = len(yt)
    if n == 0:
        return EvalReport(0, 0.0, 0.0, 0.0, 0.0, [], {})

    correct = sum(1 for a, b in zip(yt, yp, strict=True) if a == b)
    accuracy = correct / n

    confusion: dict[tuple[str, str], int] = defaultdict(int)
    for a, b in zip(yt, yp, strict=True):
        confusion[(a, b)] += 1

    support = Counter(yt)
    predicted = Counter(yp)
    tp: Counter[str] = Counter()
    for a, b in zip(yt, yp, strict=True):
        if a == b:
            tp[a] += 1

    labels = sorted(set(support) | set(predicted))
    per_class: list[ClassMetrics] = []
    for lab in labels:
        s = support.get(lab, 0)
        p = predicted.get(lab, 0)
        t = tp.get(lab, 0)
        precision = t / p if p else 0.0
        recall = t / s if s else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class.append(ClassMetrics(lab, s, p, t, precision, recall, f1))

    # Macro averages over classes that actually occur in the ground truth, so a
    # never-true spurious predicted class can't dominate the average.
    truth_classes = [m for m in per_class if m.support > 0]
    k = len(truth_classes) or 1
    macro_p = sum(m.precision for m in truth_classes) / k
    macro_r = sum(m.recall for m in truth_classes) / k
    macro_f1 = sum(m.f1 for m in truth_classes) / k

    return EvalReport(
        n=n,
        accuracy=accuracy,
        macro_precision=macro_p,
        macro_recall=macro_r,
        macro_f1=macro_f1,
        per_class=per_class,
        confusion=dict(confusion),
    )


# Default display order for the planner's categorical confidence.
_CONF_ORDER = {"high": 0, "medium": 1, "low": 2, "unknown": 3, "": 4}


def confidence_calibration(y_true: list, y_pred: list, confidence: list) -> list[ConfidenceBucket]:
    """Accuracy within each confidence bucket.

    A well-calibrated classifier scores higher accuracy in 'high' than in 'low'.
    Buckets are returned in the planner's natural order (high → low → unknown).
    """
    if not (len(y_true) == len(y_pred) == len(confidence)):
        raise ValueError("y_true, y_pred and confidence must have the same length")

    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # bucket -> [n, correct]
    for a, b, c in zip(y_true, y_pred, confidence, strict=True):
        key = _norm(c).lower()
        agg[key][0] += 1
        if _norm(a) == _norm(b):
            agg[key][1] += 1

    buckets = [
        ConfidenceBucket(
            bucket=k or "unknown",
            n=v[0],
            correct=v[1],
            accuracy=(v[1] / v[0] if v[0] else 0.0),
        )
        for k, v in agg.items()
    ]
    buckets.sort(key=lambda b: _CONF_ORDER.get(b.bucket, 99))
    return buckets


def is_calibrated(buckets: list[ConfidenceBucket], min_support: int = 5) -> bool:
    """True if accuracy is monotonically non-increasing high → low.

    Buckets with fewer than `min_support` samples are ignored (too noisy to
    judge). 'unknown'/'' buckets are excluded from the monotonicity check.
    """
    ordered = [b for b in buckets if b.bucket in ("high", "medium", "low") and b.n >= min_support]
    ordered.sort(key=lambda b: _CONF_ORDER[b.bucket])
    accs = [b.accuracy for b in ordered]
    return all(accs[i] >= accs[i + 1] for i in range(len(accs) - 1))
