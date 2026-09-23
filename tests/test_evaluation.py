"""Tests for engine.evaluation — classifier-quality metrics."""

from __future__ import annotations

import pytest

from engine.evaluation import (
    confidence_calibration,
    evaluate_classification,
    is_calibrated,
)


class TestEvaluateClassification:
    def test_perfect_prediction(self):
        y = ["drill", "mill", "drill", "reamer"]
        rep = evaluate_classification(y, y)
        assert rep.n == 4
        assert rep.accuracy == 1.0
        assert rep.macro_precision == 1.0
        assert rep.macro_recall == 1.0
        assert rep.macro_f1 == 1.0
        # no off-diagonal confusion
        assert rep.top_confusions() == []

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            evaluate_classification(["a"], ["a", "b"])

    def test_empty_inputs(self):
        rep = evaluate_classification([], [])
        assert rep.n == 0 and rep.accuracy == 0.0 and rep.per_class == []

    def test_accuracy_and_confusion(self):
        y_true = ["drill", "drill", "mill", "mill"]
        y_pred = ["drill", "mill", "mill", "mill"]
        rep = evaluate_classification(y_true, y_pred)
        assert rep.accuracy == 0.75  # 3 of 4 correct
        # one drill misclassified as mill
        assert rep.confusion[("drill", "mill")] == 1
        assert rep.confusion[("drill", "drill")] == 1
        assert rep.confusion[("mill", "mill")] == 2

    def test_precision_recall_math(self):
        # mill: predicted 3 times, 2 truly mill -> precision 2/3; recall 2/2 = 1
        y_true = ["drill", "drill", "mill", "mill"]
        y_pred = ["drill", "mill", "mill", "mill"]
        rep = evaluate_classification(y_true, y_pred)
        mill = next(m for m in rep.per_class if m.label == "mill")
        drill = next(m for m in rep.per_class if m.label == "drill")
        assert mill.precision == pytest.approx(2 / 3)
        assert mill.recall == pytest.approx(1.0)
        assert drill.precision == pytest.approx(1.0)  # 1 predicted, 1 correct
        assert drill.recall == pytest.approx(0.5)  # 2 true, 1 found

    def test_top_confusions_sorted(self):
        y_true = ["a", "a", "a", "b"]
        y_pred = ["b", "b", "a", "b"]
        rep = evaluate_classification(y_true, y_pred)
        conf = rep.top_confusions()
        assert conf[0] == ("a", "b", 2)

    def test_macro_ignores_spurious_predicted_only_class(self):
        # 'x' is predicted but never true; it shouldn't be averaged into recall
        y_true = ["a", "a", "a"]
        y_pred = ["a", "a", "x"]
        rep = evaluate_classification(y_true, y_pred)
        # only 'a' has support, so macro recall = a's recall = 2/3
        assert rep.macro_recall == pytest.approx(2 / 3)


class TestConfidenceCalibration:
    def test_buckets_ordered_and_accurate(self):
        y_true = ["a", "a", "a", "b", "b", "b"]
        y_pred = ["a", "a", "a", "b", "x", "x"]  # high all right, low mostly wrong
        conf = ["high", "high", "high", "low", "low", "low"]
        buckets = confidence_calibration(y_true, y_pred, conf)
        by = {b.bucket: b for b in buckets}
        assert by["high"].accuracy == 1.0
        assert by["low"].accuracy == pytest.approx(1 / 3)
        # high listed before low
        assert [b.bucket for b in buckets] == ["high", "low"]

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            confidence_calibration(["a"], ["a"], ["high", "low"])

    def test_is_calibrated_true_when_monotonic(self):
        y_true = ["a"] * 10 + ["b"] * 10
        y_pred = ["a"] * 10 + ["b"] * 5 + ["x"] * 5  # high perfect, low 50%
        conf = ["high"] * 10 + ["low"] * 10
        buckets = confidence_calibration(y_true, y_pred, conf)
        assert is_calibrated(buckets) is True

    def test_is_calibrated_false_when_inverted(self):
        # low more accurate than high -> not calibrated
        y_true = ["a"] * 10 + ["b"] * 10
        y_pred = ["x"] * 5 + ["a"] * 5 + ["b"] * 10
        conf = ["high"] * 10 + ["low"] * 10
        buckets = confidence_calibration(y_true, y_pred, conf)
        assert is_calibrated(buckets) is False

    def test_low_support_buckets_ignored(self):
        # only 2 'high' samples -> ignored; can't violate calibration
        buckets = confidence_calibration(
            ["a", "a", "a", "a", "a", "a"],
            ["x", "x", "a", "a", "a", "a"],
            ["high", "high", "low", "low", "low", "low"],
        )
        assert is_calibrated(buckets, min_support=5) is True
