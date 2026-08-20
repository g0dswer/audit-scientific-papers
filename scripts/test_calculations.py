import contextlib
import io
import json
import math
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from statistics import NormalDist


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import calculate_binary_effects  # noqa: E402
from calculate_binary_effects import (  # noqa: E402
    _ceil_positive,
    _cli_direction,
    _fisher_exact_two_sided,
    _odds_ratio_interval,
    _risk_ratio_interval,
    _split_reciprocal_interval,
    analyze_binary,
    newcombe_difference_interval,
    wilson_interval,
)
import verify_continuous_result as vcr  # noqa: E402
from verify_continuous_result import (  # noqa: E402
    check_change_means,
    check_standardized_effect,
    reconstruct_from_ci,
    reconstruct_from_row,
)


_CRITICAL_VALUE_95 = NormalDist().inv_cdf(0.975)


def back_geometric_mean(result):
    """Convenience accessor for the back-transformed interval geometric mean."""

    return result["back_transformed"]["interval_geometric_mean"]


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

    def test_relative_effect_intervals_match_hand_worked_log_scale_values(self):
        # Worked example with cells a=15, b=85, c=5, d=95.
        # Katz: log RR = log 3, SE = sqrt(1/15 - 1/100 + 1/5 - 1/100) = 0.4966555.
        # Woolf: log OR = log 3.352941, SE = sqrt(1/15 + 1/85 + 1/5 + 1/95) = 0.5375478.
        result = analyze_binary(15, 100, 5, 100, beneficial=True)

        risk_ratio_ci = result["risk_ratio_ci"]
        odds_ratio_ci = result["odds_ratio_ci"]
        self.assertAlmostEqual(result["risk_ratio"], 3.0, places=12)
        self.assertAlmostEqual(risk_ratio_ci["log_standard_error"], 0.49665548085838, places=12)
        self.assertAlmostEqual(risk_ratio_ci["lower"], 1.1333585961897887, delta=1e-12)
        self.assertAlmostEqual(risk_ratio_ci["upper"], 7.940999459709293, delta=1e-12)
        self.assertEqual(risk_ratio_ci["method"], "katz_log")
        self.assertTrue(risk_ratio_ci["approximate"])

        self.assertAlmostEqual(result["odds_ratio"], 3.3529411764705883, places=12)
        self.assertAlmostEqual(odds_ratio_ci["log_standard_error"], 0.53754784748755, places=12)
        self.assertAlmostEqual(odds_ratio_ci["lower"], 1.1691342325734828, delta=1e-12)
        self.assertAlmostEqual(odds_ratio_ci["upper"], 9.61584582817814, delta=1e-12)
        self.assertEqual(odds_ratio_ci["method"], "woolf_log")
        self.assertIn("continuity correction", result["relative_effect_note"])

    def test_relative_effect_intervals_are_null_when_a_cell_is_zero(self):
        no_events_in_treatment = analyze_binary(0, 10, 5, 10, beneficial=True)
        self.assertEqual(no_events_in_treatment["risk_ratio"], 0.0)
        self.assertIsNone(no_events_in_treatment["risk_ratio_ci"])
        self.assertEqual(no_events_in_treatment["odds_ratio"], 0.0)
        self.assertIsNone(no_events_in_treatment["odds_ratio_ci"])

        no_events_in_control = analyze_binary(5, 10, 0, 10, beneficial=True)
        self.assertIsNone(no_events_in_control["risk_ratio"])
        self.assertIsNone(no_events_in_control["risk_ratio_ci"])
        self.assertIsNone(no_events_in_control["odds_ratio"])
        self.assertIsNone(no_events_in_control["odds_ratio_ci"])

        all_events_in_treatment = analyze_binary(10, 10, 5, 10, beneficial=True)
        self.assertIsNotNone(all_events_in_treatment["risk_ratio_ci"])
        self.assertIsNone(all_events_in_treatment["odds_ratio_ci"])

        self.assertIsNone(_risk_ratio_interval(0, 10, 0, 10, 0.95))
        self.assertIsNone(_odds_ratio_interval(0, 10, 0, 10, 0.95))

    def test_unspecified_event_direction_is_announced_not_silent(self):
        assumed = analyze_binary(16, 41, 12, 39)
        self.assertFalse(assumed["event_direction_specified"])
        self.assertTrue(assumed["beneficial_event"])
        self.assertEqual(assumed["event_direction"], "beneficial")
        self.assertIn("NOT SPECIFIED", assumed["event_direction_notice"])
        self.assertIn("--harm", assumed["event_direction_notice"])

        stated_benefit = analyze_binary(16, 41, 12, 39, beneficial=True)
        self.assertTrue(stated_benefit["event_direction_specified"])
        self.assertIsNone(stated_benefit["event_direction_notice"])
        self.assertEqual(stated_benefit["event_direction"], "beneficial")

        stated_harm = analyze_binary(16, 41, 12, 39, beneficial=False)
        self.assertTrue(stated_harm["event_direction_specified"])
        self.assertIsNone(stated_harm["event_direction_notice"])
        self.assertEqual(stated_harm["event_direction"], "harmful")

        # The assumed default must not move any number relative to --benefit.
        self.assertEqual(assumed["classification"], stated_benefit["classification"])
        self.assertEqual(
            assumed["point_estimate"]["unrounded"],
            stated_benefit["point_estimate"]["unrounded"],
        )

    def test_direction_flags_map_to_the_beneficial_argument(self):
        self.assertIsNone(_cli_direction(False, False))
        self.assertFalse(_cli_direction(True, False))
        self.assertTrue(_cli_direction(False, True))

        with self.assertRaises(ValueError):
            analyze_binary(1, 10, 1, 10, beneficial="yes")

    def test_cli_direction_flags_and_notice(self):
        script = str(SCRIPT_DIR / "calculate_binary_effects.py")
        counts = ["16", "41", "12", "39"]

        default_run = subprocess.run(
            [sys.executable, script, *counts], check=True, capture_output=True, text=True
        )
        self.assertIn("EVENT DIRECTION NOT SPECIFIED", default_run.stdout)

        default_json = json.loads(
            subprocess.run(
                [sys.executable, script, *counts, "--json"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        self.assertFalse(default_json["event_direction_specified"])
        self.assertIn("NOT SPECIFIED", default_json["event_direction_notice"])

        benefit_json = json.loads(
            subprocess.run(
                [sys.executable, script, *counts, "--benefit", "--json"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        self.assertTrue(benefit_json["event_direction_specified"])
        self.assertIsNone(benefit_json["event_direction_notice"])
        self.assertEqual(benefit_json["event_direction"], "beneficial")

        harm_json = json.loads(
            subprocess.run(
                [sys.executable, script, *counts, "--harm", "--json"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        self.assertEqual(harm_json["event_direction"], "harmful")
        self.assertIsNone(harm_json["event_direction_notice"])

        conflicting = subprocess.run(
            [sys.executable, script, *counts, "--harm", "--benefit"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(conflicting.returncode, 0)
        self.assertIn("not allowed with argument", conflicting.stderr)

    def test_cli_prints_relative_effects_with_intervals(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "calculate_binary_effects.py"),
                "15",
                "100",
                "5",
                "100",
                "--benefit",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Risk ratio: 3 (large-sample 95% CI [1.13336, 7.941], katz_log)", completed.stdout)
        self.assertIn("Odds ratio: 3.35294 (large-sample 95% CI [1.16913, 9.61585], woolf_log)", completed.stdout)

        zero_cell = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "calculate_binary_effects.py"),
                "0",
                "10",
                "5",
                "10",
                "--benefit",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("CI undefined: zero cell", zero_cell.stdout)

    def test_split_reciprocal_interval_bounds_are_unbounded_nulls(self):
        both_sides = _split_reciprocal_interval(-0.2, 0.25)
        self.assertEqual(both_sides["benefit_from"], 4)
        self.assertEqual(both_sides["harm_from"], 5)
        self.assertIsNone(both_sides["benefit_to"])
        self.assertIsNone(both_sides["harm_to"])

        benefit_only = _split_reciprocal_interval(0.0, 0.25)
        self.assertEqual(benefit_only["benefit_from"], 4)
        self.assertIsNone(benefit_only["harm_from"])

        harm_only = _split_reciprocal_interval(-0.2, 0.0)
        self.assertIsNone(harm_only["benefit_from"])
        self.assertEqual(harm_only["harm_from"], 5)

    def test_human_output_never_prints_a_none_reciprocal_bound(self):
        result = analyze_binary(16, 41, 12, 39, beneficial=True)
        result["split_interval"] = _split_reciprocal_interval(0.0, 0.25)
        original = calculate_binary_effects.analyze_binary
        calculate_binary_effects.analyze_binary = lambda *args, **kwargs: result
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                calculate_binary_effects.main(["16", "41", "12", "39", "--benefit"])
        finally:
            calculate_binary_effects.analyze_binary = original
        output = buffer.getvalue()
        self.assertIn("Split reciprocal interval:", output)
        self.assertIn("no possible harm side", output)
        self.assertNotIn("None", output)


class FisherOptionalDependencyTests(unittest.TestCase):
    """The optional SciPy path must degrade, never crash the calculator."""

    def setUp(self):
        self._saved = {
            name: sys.modules[name]
            for name in ("scipy", "scipy.stats")
            if name in sys.modules
        }

    def tearDown(self):
        for name in ("scipy", "scipy.stats"):
            sys.modules.pop(name, None)
        sys.modules.update(self._saved)

    @staticmethod
    def _install_fake_scipy(fisher_exact):
        scipy = types.ModuleType("scipy")
        stats = types.ModuleType("scipy.stats")
        stats.fisher_exact = fisher_exact
        scipy.stats = stats
        sys.modules["scipy"] = scipy
        sys.modules["scipy.stats"] = stats

    def test_absent_scipy_degrades_to_none(self):
        sys.modules.pop("scipy", None)
        sys.modules.pop("scipy.stats", None)
        self.assertIsNone(_fisher_exact_two_sided(15, 100, 5, 100))
        self.assertIsNone(analyze_binary(15, 100, 5, 100)["fisher_exact_p_two_sided"])

    def test_modern_scipy_result_object_is_used(self):
        class SignificanceResult(tuple):
            @property
            def pvalue(self):
                return self[1]

        self._install_fake_scipy(
            lambda table, alternative=None: SignificanceResult((3.35, 0.0325))
        )
        self.assertAlmostEqual(_fisher_exact_two_sided(15, 100, 5, 100), 0.0325, places=12)

    def test_legacy_scipy_tuple_is_accepted(self):
        self._install_fake_scipy(lambda table, alternative=None: (3.35, 0.0325))
        self.assertAlmostEqual(_fisher_exact_two_sided(15, 100, 5, 100), 0.0325, places=12)
        self.assertAlmostEqual(
            analyze_binary(15, 100, 5, 100)["fisher_exact_p_two_sided"], 0.0325, places=12
        )

    def test_raising_scipy_does_not_break_the_calculator(self):
        def explode(table, alternative=None):
            raise RuntimeError("legacy SciPy failure")

        self._install_fake_scipy(explode)
        self.assertIsNone(_fisher_exact_two_sided(15, 100, 5, 100))
        result = analyze_binary(15, 100, 5, 100)
        self.assertIsNone(result["fisher_exact_p_two_sided"])
        self.assertAlmostEqual(result["risk_ratio"], 3.0, places=12)


class ContinuousResultTests(unittest.TestCase):
    def test_ratio_scale_uses_the_log_scale_and_a_null_of_one(self):
        # Hazard ratio 0.75 (0.60 to 0.94): SE(log HR) = 0.11453, z = -2.51184,
        # two-sided p = 0.0120. The interval is essentially symmetric on the
        # log scale, so log-scale asymmetry must be ~0.
        result = reconstruct_from_ci(0.75, 0.60, 0.94, scale="ratio")

        self.assertEqual(result["scale"], "ratio")
        self.assertEqual(result["analysis_scale"], "log")
        self.assertEqual(result["null_value"], 1.0)
        self.assertAlmostEqual(result["analysis_estimate"], math.log(0.75), places=12)
        self.assertAlmostEqual(result["standard_error_approx"], 0.11453, places=5)
        self.assertAlmostEqual(result["z_statistic_approx"], -2.51184, places=5)
        self.assertAlmostEqual(result["p_two_sided_approx"], 0.0120, delta=0.0001)
        self.assertAlmostEqual(result["asymmetry_approx"], 0.0, delta=0.002)
        self.assertAlmostEqual(result["asymmetry_ratio_approx"], 1.0, delta=0.02)
        self.assertIsNone(result["scale_warning"])
        self.assertIn("log scale", result["scale_note"])

        back = result["back_transformed"]
        self.assertAlmostEqual(back["estimate"], 0.75, places=12)
        self.assertAlmostEqual(back["lower"], 0.60, places=12)
        self.assertAlmostEqual(back["upper"], 0.94, places=12)
        self.assertAlmostEqual(back["interval_geometric_mean"], 0.75, delta=0.002)
        self.assertAlmostEqual(
            back["standard_error_multiplicative"],
            math.exp(result["standard_error_approx"]),
            places=12,
        )

    def test_exactly_log_symmetric_ratio_has_zero_log_asymmetry(self):
        result = reconstruct_from_ci(2.0, 1.0, 4.0, scale="ratio")

        expected_se = math.log(2.0) / _CRITICAL_VALUE_95
        self.assertAlmostEqual(result["asymmetry_approx"], 0.0, places=12)
        self.assertAlmostEqual(result["asymmetry_ratio_approx"], 1.0, places=12)
        self.assertAlmostEqual(result["standard_error_approx"], expected_se, places=12)
        self.assertAlmostEqual(
            result["z_statistic_approx"], math.log(2.0) / expected_se, places=12
        )
        self.assertAlmostEqual(back_geometric_mean(result), 2.0, places=12)

    def test_ratio_scale_requires_strictly_positive_values(self):
        invalid = ((0.0, -1.0, 1.0), (1.0, 0.0, 2.0), (-1.0, -2.0, -0.5))
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    reconstruct_from_ci(*values, scale="ratio")

        with self.assertRaises(ValueError):
            reconstruct_from_ci(0.75, 0.60, 0.94, scale="log")

    def test_linear_path_is_unchanged_and_states_its_null(self):
        result = reconstruct_from_ci(-4.04, -6.89, -1.18, scale="linear")

        self.assertEqual(result["scale"], "linear")
        self.assertEqual(result["analysis_scale"], "identity")
        self.assertEqual(result["null_value"], 0.0)
        self.assertIsNone(result["back_transformed"])
        self.assertIsNone(result["scale_warning"])
        self.assertAlmostEqual(result["standard_error_approx"], 1.456659, places=5)
        self.assertAlmostEqual(result["p_two_sided_approx"], 0.0055, delta=0.0002)
        self.assertIn("null of 0", result["scale_note"])

    def test_linear_path_warns_when_the_input_looks_like_a_ratio(self):
        warned = reconstruct_from_ci(0.75, 0.60, 0.94, scale="linear")
        self.assertIsNotNone(warned["scale_warning"])
        self.assertIn("--scale ratio", warned["scale_warning"])
        # The heuristic only warns: the linear numbers are untouched.
        self.assertAlmostEqual(warned["z_statistic_approx"], 0.75 / warned["standard_error_approx"], places=12)
        self.assertEqual(warned["null_value"], 0.0)

        for values in (
            (-4.04, -6.89, -1.18),  # negative estimate: cannot be a ratio
            (10.0, 8.0, 15.0),  # positive but asymmetric on the log scale too
            (2.0, 1.0, 3.0),  # symmetric on the linear scale
        ):
            with self.subTest(values=values):
                self.assertIsNone(reconstruct_from_ci(*values, scale="linear")["scale_warning"])

    def test_scale_is_mandatory_because_the_warning_cannot_catch_every_ratio(self):
        # No default is allowed on either the CLI or the Python entry point.
        # The heuristic is a second net, not the primary defence: a ratio close
        # to the null with a narrow interval is near-symmetric on both scales,
        # so nothing can fire, yet the linear path is badly wrong.
        missing = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_continuous_result.py"),
                "ci",
                "0.98",
                "0.94",
                "1.02",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("--measure", missing.stderr)
        self.assertIn("--scale", missing.stderr)

        with self.assertRaisesRegex(ValueError, "exactly one of scale"):
            reconstruct_from_ci(0.98, 0.94, 1.02)

        # The undetectable case: no warning is possible, and the two scales
        # disagree by roughly fifty standard errors.
        linear = reconstruct_from_ci(0.98, 0.94, 1.02, scale="linear")
        ratio = reconstruct_from_ci(0.98, 0.94, 1.02, scale="ratio")
        self.assertIsNone(linear["scale_warning"])
        self.assertGreater(linear["absolute_z_statistic_approx"], 40.0)
        self.assertLess(ratio["absolute_z_statistic_approx"], 1.5)
        self.assertAlmostEqual(ratio["p_two_sided_approx"], 0.332, delta=0.01)

    def test_measure_vocabulary_matches_the_meta_analysis_engine(self):
        # The calculator keeps its own copy so it stays standalone, but a row
        # extracted for the meta engine must be accepted here unchanged.
        import reconstruct_meta_analysis as engine

        self.assertEqual(vcr.RATIO_MEASURES, engine.RATIO_MEASURES)
        self.assertEqual(vcr.LINEAR_MEASURES, engine.LINEAR_MEASURES)
        self.assertFalse(vcr.RATIO_MEASURES & vcr.LINEAR_MEASURES)

    def test_measure_derives_the_scale_and_is_reported_back(self):
        for measure in sorted(vcr.RATIO_MEASURES):
            with self.subTest(measure=measure):
                result = reconstruct_from_ci(0.75, 0.60, 0.94, measure=measure)
                self.assertEqual(result["scale"], "ratio")
                self.assertEqual(result["measure"], measure)
                self.assertEqual(result["scale_source"], "measure")
                self.assertEqual(result["null_value"], 1.0)
                self.assertAlmostEqual(result["p_two_sided_approx"], 0.0120102, delta=1e-6)

        for measure in sorted(vcr.LINEAR_MEASURES):
            with self.subTest(measure=measure):
                result = reconstruct_from_ci(-4.04, -6.89, -1.18, measure=measure)
                self.assertEqual(result["scale"], "linear")
                self.assertEqual(result["measure"], measure)
                self.assertEqual(result["null_value"], 0.0)

        # Lower case and stray whitespace are normalised, not rejected.
        self.assertEqual(
            reconstruct_from_ci(0.75, 0.60, 0.94, measure=" hr ")["measure"], "HR"
        )
        # Naming the scale directly leaves measure unset.
        direct = reconstruct_from_ci(0.75, 0.60, 0.94, scale="ratio")
        self.assertIsNone(direct["measure"])
        self.assertEqual(direct["scale_source"], "scale")

    def test_measure_and_scale_are_mutually_exclusive_and_measure_is_validated(self):
        with self.assertRaisesRegex(ValueError, "exactly one of scale"):
            reconstruct_from_ci(0.75, 0.60, 0.94, scale="ratio", measure="HR")
        with self.assertRaisesRegex(ValueError, "unknown effect measure"):
            reconstruct_from_ci(0.75, 0.60, 0.94, measure="RD")
        with self.assertRaisesRegex(ValueError, "measure HR requires strictly positive"):
            reconstruct_from_ci(-1.0, -2.0, -0.5, measure="HR")

        both = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_continuous_result.py"),
                "ci", "0.75", "0.60", "0.94", "--measure", "HR", "--scale", "ratio",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(both.returncode, 0)
        self.assertIn("not allowed with argument", both.stderr)

    def test_measure_path_still_runs_the_ratio_guard_on_a_mislabeled_linear_measure(self):
        # A row labelled MD whose interval has the signature of an unlogged
        # ratio must still be flagged: the measure column can itself be wrong.
        result = reconstruct_from_ci(0.75, 0.60, 0.94, measure="MD")
        self.assertEqual(result["scale"], "linear")
        self.assertIsNotNone(result["scale_warning"])
        self.assertIn("--scale ratio", result["scale_warning"])

    def test_row_reads_measure_and_interval_from_the_dataset(self):
        fixture = str(
            Path(__file__).resolve().parent.parent
            / "tests" / "fixtures" / "naghshi_2020_mortality.csv"
        )
        result = reconstruct_from_row(fixture, "Song_2016", analysis_id="total_all_cause")

        # Nothing was retyped: the scale came from the row's own measure.
        self.assertEqual(result["measure"], "HR")
        self.assertEqual(result["scale"], "ratio")
        self.assertEqual(result["scale_source"], "row_measure")
        self.assertEqual(result["null_value"], 1.0)
        self.assertEqual(result["row"]["study_id"], "Song_2016")
        self.assertEqual(result["row"]["analysis_id"], "total_all_cause")

        # This is exactly the row the heuristic cannot flag, and reading it
        # from the dataset gets it right with no scale decision at all.
        self.assertAlmostEqual(result["z_statistic_approx"], -0.969577, delta=1e-5)
        self.assertAlmostEqual(result["p_two_sided_approx"], 0.332257, delta=1e-5)

        typed = reconstruct_from_ci(0.98, 0.94, 1.02, measure="HR")
        self.assertEqual(result["z_statistic_approx"], typed["z_statistic_approx"])
        self.assertEqual(result["p_two_sided_approx"], typed["p_two_sided_approx"])

    def test_row_surfaces_provenance_and_resolves_the_interval_level(self):
        fixture = str(
            Path(__file__).resolve().parent.parent
            / "tests" / "fixtures" / "naghshi_2020_mortality.csv"
        )
        flagged = reconstruct_from_row(
            fixture, "Sauvaget_2004", analysis_id="total_all_cause"
        )
        self.assertTrue(flagged["provenance_warnings"])
        self.assertIn(
            "DERIVED_INVALID_OR_UNJUSTIFIED", flagged["provenance_warnings"][0]
        )
        clean = reconstruct_from_row(fixture, "Song_2016", analysis_id="total_all_cause")
        self.assertEqual(clean["provenance_warnings"], [])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "levels.csv"
            path.write_text(
                "analysis_id,study_id,citation,cohort_id,effect,lower,upper,measure,"
                "outcome_provenance,exposure_provenance,input_confidence\n"
                "p,a90,A 2020,a90,0.80,0.68,0.94,HR,DIRECT,DIRECT,0.90\n"
                "p,b95,B 2020,b95,0.80,0.68,0.94,HR,DIRECT,DIRECT,\n",
                encoding="utf-8",
            )
            per_row = reconstruct_from_row(str(path), "a90")
            fallback = reconstruct_from_row(str(path), "b95")
            override = reconstruct_from_row(str(path), "a90", confidence=0.99)

        self.assertEqual(per_row["confidence"], 0.90)
        self.assertEqual(per_row["row"]["input_confidence_source"], "row")
        self.assertEqual(fallback["confidence"], 0.95)
        self.assertEqual(fallback["row"]["input_confidence_source"], "default")
        self.assertEqual(override["confidence"], 0.99)
        self.assertEqual(override["row"]["input_confidence_source"], "override")
        # Identical printed bounds at different levels must not reconstruct
        # the same standard error.
        self.assertGreater(
            per_row["standard_error_approx"], fallback["standard_error_approx"]
        )

    def test_row_refuses_an_ambiguous_or_missing_study_id(self):
        fixture = str(
            Path(__file__).resolve().parent.parent
            / "tests" / "fixtures" / "naghshi_2020_mortality.csv"
        )
        with self.assertRaisesRegex(ValueError, "more than one analysis"):
            reconstruct_from_row(fixture, "Song_2016")
        with self.assertRaisesRegex(ValueError, "no row with study_id"):
            reconstruct_from_row(fixture, "Not_A_Study")

        missing = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_continuous_result.py"),
                "row", fixture, "Song_2016",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("--analysis-id", missing.stderr)

        ok = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_continuous_result.py"),
                "row", fixture, "Song_2016", "--analysis-id", "total_all_cause",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("read from the dataset, not retyped", ok.stdout)
        self.assertIn("Null value: 1", ok.stdout)

    def test_ratio_cli_reports_both_scales_and_json_carries_the_warning(self):
        ratio_text = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_continuous_result.py"),
                "ci",
                "0.75",
                "0.60",
                "0.94",
                "--scale",
                "ratio",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Scale: ratio (given directly; analysis scale: log)", ratio_text.stdout)
        self.assertIn("Null value: 1", ratio_text.stdout)
        self.assertIn("Log-scale estimate:", ratio_text.stdout)
        self.assertIn("Approximate log-scale SE: 0.11453", ratio_text.stdout)
        self.assertIn("Approximate two-sided p: 0.0120", ratio_text.stdout)
        self.assertIn("Back-transformed:", ratio_text.stdout)
        self.assertNotIn("WARNING", ratio_text.stdout)

        linear_text = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_continuous_result.py"),
                "ci",
                "0.75",
                "0.60",
                "0.94",
                "--scale",
                "linear",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Null value: 0", linear_text.stdout)
        self.assertIn("WARNING:", linear_text.stdout)
        self.assertIn("--scale ratio", linear_text.stdout)

        linear_json = json.loads(
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "verify_continuous_result.py"),
                    "ci",
                    "0.75",
                    "0.60",
                    "0.94",
                    "--scale",
                    "linear",
                    "--json",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        self.assertIn("--scale ratio", linear_json["scale_warning"])
        self.assertEqual(linear_json["null_value"], 0.0)

    def test_reconstructs_approximate_se_statistics_and_asymmetry(self):
        result = reconstruct_from_ci(-4.04, -6.89, -1.18, scale="linear")

        self.assertAlmostEqual(result["standard_error_approx"], 1.456659, places=5)
        self.assertAlmostEqual(result["standard_error_lower_approx"], 1.454108, places=5)
        self.assertAlmostEqual(result["standard_error_upper_approx"], 1.459210, places=5)
        self.assertAlmostEqual(result["asymmetry_approx"], 0.005102, places=5)
        self.assertAlmostEqual(abs(result["z_statistic_approx"]), 2.775, delta=0.002)
        self.assertAlmostEqual(result["p_two_sided_approx"], 0.0055, delta=0.0002)
        self.assertEqual(result["approximation_label"], "approximate")
        self.assertTrue(result["approximate"])

    def test_reconstructs_nonstandard_confidence_and_reports_ci_asymmetry(self):
        nonstandard = reconstruct_from_ci(-4.04, -6.89, -1.18, confidence=0.90, scale="linear")
        self.assertAlmostEqual(nonstandard["critical_value_approx"], 1.644854, places=5)
        self.assertEqual(nonstandard["confidence"], 0.90)

        asymmetric = reconstruct_from_ci(10.0, 8.0, 15.0, scale="linear")
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
                "--scale",
                "linear",
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
                    reconstruct_from_ci(*values, scale="linear")

        for confidence in (0.0, 1.0, float("nan"), float("inf")):
            with self.subTest(confidence=confidence):
                with self.assertRaises(ValueError):
                    reconstruct_from_ci(-1.0, -2.0, 0.0, confidence=confidence, scale="linear")

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
                "--scale",
                "linear",
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
