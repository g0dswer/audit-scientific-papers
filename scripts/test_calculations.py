import json
import math
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from calculate_binary_effects import (  # noqa: E402
    _ceil_positive,
    analyze_binary,
    newcombe_difference_interval,
    wilson_interval,
)
from verify_continuous_result import (  # noqa: E402
    check_change_means,
    check_standardized_effect,
    reconstruct_from_ci,
)


class BinaryEffectTests(unittest.TestCase):
    def test_primary_example_crosses_zero_and_splits_reciprocal_interval(self):
        result = analyze_binary(16, 41, 12, 39)

        self.assertAlmostEqual(result["risk_difference"], 16 / 41 - 12 / 39, places=12)
        self.assertEqual(result["classification"], "inconclusive_crosses_zero")
        self.assertTrue(result["point_estimate"]["exploratory"])
        self.assertEqual(result["point_estimate"]["rounded"], 13)
        self.assertEqual(result["split_interval"]["benefit_from"], 4)
        self.assertEqual(result["split_interval"]["harm_from"], 9)

    def test_integer_reciprocal_is_not_rounded_up_by_float_noise(self):
        result = analyze_binary(30, 100, 10, 100)

        self.assertAlmostEqual(result["point_estimate"]["unrounded"], 5.0, places=14)
        self.assertEqual(result["point_estimate"]["rounded"], 5)
        self.assertEqual(_ceil_positive(5.0 + math.ulp(5.0)), 5)
        self.assertEqual(_ceil_positive(5.0 + 4.0 * math.ulp(5.0)), 6)

    def test_wilson_and_newcombe_values_match_independent_references(self):
        expected_wilson = {
            (16, 41): (0.25656145060123525, 0.5427314306587621),
            (12, 39): (0.18565932306911137, 0.464212543741493),
            (0, 10): (0.0, 0.27753279986288915),
            (31, 43): (0.5730897131812114, 0.832533862137625),
            (14, 42): (0.21012467072357263, 0.4844749262316619),
        }
        for counts, expected in expected_wilson.items():
            with self.subTest(counts=counts):
                observed = wilson_interval(*counts, 0.95)
                self.assertAlmostEqual(observed[0], expected[0], delta=1e-13)
                self.assertAlmostEqual(observed[1], expected[1], delta=1e-13)

        expected_newcombe = {
            (16, 41, 12, 39): (-0.12328713392759158, 0.27785775337621454),
            (31, 43, 14, 42): (0.17617173451283547, 0.5538369205115014),
            (0, 10, 0, 10): (-0.27753279986288915, 0.27753279986288915),
        }
        for counts, expected in expected_newcombe.items():
            with self.subTest(counts=counts):
                observed = newcombe_difference_interval(*counts, 0.95)
                self.assertAlmostEqual(observed[0], expected[0], delta=1e-13)
                self.assertAlmostEqual(observed[1], expected[1], delta=1e-13)

    def test_wilson_interval_is_bounded_and_handles_zero_cells(self):
        lower, upper = wilson_interval(0, 10, 0.95)
        self.assertEqual(lower, 0.0)
        self.assertGreater(upper, 0.0)

        lower, upper = wilson_interval(10, 10, 0.95)
        self.assertLess(lower, 1.0)
        self.assertEqual(upper, 1.0)

    def test_identical_risks_have_zero_point_difference(self):
        result = analyze_binary(5, 20, 5, 20)

        self.assertEqual(result["risk_difference"], 0.0)
        self.assertEqual(result["point_estimate"]["rounded"], None)
        self.assertEqual(result["classification"], "inconclusive_crosses_zero")

    def test_clear_benefit_has_finite_reciprocal_interval(self):
        result = analyze_binary(18, 20, 2, 20)

        self.assertEqual(result["classification"], "clear_benefit")
        self.assertEqual(result["point_estimate"]["label"], "NNT")
        self.assertFalse(result["point_estimate"]["exploratory"])
        self.assertIsNone(result["split_interval"])
        self.assertIsNotNone(result["reciprocal_interval"])
        self.assertGreater(result["reciprocal_interval"]["lower"], 0)
        self.assertGreater(result["reciprocal_interval"]["upper"], result["reciprocal_interval"]["lower"])

    def test_clear_harm_uses_nnh_when_event_is_beneficial(self):
        result = analyze_binary(2, 20, 18, 20)

        self.assertEqual(result["classification"], "clear_harm")
        self.assertEqual(result["point_estimate"]["label"], "NNH")
        self.assertIsNone(result["split_interval"])
        self.assertIsNotNone(result["reciprocal_interval"])

    def test_harm_flag_relabels_excess_undesirable_events(self):
        result = analyze_binary(31, 43, 14, 42, beneficial=False)

        self.assertEqual(result["classification"], "clear_harm")
        self.assertEqual(result["point_estimate"]["label"], "NNH")
        self.assertEqual(result["point_estimate"]["rounded"], 3)
        self.assertFalse(result["point_estimate"]["exploratory"])
        self.assertIsNone(result["split_interval"])
        self.assertEqual(result["reciprocal_interval"]["rounded_lower"], 2)
        self.assertEqual(result["reciprocal_interval"]["rounded_upper"], 6)

    def test_zero_cells_do_not_receive_continuity_correction(self):
        result = analyze_binary(0, 10, 0, 10)

        self.assertIsNone(result["risk_ratio"])
        self.assertIsNone(result["odds_ratio"])
        self.assertEqual(result["risk_difference"], 0.0)

    def test_invalid_counts_are_rejected(self):
        invalid = ((-1, 10, 0, 10), (11, 10, 0, 10), (0, 0, 0, 10), (0, 10, 1, 0))
        for counts in invalid:
            with self.subTest(counts=counts):
                with self.assertRaises(ValueError):
                    analyze_binary(*counts)

    def test_non_integer_counts_are_rejected(self):
        with self.assertRaises(ValueError):
            analyze_binary(1.5, 10, 0, 10)

    def test_confidence_must_be_between_zero_and_one(self):
        for confidence in (0, 1, -0.1, 1.1):
            with self.subTest(confidence=confidence):
                with self.assertRaises(ValueError):
                    analyze_binary(1, 10, 0, 10, confidence=confidence)

    def test_newcombe_interval_is_ordered(self):
        lower, upper = newcombe_difference_interval(16, 41, 12, 39, 0.95)

        self.assertLess(lower, upper)
        self.assertLess(lower, 16 / 41 - 12 / 39)
        self.assertGreater(upper, 16 / 41 - 12 / 39)

    def test_cli_json_and_harm_option(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "calculate_binary_effects.py"),
                "31",
                "43",
                "14",
                "42",
                "--harm",
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["point_estimate"]["rounded"], 3)
        self.assertEqual(payload["point_estimate"]["label"], "NNH")

    def test_human_cli_leads_with_inconclusive_effect_and_prints_intervals(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "calculate_binary_effects.py"),
                "16",
                "41",
                "12",
                "39",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        lines = completed.stdout.splitlines()
        self.assertTrue(lines[0].startswith("Binary effect inconclusive"))
        self.assertIn("Risk-difference 95% CI:", completed.stdout)
        self.assertIn("Split reciprocal interval:", completed.stdout)
        self.assertIn("possible benefit", completed.stdout)
        self.assertIn("possible harm", completed.stdout)


