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
    VALID_OVERLAP_STATUSES,
    MetaAnalysisError,
    _student_t_quantile,
    filter_records,
    load_records,
    meta_analysis,
    run_sensitivity_ladder,
)
from plot_forest import write_forest_svg  # noqa: E402
from validate_meta_dataset import validate_records  # noqa: E402


CSV_HEADER = (
    "analysis_id,study_id,citation,cohort_id,effect,lower,upper,measure,"
    "outcome_provenance,exposure_provenance,participant_overlap_possible,"
    "overlap_status,include_published,input_confidence\n"
)


def _write_csv(directory, rows):
    path = Path(directory) / "dataset.csv"
    path.write_text(CSV_HEADER + "".join(rows), encoding="utf-8")
    return path


def _row(study_id, effect, lower, upper, *, overlap_status="none", input_confidence="", cohort_id=None):
    return (
        f"pool,{study_id},{study_id} 2020,{cohort_id or study_id},{effect},{lower},{upper},HR,"
        f"DIRECT,DIRECT,false,{overlap_status},true,{input_confidence}\n"
    )


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
        for step in ladder:
            with self.subTest(step=step["id"]):
                self.assertEqual(step["model"], "random")

    def test_sensitivity_ladder_honours_a_fixed_effect_request(self):
        records = filter_records(self.records, analysis_id="total_all_cause")
        gate = meta_analysis(
            records, model="fixed", tau2_method="DL", allow_mixed_estimands=True
        )
        ladder = run_sensitivity_ladder(
            records,
            model="fixed",
            tau2_method="DL",
            common_measure="HR",
            allow_mixed_estimands=True,
        )
        steps = {step["id"]: step for step in ladder}
        # S1 must reproduce the very model the reproduction gate validated.
        self.assertAlmostEqual(
            steps["S1_published_reconstruction"]["result"]["pooled"], gate["pooled"], delta=5e-13
        )
        self.assertAlmostEqual(gate["pooled"], 0.9892243768546655, delta=5e-10)
        for step_id in ("S1_published_reconstruction", "S2_direct_outcomes", "S3_common_measure",
                        "S4_direct_outcome_common_measure", "S5_direct_exposure",
                        "S8_leave_one_cluster_out"):
            with self.subTest(step=step_id):
                self.assertEqual(steps[step_id]["model"], "fixed")
                self.assertEqual(steps[step_id]["result"]["model"], "fixed")
                self.assertEqual(steps[step_id]["result"]["tau2"], 0.0)
        # Random-effects-only rungs must not publish numbers under a fixed heading.
        for step_id in ("S6_alternative_tau2", "S7_hksj"):
            with self.subTest(step=step_id):
                self.assertEqual(steps[step_id]["result"]["status"], "NOT_ASSESSABLE")
                self.assertEqual(steps[step_id]["result"]["model"], "fixed")
                self.assertIn("random-effects", steps[step_id]["result"]["reason"])
        random_ladder = run_sensitivity_ladder(
            records, model="random", tau2_method="DL", common_measure="HR", allow_mixed_estimands=True
        )
        self.assertAlmostEqual(
            random_ladder[0]["result"]["pooled"], 0.9394212689, delta=5e-10
        )


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
        # Default convention is Student t on k-2 degrees of freedom (Cochrane
        # Handbook; Higgins-Thompson-Spiegelhalter 2009; IntHout 2016).
        self.assertEqual(normal["prediction_df_convention"], "k-2")
        self.assertEqual(normal["prediction_interval_df"], 11)
        self.assertAlmostEqual(normal["prediction_lower"], 0.8263473638682611, delta=1e-12)
        self.assertAlmostEqual(normal["prediction_upper"], 1.0950422663294554, delta=1e-12)
        self.assertAlmostEqual(hksj["ci_lower"], 0.8760814699052611, delta=1e-12)
        self.assertAlmostEqual(hksj["ci_upper"], 1.0328780155611845, delta=1e-12)

    def test_prediction_interval_conventions_and_degenerate_degrees_of_freedom(self):
        records = filter_records(
            self.records,
            analysis_id="total_all_cause",
            direct_outcomes_only=True,
            common_measure="HR",
        )
        legacy = meta_analysis(records, tau2_method="DL", inference="normal", prediction_df="k-1")
        self.assertEqual(legacy["prediction_df_convention"], "k-1")
        self.assertEqual(legacy["prediction_interval_df"], 12)
        self.assertAlmostEqual(legacy["prediction_lower"], 0.8275200024471621, delta=1e-12)
        self.assertAlmostEqual(legacy["prediction_upper"], 1.0934905348870398, delta=1e-12)
        with self.assertRaisesRegex(MetaAnalysisError, "prediction_df must be"):
            meta_analysis(records, prediction_df="k-3")
        pair = meta_analysis(records[:2])
        self.assertIsNone(pair["prediction_lower"])
        self.assertIsNone(pair["prediction_interval_df"])
        self.assertIn("not estimable", pair["prediction_not_estimable_reason"])
        self.assertAlmostEqual(
            meta_analysis(records[:2], prediction_df="k-1")["prediction_interval_df"], 1
        )

    def test_prediction_interval_does_not_depend_on_hksj_inference(self):
        records = filter_records(
            self.records,
            analysis_id="total_all_cause",
            direct_outcomes_only=True,
            common_measure="HR",
        )
        normal = meta_analysis(records, tau2_method="DL", inference="normal")
        hksj = meta_analysis(records, tau2_method="DL", inference="HKSJ")
        self.assertAlmostEqual(normal["tau2"], hksj["tau2"], delta=1e-14)
        # The prediction interval describes the distribution of true effects and is
        # always built from the conventional standard error.
        self.assertAlmostEqual(hksj["prediction_lower"], normal["prediction_lower"], delta=1e-14)
        self.assertAlmostEqual(hksj["prediction_upper"], normal["prediction_upper"], delta=1e-14)

    def test_degenerate_hksj_scale_factor_is_not_estimable(self):
        source = filter_records(self.records, analysis_id="total_all_cause", common_measure="HR")[:3]
        identical = [replace(record, effect=0.74, lower=0.60, upper=0.91) for record in source]
        self.assertAlmostEqual(meta_analysis(identical)["pooled"], 0.74, delta=1e-12)
        with self.assertRaisesRegex(MetaAnalysisError, "not estimable"):
            meta_analysis(identical, inference="HKSJ")

    def test_ratio_and_linear_measures_report_the_actual_incompatibility(self):
        source = filter_records(self.records, analysis_id="total_all_cause", common_measure="HR")[:2]
        mixed_scales = [replace(source[0]), replace(source[1], measure="MD")]
        with self.assertRaisesRegex(MetaAnalysisError, "Ratio measures cannot be pooled with linear"):
            meta_analysis(mixed_scales, allow_mixed_estimands=True)

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

    def test_unknown_overlap_status_is_rejected_at_load_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = _write_csv(
                temp_dir,
                [
                    _row("A", 0.90, 0.80, 1.01, overlap_status="unresolvd"),
                    _row("B", 0.95, 0.85, 1.06),
                ],
            )
            with self.assertRaisesRegex(MetaAnalysisError, "Unknown overlap status .*at row 2"):
                load_records(dataset)

    def test_unknown_overlap_status_never_pools_silently(self):
        source = filter_records(self.records, analysis_id="total_all_cause", common_measure="HR")[:3]
        for status in ("unresolvd", "pending"):
            with self.subTest(status=status):
                records = [
                    replace(source[0], participant_overlap_possible=True, overlap_status=status),
                    replace(source[1]),
                    replace(source[2]),
                ]
                with self.assertRaisesRegex(MetaAnalysisError, "Unknown overlap status"):
                    meta_analysis(records)
                self.assertIn(
                    "INVALID_OVERLAP_STATUS",
                    {issue["code"] for issue in validate_records(records)["issues"]},
                )
        self.assertEqual(len(VALID_OVERLAP_STATUSES), 7)
        self.assertIn("possible", VALID_OVERLAP_STATUSES)

    def test_per_row_input_confidence_overrides_the_global_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            mixed = load_records(
                _write_csv(
                    temp_dir,
                    [
                        _row("A", 0.90, 0.80, 1.01, input_confidence="0.90"),
                        _row("B", 0.95, 0.85, 1.06),
                    ],
                )
            )
        self.assertEqual(mixed[0].input_confidence, 0.90)
        self.assertIsNone(mixed[1].input_confidence)
        result = meta_analysis(mixed)
        self.assertEqual(result["input_confidence_levels"], [0.90, 0.95])
        uniform = [replace(record, input_confidence=None) for record in mixed]
        self.assertEqual(meta_analysis(uniform)["input_confidence_levels"], [0.95])
        # A 90% source interval implies a larger standard error, so the row is
        # down-weighted relative to the same row read as a 95% interval.
        self.assertLess(
            result["study_weights_percent"][0]["weight"],
            meta_analysis(uniform)["study_weights_percent"][0]["weight"],
        )
        # A per-row value equal to the global default reproduces it exactly.
        pinned = [replace(record, input_confidence=0.95) for record in mixed]
        self.assertAlmostEqual(
            meta_analysis(pinned)["pooled"], meta_analysis(uniform)["pooled"], delta=1e-15
        )

    def test_invalid_per_row_input_confidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = _write_csv(
                temp_dir,
                [
                    _row("A", 0.90, 0.80, 1.01, input_confidence="95"),
                    _row("B", 0.95, 0.85, 1.06),
                ],
            )
            with self.assertRaisesRegex(MetaAnalysisError, "input_confidence must be strictly"):
                load_records(dataset)
            dataset = _write_csv(
                temp_dir,
                [
                    _row("A", 0.90, 0.80, 1.01, input_confidence="ninety"),
                    _row("B", 0.95, 0.85, 1.06),
                ],
            )
            with self.assertRaisesRegex(MetaAnalysisError, "Invalid row 2"):
                load_records(dataset)

    def test_forest_squares_use_row_weights_not_study_id_lookup(self):
        source = filter_records(self.records, analysis_id="total_all_cause", common_measure="HR")
        duplicated = [
            replace(source[0], study_id="Shared", cohort_id="c1", citation="First row"),
            replace(source[5], study_id="Shared", cohort_id="c2", citation="Second row"),
            replace(source[7], study_id="Other", cohort_id="c3", citation="Third row"),
        ]
        result = meta_analysis(duplicated)
        weights = [item["weight"] for item in result["study_weights_percent"]]
        self.assertNotAlmostEqual(weights[0], weights[1], places=3)
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "duplicate.svg"
            write_forest_svg(duplicated, result, destination)
            sides = [
                float(fragment.split('width="')[1].split('"')[0])
                for fragment in destination.read_text().splitlines()
                if fragment.startswith("<rect x=")
            ]
        self.assertEqual(len(sides), len(duplicated))
        self.assertNotAlmostEqual(sides[0], sides[1], places=3)

    def test_forest_omits_the_null_line_when_it_is_off_scale(self):
        source = filter_records(self.records, analysis_id="total_all_cause", common_measure="HR")[:3]
        far = [
            replace(record, effect=2.0 + index, lower=1.8 + index, upper=2.4 + index)
            for index, record in enumerate(source)
        ]
        # A fixed-effect fit keeps the plotted range entirely above the null.
        result = meta_analysis(far, model="fixed")
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "offscale.svg"
            write_forest_svg(far, result, destination)
            svg = destination.read_text()
        self.assertNotIn("stroke-dasharray", svg)

    def test_secondary_entry_points_report_guardrails_without_a_traceback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dependent = Path(temp_dir) / "dependent.csv"
            dependent.write_text(
                FIXTURE.read_text().replace(",false,none,", ",true,unresolved,"), encoding="utf-8"
            )
            blocked = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "compare_meta_models.py"),
                    str(dependent),
                    "--analysis-id",
                    "total_all_cause",
                    "--common-measure",
                    "HR",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertNotIn("Traceback", blocked.stderr)
            self.assertTrue(blocked.stderr.startswith("error: "))
            allowed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "compare_meta_models.py"),
                    str(dependent),
                    "--analysis-id",
                    "total_all_cause",
                    "--common-measure",
                    "HR",
                    "--allow-dependence",
                    "--json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(json.loads(allowed.stdout)[0]["warnings"])

            forest = Path(temp_dir) / "blocked.svg"
            plotted = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "plot_forest.py"),
                    str(dependent),
                    str(forest),
                    "--analysis-id",
                    "total_all_cause",
                    "--common-measure",
                    "HR",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(plotted.returncode, 0)
            self.assertNotIn("Traceback", plotted.stderr)
            self.assertTrue(plotted.stderr.startswith("error: "))

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
