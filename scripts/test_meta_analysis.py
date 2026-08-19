import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
FIXTURE = ROOT / "tests" / "fixtures" / "naghshi_2020_mortality.csv"
EXPECTED = ROOT / "tests" / "fixtures" / "naghshi_2020_expected.json"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconstruct_meta_analysis import (  # noqa: E402
    MetaAnalysisError,
    _student_t_quantile,
    filter_records,
    load_records,
    meta_analysis,
    run_sensitivity_ladder,
)
from validate_meta_dataset import validate_records  # noqa: E402


class NaghshiRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_records(FIXTURE)
        cls.expected = json.loads(EXPECTED.read_text())

    def _pool(self, analysis_id, direct=False, measure=None):
        records = filter_records(
            self.records,
            analysis_id=analysis_id,
            direct_outcomes_only=direct,
            common_measure=measure,
        )
        return meta_analysis(
            records,
            tau2_method="DL",
            inference="normal",
            allow_mixed_estimands=measure is None,
        )

    def test_published_and_clean_total_regressions(self):
        observed = {
            "published_total": self._pool("total_all_cause")["pooled"],
            "clean_total_direct_outcome": self._pool("total_all_cause", direct=True)["pooled"],
            "clean_total_direct_outcome_hr": self._pool("total_all_cause", direct=True, measure="HR")["pooled"],
        }
        for key, value in observed.items():
            with self.subTest(key=key):
                self.assertAlmostEqual(value, self.expected["strict_reference"][key], delta=5e-10)
        self.assertEqual(len(filter_records(self.records, analysis_id="total_all_cause")), 23)
        clean_hr = filter_records(
            self.records,
            analysis_id="total_all_cause",
            direct_outcomes_only=True,
            common_measure="HR",
        )
        self.assertEqual(len(clean_hr), 13)
        self.assertEqual(
            {record.study_id for record in clean_hr},
            {
                "Halbesma_2009",
                "Argos_2013",
                "Hernandez_Alonso_2016",
                "Song_2016",
                "Courand_2016",
                "Zaslavsky_2017",
                "Dehghan_2017",
                "Virtanen_2019",
                "Papanikolaou_2019",
                "Budhathoki_2019",
                "Mendonca_2019",
                "Chan_2019_men",
                "Chan_2019_women",
            },
        )

    def test_published_and_clean_plant_regressions(self):
        observed = {
            "published_plant": self._pool("plant_all_cause")["pooled"],
            "clean_plant_direct_outcome": self._pool("plant_all_cause", direct=True)["pooled"],
            "clean_plant_direct_outcome_hr": self._pool("plant_all_cause", direct=True, measure="HR")["pooled"],
        }
        for key, value in observed.items():
            with self.subTest(key=key):
                self.assertAlmostEqual(value, self.expected["strict_reference"][key], delta=5e-10)

    def test_proposed_targets_are_approximate_calibration_bands(self):
        target = self.expected["proposed_approximate_targets"]
        observed = {
            "published_total": self._pool("total_all_cause")["pooled"],
            "clean_total_direct_outcome": self._pool("total_all_cause", direct=True)["pooled"],
            "clean_total_direct_outcome_hr": self._pool("total_all_cause", direct=True, measure="HR")["pooled"],
            "published_plant": self._pool("plant_all_cause")["pooled"],
            "clean_plant_direct_outcome": self._pool("plant_all_cause", direct=True)["pooled"],
            "clean_plant_direct_outcome_hr": self._pool("plant_all_cause", direct=True, measure="HR")["pooled"],
        }
        for key, value in observed.items():
            with self.subTest(key=key):
                self.assertAlmostEqual(value, target[key], delta=target["tolerance"])

    def test_sensitivity_ladder_keeps_published_reconstruction_first(self):
        ladder = run_sensitivity_ladder(
            filter_records(self.records, analysis_id="total_all_cause"),
            tau2_method="DL",
            common_measure="HR",
            allow_mixed_estimands=True,
        )
        self.assertEqual(ladder[0]["id"], "S1_published_reconstruction")
        self.assertAlmostEqual(ladder[0]["result"]["pooled"], 0.9394212689, delta=5e-10)
        self.assertEqual(ladder[1]["id"], "S2_direct_outcomes")
        self.assertEqual(ladder[2]["id"], "S3_common_measure")


class MetaAnalysisGuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_records(FIXTURE)

    def test_mixed_estimands_are_rejected_by_default(self):
        records = filter_records(self.records, analysis_id="total_all_cause")
        with self.assertRaisesRegex(MetaAnalysisError, "Mixed effect measures"):
            meta_analysis(records, tau2_method="DL")

    def test_mixed_estimands_require_explicit_reproduction_override_and_warning(self):
        records = filter_records(self.records, analysis_id="total_all_cause")
        result = meta_analysis(records, tau2_method="DL", allow_mixed_estimands=True)
        self.assertTrue(any("does not harmonize estimands" in item for item in result["warnings"]))

    def test_multiple_analysis_ids_are_never_pooled(self):
        with self.assertRaisesRegex(MetaAnalysisError, "Multiple analysis_id"):
            meta_analysis(self.records, allow_mixed_estimands=True)

    def test_md_and_smd_cannot_use_mixed_reproduction_override(self):
        source = filter_records(self.records, analysis_id="total_all_cause", common_measure="HR")[:2]
        records = [replace(source[0], measure="MD"), replace(source[1], measure="SMD")]
        with self.assertRaisesRegex(MetaAnalysisError, "MD and SMD"):
            meta_analysis(records, allow_mixed_estimands=True)

    def test_invalid_provenance_and_source_conflict_are_reported(self):
        records = filter_records(self.records, analysis_id="total_all_cause")
        report = validate_records(records)
        codes = {issue["code"] for issue in report["issues"]}
        self.assertIn("INVALID_OR_UNJUSTIFIED_OUTCOME", codes)
        self.assertIn("SOURCE_CONFLICT_NOTE", codes)

    def test_unresolved_overlap_is_rejected(self):
        records = filter_records(self.records, analysis_id="total_all_cause", common_measure="HR")
        records = [
            replace(record, participant_overlap_possible=True, overlap_status="unresolved")
            if index == 0
            else replace(record)
            for index, record in enumerate(records)
        ]
        with self.assertRaisesRegex(MetaAnalysisError, "dependence"):
            meta_analysis(records, tau2_method="DL")

    def test_repeated_cohort_requires_explicit_resolved_independence(self):
        source = filter_records(self.records, analysis_id="total_all_cause", common_measure="HR")[:2]
        records = [
            replace(source[0], cohort_id="shared", overlap_status="none"),
            replace(source[1], cohort_id="shared", overlap_status="none"),
        ]
        with self.assertRaisesRegex(MetaAnalysisError, "Repeated cohort"):
            meta_analysis(records)
        report = validate_records(records)
        self.assertFalse(report["valid_for_defensible_default_pooling"])
        self.assertIn("UNRESOLVED_REPEATED_COHORT", {issue["code"] for issue in report["issues"]})

    def test_invalid_overlap_status_and_unsupported_modeled_dependence_are_errors(self):
        source = filter_records(self.records, analysis_id="total_all_cause", common_measure="HR")[:2]
        invalid = [replace(source[0], overlap_status="mystery"), replace(source[1])]
        modeled = [replace(source[0], overlap_status="modeled"), replace(source[1])]
        self.assertIn("INVALID_OVERLAP_STATUS", {item["code"] for item in validate_records(invalid)["issues"]})
        self.assertIn("DEPENDENCE_MODEL_NOT_SUPPORTED", {item["code"] for item in validate_records(modeled)["issues"]})

    def test_estimators_hksj_prediction_and_leave_one_out(self):
        records = filter_records(
            self.records,
            analysis_id="total_all_cause",
            direct_outcomes_only=True,
            common_measure="HR",
        )
        for method in ("DL", "PM", "REML"):
            with self.subTest(method=method):
                result = meta_analysis(records, tau2_method=method, inference="HKSJ", leave_one_out=True)
                self.assertGreaterEqual(result["tau2"], 0.0)
                self.assertLess(result["ci_lower"], result["pooled"])
                self.assertGreater(result["ci_upper"], result["pooled"])
                self.assertLess(result["prediction_lower"], result["prediction_upper"])
                self.assertEqual(len(result["leave_one_out"]), len({record.cohort_id for record in records}))

    def test_tau2_and_student_t_match_independent_scipy_references(self):
        records = filter_records(
            self.records,
            analysis_id="total_all_cause",
            direct_outcomes_only=True,
            common_measure="HR",
        )
        expected_tau2 = {
            "DL": 0.003312243622678547,
            "PM": 0.019391430872969552,
            "REML": 0.010886204568184623,
        }
        for method, expected in expected_tau2.items():
            with self.subTest(method=method):
                observed = meta_analysis(records, tau2_method=method)["tau2"]
                self.assertAlmostEqual(observed, expected, delta=1e-9)
        self.assertAlmostEqual(_student_t_quantile(0.975, 12), 2.1788128296672284, delta=1e-12)

    def test_input_confidence_is_separate_from_output_confidence(self):
        records = filter_records(
            self.records,
            analysis_id="total_all_cause",
            direct_outcomes_only=True,
            common_measure="HR",
        )
        ninety = meta_analysis(records, confidence=0.90, input_confidence=0.95)
        ninety_nine = meta_analysis(records, confidence=0.99, input_confidence=0.95)
        self.assertAlmostEqual(ninety["pooled"], ninety_nine["pooled"], delta=1e-14)
        self.assertAlmostEqual(ninety["tau2"], ninety_nine["tau2"], delta=1e-14)
        self.assertGreater(ninety_nine["ci_upper"] - ninety_nine["ci_lower"], ninety["ci_upper"] - ninety["ci_lower"])

    def test_hksj_and_prediction_interval_match_independent_references(self):
        records = filter_records(
            self.records,
            analysis_id="total_all_cause",
            direct_outcomes_only=True,
            common_measure="HR",
        )
        normal = meta_analysis(records, tau2_method="DL", inference="normal")
        hksj = meta_analysis(records, tau2_method="DL", inference="HKSJ")
        self.assertAlmostEqual(normal["ci_lower"], 0.9006422182365167, delta=1e-12)
        self.assertAlmostEqual(normal["ci_upper"], 1.0047111625274052, delta=1e-12)
        self.assertAlmostEqual(normal["prediction_lower"], 0.8275200024471621, delta=1e-12)
        self.assertAlmostEqual(normal["prediction_upper"], 1.0934905348870398, delta=1e-12)
        self.assertAlmostEqual(hksj["ci_lower"], 0.8760814699052611, delta=1e-12)
        self.assertAlmostEqual(hksj["ci_upper"], 1.0328780155611845, delta=1e-12)

    def test_fixed_model_has_no_prediction_interval_and_rejects_hksj(self):
        records = filter_records(self.records, analysis_id="total_all_cause", common_measure="HR")
        fixed = meta_analysis(records, model="fixed")
        self.assertIsNone(fixed["prediction_lower"])
        self.assertIsNone(fixed["prediction_upper"])
        with self.assertRaisesRegex(MetaAnalysisError, "only for random-effects"):
            meta_analysis(records, model="fixed", inference="HKSJ")

    def test_sparse_sensitivity_step_is_not_assessable_instead_of_crashing(self):
        source = filter_records(self.records, analysis_id="total_all_cause", common_measure="HR")[:2]
        records = [replace(record, outcome_provenance="DERIVED_INVALID_OR_UNJUSTIFIED") for record in source]
        ladder = run_sensitivity_ladder(records, common_measure="HR")
        self.assertEqual(ladder[1]["result"]["status"], "NOT_ASSESSABLE")

    def test_cli_json_and_forest_svg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            forest = Path(temp_dir) / "forest.svg"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "reconstruct_meta_analysis.py"),
                    str(FIXTURE),
                    "--analysis-id",
                    "total_all_cause",
                    "--tau2",
                    "DL",
                    "--allow-mixed-estimands",
                    "--forest",
                    str(forest),
                    "--title",
                    "Naghshi 2020 reconstruction",
                    "--json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(completed.stdout)
            self.assertAlmostEqual(payload["pooled"], 0.9394212689, delta=5e-10)
            self.assertTrue(forest.read_text().startswith("<svg"))
            self.assertIn("Naghshi", forest.read_text())

    def test_cli_blocks_sensitivities_when_published_reproduction_fails(self):
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
                "--expected-pooled",
                "2.0",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["sensitivity_status"], "BLOCKED_REPRODUCTION_FAILURE")
        self.assertEqual(payload["sensitivity_ladder"], [])

    def test_non_sensitivity_reproduction_failure_has_nonzero_exit(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "reconstruct_meta_analysis.py"),
                str(FIXTURE),
                "--analysis-id",
                "plant_all_cause",
                "--allow-mixed-estimands",
                "--expected-pooled",
                "2.0",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["published_reproduction"]["status"], "FAIL")

    def test_comparison_and_forest_outputs_preserve_warnings(self):
        comparison = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "compare_meta_models.py"),
                str(FIXTURE),
                "--analysis-id",
                "total_all_cause",
                "--allow-mixed-estimands",
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        models = json.loads(comparison.stdout)
        self.assertEqual(models[0]["measures"], ["HR", "OR", "RR"])
        self.assertTrue(any("does not harmonize estimands" in warning for warning in models[0]["warnings"]))

        with tempfile.TemporaryDirectory() as temp_dir:
            forest = Path(temp_dir) / "mixed.svg"
            plotted = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "plot_forest.py"),
                    str(FIXTURE),
                    str(forest),
                    "--analysis-id",
                    "total_all_cause",
                    "--allow-mixed-estimands",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(plotted.stdout)
            self.assertTrue(payload["warnings"])
            svg = forest.read_text()
            self.assertIn("WARNING:", svg)
            self.assertEqual(svg.count('text-anchor="middle"'), 5)


if __name__ == "__main__":
    unittest.main()