class ContinuousResultTests(unittest.TestCase):
    def test_reconstructs_approximate_se_statistics_and_asymmetry(self):
        result = reconstruct_from_ci(-4.04, -6.89, -1.18)

        self.assertAlmostEqual(result["standard_error_approx"], 1.456659, places=5)
        self.assertAlmostEqual(result["standard_error_lower_approx"], 1.454108, places=5)
        self.assertAlmostEqual(result["standard_error_upper_approx"], 1.459210, places=5)
        self.assertAlmostEqual(result["asymmetry_approx"], 0.005102, places=5)
        self.assertAlmostEqual(abs(result["z_statistic_approx"]), 2.775, delta=0.002)
        self.assertAlmostEqual(result["p_two_sided_approx"], 0.0055, delta=0.0002)
        self.assertEqual(result["approximation_label"], "approximate")
        self.assertTrue(result["approximate"])

    def test_reconstructs_nonstandard_confidence_and_reports_ci_asymmetry(self):
        nonstandard = reconstruct_from_ci(-4.04, -6.89, -1.18, confidence=0.90)
        self.assertAlmostEqual(nonstandard["critical_value_approx"], 1.644854, places=5)
        self.assertEqual(nonstandard["confidence"], 0.90)

        asymmetric = reconstruct_from_ci(10.0, 8.0, 15.0)
        self.assertGreater(asymmetric["standard_error_upper_approx"], asymmetric["standard_error_lower_approx"])
        self.assertGreater(asymmetric["asymmetry_approx"], 0.0)
        self.assertAlmostEqual(asymmetric["asymmetry_ratio_approx"], 2.5, places=12)

    def test_continuous_cli_text_output_labels_approximation(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_continuous_result.py"),
                "ci",
                "-4.04",
                "-6.89",
                "-1.18",
                "--confidence",
                "0.90",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Continuous result reconstruction: approximate", completed.stdout)
        self.assertIn("Approximate normal statistic:", completed.stdout)
        self.assertIn("Approximate two-sided p:", completed.stdout)

    def test_reconstruct_from_ci_rejects_nonfinite_or_misordered_inputs(self):
        invalid = (
            (float("nan"), -1.0, 1.0),
            (0.0, float("inf"), 1.0),
            (0.0, -1.0, float("-inf")),
            (0.0, 1.0, -1.0),
            (2.0, -1.0, 1.0),
        )
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    reconstruct_from_ci(*values)

        for confidence in (0.0, 1.0, float("nan"), float("inf")):
            with self.subTest(confidence=confidence):
                with self.assertRaises(ValueError):
                    reconstruct_from_ci(-1.0, -2.0, 0.0, confidence=confidence)

    def test_check_change_means_reports_raw_contrast_and_estimand_difference(self):
        result = check_change_means(41.54, 34.98, 39.51, 37.26, -4.04)

        self.assertAlmostEqual(result["change_treatment"], -6.56, places=12)
        self.assertAlmostEqual(result["change_control"], -2.25, places=12)
        self.assertAlmostEqual(result["raw_contrast"], -4.31, places=12)
        self.assertAlmostEqual(result["adjusted_minus_raw"], 0.27, places=12)
        self.assertIn("potentially different estimands", result["estimand_note"])

    def test_check_change_means_can_omit_adjusted_estimate(self):
        result = check_change_means(10.0, 7.0, 8.0, 8.5, None)

        self.assertAlmostEqual(result["raw_contrast"], -3.5, places=12)
        self.assertIsNone(result["adjusted_estimate"])
        self.assertIsNone(result["adjusted_minus_raw"])

    def test_check_change_means_rejects_nonfinite_inputs(self):
        with self.assertRaises(ValueError):
            check_change_means(float("nan"), 1.0, 0.0, 1.0, None)
        with self.assertRaises(ValueError):
            check_change_means(0.0, 1.0, 0.0, 1.0, float("inf"))

    def test_standardized_effect_reconstructs_d_and_hedges_g(self):
        result = check_standardized_effect(
            mean_difference=5.0,
            denominator_sd=10.0,
            n_treatment=25,
            n_control=25,
            reported_effect=0.49,
            reported_metric="hedges_g",
            tolerance=0.01,
        )

        expected_j = 1.0 - 3.0 / (4.0 * 48.0 - 1.0)
        self.assertAlmostEqual(result["cohens_d_approx"], 0.5, places=12)
        self.assertEqual(result["degrees_of_freedom"], 48)
        self.assertAlmostEqual(result["j_correction_approx"], expected_j, places=12)
        self.assertAlmostEqual(result["hedges_g_approx"], 0.5 * expected_j, places=12)
        self.assertEqual(result["df_source"], "two_independent_groups")
        self.assertIn("classical", result["validity_scope"])
        self.assertAlmostEqual(
            result["absolute_difference"], abs(0.5 * expected_j - 0.49), places=12
        )
        self.assertTrue(result["consistent_with_tolerance"])
        self.assertEqual(result["approximation_label"], "approximate")
        self.assertTrue(result["approximate"])
        self.assertIn("arithmetic", result["consistent_with_tolerance_note"])

    def test_standardized_effect_can_flag_reported_value_outside_tolerance(self):
        result = check_standardized_effect(
            5.0,
            10.0,
            25,
            25,
            reported_effect=0.65,
            reported_metric="hedges_g",
            tolerance=0.01,
        )

        self.assertFalse(result["consistent_with_tolerance"])
        self.assertGreater(result["absolute_difference"], 0.01)

    def test_standardized_effect_accepts_user_supplied_noninteger_df(self):
        result = check_standardized_effect(
            5.0,
            10.0,
            30,
            20,
            degrees_of_freedom=47.5,
        )

        expected_j = 1.0 - 3.0 / (4.0 * 47.5 - 1.0)
        self.assertEqual(result["degrees_of_freedom"], 47.5)
        self.assertEqual(result["df_source"], "user_supplied")
        self.assertIsNone(result["comparison_target"])
        self.assertIn("user-supplied", result["validity_scope"])
        self.assertAlmostEqual(result["j_correction_approx"], expected_j, places=12)
        self.assertAlmostEqual(result["hedges_g_approx"], 0.5 * expected_j, places=12)

    def test_standardized_effect_compares_the_explicit_reported_metric(self):
        d_result = check_standardized_effect(
            5.0,
            10.0,
            30,
            20,
            reported_effect=0.5,
            reported_metric="cohens_d",
            tolerance=0.001,
        )
        g_result = check_standardized_effect(
            5.0,
            10.0,
            30,
            20,
            reported_effect=d_result["hedges_g_approx"],
            reported_metric="hedges_g",
            tolerance=0.001,
        )

        self.assertEqual(d_result["comparison_target"], "cohens_d_approx")
        self.assertEqual(g_result["comparison_target"], "hedges_g_approx")
        self.assertAlmostEqual(d_result["absolute_difference"], 0.0, places=12)
        self.assertAlmostEqual(g_result["absolute_difference"], 0.0, places=12)
        self.assertTrue(d_result["consistent_with_tolerance"])
        self.assertTrue(g_result["consistent_with_tolerance"])

    def test_standardized_effect_rejects_ambiguous_reported_metric(self):
        with self.assertRaises(ValueError):
            check_standardized_effect(5.0, 10.0, 25, 25, reported_effect=0.5)
        with self.assertRaises(ValueError):
            check_standardized_effect(5.0, 10.0, 25, 25, reported_metric="cohens_d")
        with self.assertRaises(ValueError):
            check_standardized_effect(
                5.0,
                10.0,
                25,
                25,
                reported_effect=0.5,
                reported_metric="standardized_effect",
            )

    def test_standardized_effect_validates_sd_samples_and_comparison_inputs(self):
        invalid = (
            (5.0, 0.0, 25, 25),
            (5.0, -1.0, 25, 25),
            (5.0, 10.0, 1, 25),
            (5.0, 10.0, 25, 1),
            (5.0, 10.0, 25.5, 25),
        )
        for mean_difference, denominator_sd, n_treatment, n_control in invalid:
            with self.subTest(values=(mean_difference, denominator_sd, n_treatment, n_control)):
                with self.assertRaises(ValueError):
                    check_standardized_effect(
                        mean_difference, denominator_sd, n_treatment, n_control
                    )

        with self.assertRaises(ValueError):
            check_standardized_effect(
                5.0,
                10.0,
                25,
                25,
                reported_effect=float("nan"),
                reported_metric="hedges_g",
            )
        with self.assertRaises(ValueError):
            check_standardized_effect(5.0, 10.0, 25, 25, tolerance=-0.01)
        for degrees_of_freedom in (1.0, 0.0, -2.0, float("nan"), float("inf")):
            with self.subTest(degrees_of_freedom=degrees_of_freedom):
                with self.assertRaises(ValueError):
                    check_standardized_effect(
                        5.0,
                        10.0,
                        25,
                        25,
                        degrees_of_freedom=degrees_of_freedom,
                    )

    def test_continuous_cli_subcommands_emit_json(self):
        ci = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_continuous_result.py"),
                "ci",
                "-4.04",
                "-6.89",
                "-1.18",
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        ci_payload = json.loads(ci.stdout)
        self.assertEqual(ci_payload["approximation_label"], "approximate")

        changes = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_continuous_result.py"),
                "changes",
                "41.54",
                "34.98",
                "39.51",
                "37.26",
                "--adjusted-estimate",
                "-4.04",
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        changes_payload = json.loads(changes.stdout)
        self.assertAlmostEqual(changes_payload["raw_contrast"], -4.31, places=12)

        standardized = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_continuous_result.py"),
                "standardized",
                "5.0",
                "10.0",
                "25",
                "25",
                "--reported-effect",
                "0.49",
                "--reported-metric",
                "hedges_g",
                "--tolerance",
                "0.01",
                "--json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        standardized_payload = json.loads(standardized.stdout)
        self.assertAlmostEqual(standardized_payload["hedges_g_approx"], 0.5 * (1 - 3 / 191), places=12)
        self.assertTrue(standardized_payload["consistent_with_tolerance"])

        standardized_text = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_continuous_result.py"),
                "standardized",
                "5.0",
                "10.0",
                "30",
                "20",
                "--degrees-of-freedom",
                "47.5",
                "--reported-effect",
                "0.5",
                "--reported-metric",
                "cohens_d",
                "--tolerance",
                "0.01",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("df source: user_supplied", standardized_text.stdout)
        self.assertIn("Reported metric: cohens_d", standardized_text.stdout)
        self.assertIn("arithmetic check only", standardized_text.stdout)


if __name__ == "__main__":
    unittest.main()
