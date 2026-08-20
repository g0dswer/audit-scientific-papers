"""Regression tests for binary effects and forest-plot audit findings."""

from __future__ import annotations

import builtins
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from calculate_binary_effects import _fisher_exact_two_sided, analyze_binary  # noqa: E402
from plot_forest import write_forest_svg  # noqa: E402
from reconstruct_meta_analysis import MetaAnalysisError, MetaRecord  # noqa: E402


def _record(row_key: str, citation: str = "Study") -> MetaRecord:
    record = MetaRecord(
        analysis_id="analysis",
        study_id=citation,
        citation=citation,
        cohort_id=row_key,
        effect=1.0,
        lower=0.8,
        upper=1.2,
        measure="HR",
    )
    # The meta-analysis worker adds this stable identity to MetaRecord.  Keep
    # the test compatible with the pre-contract checkout as well.
    setattr(record, "row_key", row_key)
    return record


def _forest_result(row_keys: list[str], weights: list[float]) -> dict:
    return {
        "scale": "log_ratio",
        "ci_lower": 0.9,
        "ci_upper": 1.1,
        "prediction_lower": None,
        "prediction_upper": None,
        "prediction_not_estimable_reason": "A fixed-effect model has no between-study distribution to predict",
        "input_confidence": 0.95,
        "study_weights_percent": [
            {"row_key": row_key, "weight": weight}
            for row_key, weight in zip(row_keys, weights)
        ],
        "warnings": [],
        "pooled": 1.0,
        "tau2_method": "DL",
        "confidence": 0.95,
        "Q": 1.0,
        "tau2": 0.1,
        "I2_percent": 0.0,
    }


class BinaryRegressionTests(unittest.TestCase):
    def test_count_derived_point_nnt_uses_exact_fraction_before_ceiling(self):
        result = analyze_binary(5, 10, 5, 12)

        self.assertEqual(result["point_estimate"]["exact_fraction"], "12")
        self.assertEqual(result["point_estimate"]["rounded"], 12)

    def test_count_derived_point_nnh_uses_exact_fraction_before_ceiling(self):
        result = analyze_binary(5, 12, 5, 10)

        self.assertEqual(result["point_estimate"]["exact_fraction"], "12")
        self.assertEqual(result["point_estimate"]["rounded"], 12)


class FisherOptionalDependencyRegressionTests(unittest.TestCase):
    def test_missing_scipy_import_is_really_blocked_and_returns_none(self):
        real_import = builtins.__import__

        def block_scipy(name, globals=None, locals=None, fromlist=(), level=0):
            if name in {"scipy", "scipy.stats"}:
                raise ModuleNotFoundError("No module named 'scipy'", name="scipy")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=block_scipy):
            self.assertIsNone(_fisher_exact_two_sided(15, 100, 5, 100))

    def test_missing_internal_scipy_module_is_not_treated_as_optional_absence(self):
        real_import = builtins.__import__

        def break_installed_scipy(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "scipy.stats":
                raise ModuleNotFoundError(
                    "No module named 'scipy._lib'",
                    name="scipy._lib",
                )
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=break_installed_scipy):
            with self.assertRaisesRegex(ModuleNotFoundError, "scipy._lib"):
                _fisher_exact_two_sided(15, 100, 5, 100)

    def test_fisher_calculation_failure_is_not_silently_downgraded(self):
        scipy = types.ModuleType("scipy")
        stats = types.ModuleType("scipy.stats")

        def fail(*args, **kwargs):
            raise RuntimeError("calculation failure")

        stats.fisher_exact = fail
        scipy.stats = stats
        with patch.dict(sys.modules, {"scipy": scipy, "scipy.stats": stats}):
            with self.assertRaisesRegex(RuntimeError, "calculation failure"):
                _fisher_exact_two_sided(15, 100, 5, 100)


class ForestRegressionTests(unittest.TestCase):
    def test_square_area_is_proportional_to_fitted_weight(self):
        records = [_record("a", "First"), _record("b", "Second")]
        result = _forest_result(["a", "b"], [10.0, 40.0])
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "forest.svg"
            write_forest_svg(records, result, destination)
            widths = [
                float(line.split('width="')[1].split('"')[0])
                for line in destination.read_text(encoding="utf-8").splitlines()
                if line.startswith("<rect x=")
            ]
        self.assertEqual(len(widths), 2)
        self.assertAlmostEqual((widths[0] * widths[0]) / (widths[1] * widths[1]), 0.25, delta=1e-9)

    def test_forest_rejects_reordered_or_changed_rows_by_row_key(self):
        records = [_record("a", "First"), _record("b", "Second")]
        result = _forest_result(["a", "b"], [10.0, 40.0])
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "forest.svg"
            with self.assertRaisesRegex(MetaAnalysisError, "does not match"):
                write_forest_svg(records[::-1], result, destination)
            changed = [_record("a", "First"), _record("changed", "Second")]
            with self.assertRaisesRegex(MetaAnalysisError, "does not match"):
                write_forest_svg(changed, result, destination)

    def test_forest_fails_closed_when_weight_row_key_is_missing(self):
        records = [_record("a", "First"), _record("b", "Second")]
        result = _forest_result(["a", "b"], [10.0, 40.0])
        del result["study_weights_percent"][0]["row_key"]
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(MetaAnalysisError, "every study weight"):
                write_forest_svg(records, result, Path(temp_dir) / "forest.svg")

    def test_forest_exposes_prediction_not_estimable_reason(self):
        records = [_record("a", "First"), _record("b", "Second")]
        result = _forest_result(["a", "b"], [10.0, 40.0])
        reason = "k-2 requires at least three studies"
        result["prediction_not_estimable_reason"] = reason
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "forest.svg"
            write_forest_svg(records, result, destination)
            svg = destination.read_text(encoding="utf-8")
        self.assertIn("prediction interval not estimable: k-2 requires at least three studies", svg)


class ExtractionDocumentationRegressionTests(unittest.TestCase):
    def test_mixed_interval_documentation_states_se_variance_and_weight_changes(self):
        documentation = (SCRIPT_DIR.parent / "references" / "meta-analysis-extraction.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("16.1% too low", documentation)
        self.assertIn("29.6% too low", documentation)
        self.assertIn("42% too high", documentation)


if __name__ == "__main__":
    unittest.main()
