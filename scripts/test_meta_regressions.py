"""Regression tests for the audited meta-analysis guardrails."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
FIXTURE = ROOT / "tests" / "fixtures" / "naghshi_2020_mortality.csv"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconstruct_meta_analysis import (  # noqa: E402
    CURRENT_PREDICTION_DF,
    MetaAnalysisError,
    compare_reproduction,
    filter_records,
    load_records,
    meta_analysis,
    run_sensitivity_ladder,
)
from validate_meta_dataset import validate_records  # noqa: E402


class MetaRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_records(FIXTURE)
        cls.clean = filter_records(
            cls.records,
            analysis_id="total_all_cause",
            direct_outcomes_only=True,
            common_measure="HR",
        )

    def test_materially_asymmetric_intervals_are_rejected_on_analysis_scale(self):
        source = self.clean[:2]
        linear = [
            replace(source[0], measure="MD", effect=10.0, lower=-1.0, upper=11.0),
            replace(source[1], measure="MD", effect=9.0, lower=8.5, upper=9.5),
        ]
        with self.assertRaisesRegex(MetaAnalysisError, "Materially asymmetric"):
            meta_analysis(linear)

        ratio = [
            replace(source[0], effect=2.0, lower=0.9, upper=2.1),
            replace(source[1], effect=1.2, lower=1.1, upper=1.3),
        ]
        with self.assertRaisesRegex(MetaAnalysisError, "log ratio scale"):
            meta_analysis(ratio)

    def test_dependency_state_is_canonical_and_fail_closed_in_engine(self):
        source = self.clean[:2]
        modeled = [replace(source[0], overlap_status="modeled", participant_overlap_possible=True), source[1]]
        with self.assertRaisesRegex(MetaAnalysisError, "modeled"):
            meta_analysis(modeled)
        contradictory_unresolved = [
            replace(source[0], overlap_status="unresolved", participant_overlap_possible=False),
            source[1],
        ]
        with self.assertRaisesRegex(MetaAnalysisError, "contradict"):
            meta_analysis(contradictory_unresolved)
        contradictory_none = [
            replace(source[0], overlap_status="none", participant_overlap_possible=True),
            source[1],
        ]
        with self.assertRaisesRegex(MetaAnalysisError, "contradict"):
            meta_analysis(contradictory_none)

    def test_reproduction_gate_requires_all_dimensions_and_reports_statuses(self):
        observed = {
            "pooled": 1.25,
            "ci_lower": 0.95,
            "ci_upper": 1.65,
            "k": 12,
            "model": "random",
            "scale": "log_ratio",
        }
        self.assertEqual(compare_reproduction(observed, None)["status"], "NOT_CHECKED")
        expected = dict(observed)
        self.assertEqual(compare_reproduction(observed, expected)["status"], "PASS")
        self.assertEqual(
            compare_reproduction(observed, {"pooled": observed["pooled"]})["status"],
            "NOT_CHECKED",
        )
        failed = compare_reproduction(observed, {**expected, "k": 13})
        self.assertEqual(failed["status"], "FAIL")
        self.assertEqual(failed["checks"]["k"]["status"], "FAIL")

    def test_sensitivity_cli_without_expected_result_is_not_checked_and_blocked(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "reconstruct_meta_analysis.py"),
                str(FIXTURE),
                "--analysis-id",
                "total_all_cause",
                "--common-measure",
                "HR",
                "--sensitivity",
                "all",
                "--allow-mixed-estimands",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["reproduction_status"], "NOT_CHECKED")
        self.assertEqual(payload["sensitivity_status"], "NOT_CHECKED")
        self.assertEqual(payload["sensitivity_ladder"], [])

    def test_ratio_reproduction_uses_log_scale_with_absolute_and_relative_tolerances(self):
        observed = {
            "pooled": 2.0,
            "ci_lower": 1.5,
            "ci_upper": 2.5,
            "k": 2,
            "model": "random",
            "scale": "HR",
        }
        expected = {**observed, "pooled": 2.01}
        comparison = compare_reproduction(
            observed,
            expected,
            absolute_tolerance=1e-4,
            relative_tolerance=0.01,
        )
        self.assertEqual(comparison["status"], "PASS")
        self.assertEqual(comparison["checks"]["pooled"]["comparison_scale"], "log")
        self.assertAlmostEqual(
            comparison["checks"]["pooled"]["absolute_difference"],
            abs(math.log(2.0) - math.log(2.01)),
        )

    def test_current_prediction_interval_conventions_are_explicit(self):
        normal = meta_analysis(self.clean, inference="normal")
        hksj = meta_analysis(self.clean, inference="HKSJ")
        historical = meta_analysis(self.clean, inference="normal", prediction_df="k-2")
        self.assertEqual(CURRENT_PREDICTION_DF, "k-1")
        self.assertEqual(normal["prediction_df_convention"], "k-1")
        self.assertEqual(normal["prediction_interval_df"], len(self.clean) - 1)
        self.assertEqual(normal["prediction_multiplier_distribution"], "normal")
        self.assertIn("current_Cochrane_RevMan_Wald", normal["prediction_interval_method"])
        self.assertEqual(hksj["prediction_multiplier_distribution"], "student_t")
        self.assertEqual(hksj["prediction_interval_df"], len(self.clean) - 1)
        self.assertIn("current_Cochrane_RevMan_HKSJ_t_k-1", hksj["prediction_interval_method"])
        self.assertEqual(historical["prediction_df_convention"], "k-2")
        self.assertIn("historical", historical["prediction_interval_method"])

    def test_six_to_eight_use_s5_clean_population(self):
        ladder = run_sensitivity_ladder(
            filter_records(self.records, analysis_id="total_all_cause"),
            common_measure="HR",
            allow_mixed_estimands=True,
        )
        steps = {step["id"]: step for step in ladder}
        s5_k = steps["S5_direct_exposure"]["result"]["k"]
        for method, result in steps["S6_alternative_tau2"]["result"].items():
            with self.subTest(method=method):
                self.assertEqual(result["k"], s5_k)
                self.assertNotIn(
                    "Papanikolaou_2019",
                    {item["study_id"] for item in result["study_weights_percent"]},
                )
        self.assertEqual(steps["S7_hksj"]["result"]["k"], s5_k)
        self.assertNotIn(
            "Papanikolaou_2019",
            {
                item["study_id"]
                for item in steps["S7_hksj"]["result"]["study_weights_percent"]
            },
        )
        self.assertEqual(steps["S8_leave_one_cluster_out"]["result"]["k"], s5_k)
        self.assertNotIn(
            "Papanikolaou_2019",
            {
                item["study_id"]
                for item in steps["S8_leave_one_cluster_out"]["result"][
                    "study_weights_percent"
                ]
            },
        )
        self.assertTrue(
            all(
                len(item["deleted_study_ids"]) >= 1
                for item in steps["S8_leave_one_cluster_out"]["result"]["leave_one_out"]
            )
        )

    def test_validator_separates_inventory_from_included_pool(self):
        source = self.clean[:3]
        excluded_contradiction = replace(
            source[0],
            include_published=False,
            overlap_status="unresolved",
            participant_overlap_possible=False,
        )
        report = validate_records([excluded_contradiction, source[1], source[2]])
        self.assertFalse(report["valid_for_inventory_integrity"])
        self.assertTrue(report["valid_for_included_pool"])
        self.assertEqual(report["included_records"], 2)
        self.assertTrue(
            any(
                issue["scope"] == "inventory" and issue["code"] == "CONTRADICTORY_DEPENDENCE_STATE"
                for issue in report["issues"]
            )
        )
        self.assertFalse(
            any(
                issue["scope"] == "included_pool" and issue["code"] == "CONTRADICTORY_DEPENDENCE_STATE"
                for issue in report["issues"]
            )
        )

    def test_output_confidence_is_finite_and_strictly_between_zero_and_one(self):
        for confidence in (0.0, -0.1, 1.0, float("nan")):
            with self.subTest(confidence=confidence), self.assertRaisesRegex(
                MetaAnalysisError, "Output confidence"
            ):
                meta_analysis(self.clean, confidence=confidence)

    def test_i2_method_and_stable_weight_row_keys_are_reported(self):
        result = meta_analysis(self.clean)
        self.assertEqual(result["I2_method"], "Q_based_Higgins_Thompson")
        keys = [item["row_key"] for item in result["study_weights_percent"]]
        self.assertEqual(len(keys), len(self.clean))
        self.assertEqual(len(set(keys)), len(keys))
        reordered = meta_analysis(list(reversed(self.clean)))
        self.assertEqual(
            {item["row_key"] for item in reordered["study_weights_percent"]},
            set(keys),
        )


if __name__ == "__main__":
    unittest.main()
