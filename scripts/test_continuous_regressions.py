"""Regression tests for continuous confidence-interval reconstruction.

These cases protect the two failure modes covered by the continuous-result
audit: material interval asymmetry must not yield a contradictory inferential
value of p, and normal tails must remain nonzero/stable across Python versions.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import unittest
from pathlib import Path
from statistics import NormalDist


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import verify_continuous_result as vcr  # noqa: E402
from verify_continuous_result import reconstruct_from_ci  # noqa: E402


class ContinuousRegressionTests(unittest.TestCase):
    def test_linear_interval_including_null_quarantines_p_when_materially_asymmetric(self):
        result = reconstruct_from_ci(10.0, -1.0, 11.0, scale="linear")

        self.assertTrue(result["null_in_interval"])
        self.assertEqual(result["asymmetry_status"], "material")
        self.assertGreater(
            result["asymmetry_relative_approx"],
            vcr.CI_ASYMMETRY_RELATIVE_TOLERANCE,
        )
        self.assertIsNone(result["p_two_sided_approx"])
        self.assertEqual(
            result["p_two_sided_status"], "suppressed_material_asymmetry"
        )
        self.assertEqual(result["inferential_status"], "quarantined")
        self.assertIn("cannot be recovered defensibly", result["asymmetry_diagnostic"])

    def test_ratio_interval_including_null_is_checked_on_log_scale_and_quarantined(self):
        result = reconstruct_from_ci(2.0, 0.9, 2.1, scale="ratio")

        self.assertEqual(result["analysis_scale"], "log")
        self.assertTrue(result["null_in_interval"])
        self.assertEqual(result["asymmetry_status"], "material")
        self.assertGreater(
            result["asymmetry_relative_approx"],
            vcr.CI_ASYMMETRY_RELATIVE_TOLERANCE,
        )
        self.assertIsNone(result["p_two_sided_approx"])
        self.assertEqual(result["inferential_status"], "quarantined")
        self.assertIn("log analysis scale", result["asymmetry_diagnostic"])

    def test_small_rounding_asymmetry_preserves_approximate_p(self):
        result = reconstruct_from_ci(-4.04, -6.89, -1.18, scale="linear")

        self.assertEqual(result["asymmetry_status"], "within_tolerance")
        self.assertLessEqual(
            result["asymmetry_relative_approx"],
            vcr.CI_ASYMMETRY_RELATIVE_TOLERANCE,
        )
        self.assertEqual(result["p_two_sided_status"], "available_approximation")
        self.assertEqual(result["inferential_status"], "approximate")
        self.assertIsNotNone(result["p_two_sided_approx"])
        self.assertAlmostEqual(result["p_two_sided_approx"], 0.0055, delta=0.0002)

    def test_normal_tail_uses_erfc_and_does_not_underflow_at_z_8_5(self):
        critical = NormalDist().inv_cdf(0.975)
        estimate = 8.5
        result = reconstruct_from_ci(
            estimate,
            estimate - critical,
            estimate + critical,
            scale="linear",
        )

        expected = math.erfc(abs(result["z_statistic_approx"]) / math.sqrt(2.0))
        self.assertAlmostEqual(result["z_statistic_approx"], 8.5, places=12)
        self.assertGreater(expected, 0.0)
        self.assertAlmostEqual(result["p_two_sided_approx"], expected, places=25)
        self.assertGreater(result["p_two_sided_approx"], 1.0e-18)

    def test_cli_reports_quarantine_and_json_null_p(self):
        command = [
            sys.executable,
            str(SCRIPT_DIR / "verify_continuous_result.py"),
            "ci",
            "10",
            "-1",
            "11",
            "--scale",
            "linear",
            "--json",
        ]
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertIsNone(payload["p_two_sided_approx"])
        self.assertEqual(payload["inferential_status"], "quarantined")
        self.assertEqual(payload["asymmetry_status"], "material")

        text_completed = subprocess.run(
            command[:-1],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Approximate two-sided p: SUPPRESSED", text_completed.stdout)
        self.assertIn("Inference status: quarantined", text_completed.stdout)


if __name__ == "__main__":
    unittest.main()
