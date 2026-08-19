#!/usr/bin/env python3
"""Consistency checks for reported continuous trial results.

Calculations reconstructed from a reported confidence interval are
approximations: the exact standard error and p-value can depend on degrees of
freedom, the model, and the software used for the published analysis.
"""

from __future__ import annotations

import argparse
import json
import math
from numbers import Integral, Real
from statistics import NormalDist
from typing import Any


def _validate_real(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def _validate_confidence(confidence: float) -> float:
    confidence = _validate_real(confidence, "confidence")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be a finite number in (0, 1)")
    return confidence


def _validate_sample_size(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer sample size")
    value = int(value)
    if value < 2:
        raise ValueError(f"{name} must be at least 2")
    return value


def _critical_value(confidence: float) -> float:
    return NormalDist().inv_cdf(0.5 + confidence / 2.0)


def reconstruct_from_ci(
    estimate: float,
    lower: float,
    upper: float,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Reconstruct approximate SE, normal statistic, and two-sided p-value.

    The lower and upper half-widths are converted to separate approximate
    standard errors, then averaged to obtain the central approximate SE:

        SE ~= ((estimate - lower) + (upper - estimate)) / (2 * z_critical)

    This deliberately uses a normal approximation and does not infer degrees
    of freedom or claim exact reproduction of the published model.
    """

    estimate = _validate_real(estimate, "estimate")
    lower = _validate_real(lower, "lower")
    upper = _validate_real(upper, "upper")
    confidence = _validate_confidence(confidence)
    if not lower < upper:
        raise ValueError("lower must be strictly less than upper")
    if not lower <= estimate <= upper:
        raise ValueError("estimate must lie between lower and upper")

    critical_value = _critical_value(confidence)
    lower_half_width = estimate - lower
    upper_half_width = upper - estimate
    standard_error_lower = lower_half_width / critical_value
    standard_error_upper = upper_half_width / critical_value
    standard_error = (standard_error_lower + standard_error_upper) / 2.0
    if standard_error <= 0.0:
        raise ValueError("confidence interval must have positive average width")

    z_statistic = estimate / standard_error
    p_two_sided = 2.0 * NormalDist().cdf(-abs(z_statistic))
    asymmetry = standard_error_upper - standard_error_lower
    asymmetry_ratio = (
        standard_error_upper / standard_error_lower
        if standard_error_lower > 0.0
        else None
    )

    return {
        "estimate": estimate,
        "lower": lower,
        "upper": upper,
        "confidence": confidence,
        "critical_value_approx": critical_value,
        "lower_half_width_approx": lower_half_width,
        "upper_half_width_approx": upper_half_width,
        "standard_error_approx": standard_error,
        "standard_error_lower_approx": standard_error_lower,
        "standard_error_upper_approx": standard_error_upper,
        "asymmetry_approx": asymmetry,
        "asymmetry_ratio_approx": asymmetry_ratio,
        "z_statistic_approx": z_statistic,
        "absolute_z_statistic_approx": abs(z_statistic),
        "p_two_sided_approx": p_two_sided,
        "approximate": True,
        "approximation_label": "approximate",
        "approximation_note": (
            "Reconstructed from the confidence-interval width using a normal "
            "critical value; exact standard error, degrees of freedom, and "
            "model-based p-value are not inferred."
        ),
    }


def check_change_means(
    baseline_t: float,
    endpoint_t: float,
    baseline_c: float,
    endpoint_c: float,
    adjusted_estimate: float | None,
) -> dict[str, Any]:
    """Compute raw within-arm changes and their unadjusted contrast.

    The raw contrast is arithmetic on reported group means.  If an adjusted
    estimate is supplied, its difference from the raw contrast is shown, but
    the output explicitly warns that adjusted and unadjusted values may target
    potentially different estimands and are not interchangeable.
    """

    baseline_t = _validate_real(baseline_t, "baseline_t")
    endpoint_t = _validate_real(endpoint_t, "endpoint_t")
    baseline_c = _validate_real(baseline_c, "baseline_c")
    endpoint_c = _validate_real(endpoint_c, "endpoint_c")
    if adjusted_estimate is not None:
        adjusted_estimate = _validate_real(adjusted_estimate, "adjusted_estimate")

    change_treatment = endpoint_t - baseline_t
    change_control = endpoint_c - baseline_c
    raw_contrast = change_treatment - change_control
    adjusted_minus_raw = (
        adjusted_estimate - raw_contrast
        if adjusted_estimate is not None
        else None
    )

    return {
        "baseline_treatment": baseline_t,
        "endpoint_treatment": endpoint_t,
        "baseline_control": baseline_c,
        "endpoint_control": endpoint_c,
        "change_treatment": change_treatment,
        "change_control": change_control,
        "raw_contrast": raw_contrast,
        "adjusted_estimate": adjusted_estimate,
        "adjusted_minus_raw": adjusted_minus_raw,
        "estimand_note": (
            "The raw change contrast is unadjusted arithmetic on group means; "
            "the adjusted estimate and raw contrast may target potentially "
            "different estimands and are not interchangeable."
        ),
    }


def check_standardized_effect(
    mean_difference: float,
    denominator_sd: float,
    n_treatment: int,
    n_control: int,
    reported_effect: float | None = None,
    tolerance: float = 0.1,
    degrees_of_freedom: float | None = None,
    reported_metric: str | None = None,
) -> dict[str, Any]:
    """Check approximate Cohen's d and Hedges' g from a supplied denominator.

    ``denominator_sd`` is intentionally supplied by the caller rather than
    inferred. It may be a pooled SD, residual SD, or another documented
    denominator, and the choice must be reported separately. Hedges' g uses
    the small-sample correction ``J = 1 - 3 / (4*df - 1)``. When no degrees
    of freedom are supplied, the classical two-independent-groups value
    ``df = n_treatment + n_control - 2`` is used. A supplied finite df > 1
    is accepted, including non-integer values, but its validity depends on
    matching the denominator and model.

    If ``reported_effect`` is supplied, ``reported_metric`` must explicitly be
    ``"cohens_d"`` or ``"hedges_g"``. The reported value is compared with the
    corresponding reconstructed metric. Both effect calculations are labeled
    approximate because the denominator, covariance, and model context may
    not reproduce the source analysis exactly.
    """

    mean_difference = _validate_real(mean_difference, "mean_difference")
    denominator_sd = _validate_real(denominator_sd, "denominator_sd")
    if denominator_sd <= 0.0:
        raise ValueError("denominator_sd must be greater than zero")
    n_treatment = _validate_sample_size(n_treatment, "n_treatment")
    n_control = _validate_sample_size(n_control, "n_control")
    valid_reported_metrics = {"cohens_d", "hedges_g"}
    if reported_effect is None and reported_metric is not None:
        raise ValueError("reported_metric requires reported_effect")
    if reported_effect is not None:
        reported_effect = _validate_real(reported_effect, "reported_effect")
        if reported_metric not in valid_reported_metrics:
            raise ValueError("reported_metric must be 'cohens_d' or 'hedges_g'")
    tolerance = _validate_real(tolerance, "tolerance")
    if tolerance < 0.0:
        raise ValueError("tolerance must be non-negative")

    if degrees_of_freedom is None:
        degrees_of_freedom = n_treatment + n_control - 2
        df_source = "two_independent_groups"
        validity_scope = (
            "classical two-independent-groups case only; the denominator SD "
            "must match that model"
        )
    else:
        degrees_of_freedom = _validate_real(degrees_of_freedom, "degrees_of_freedom")
        if degrees_of_freedom <= 1.0:
            raise ValueError("degrees_of_freedom must be greater than 1")
        df_source = "user_supplied"
        validity_scope = (
            "user-supplied degrees of freedom; valid only when matched to the "
            "denominator, covariance, and model"
        )

    j_correction = 1.0 - 3.0 / (4.0 * degrees_of_freedom - 1.0)
    cohens_d = mean_difference / denominator_sd
    hedges_g = j_correction * cohens_d
    if reported_metric is None:
        comparison_target = None
        reconstructed_for_comparison = None
    elif reported_metric == "cohens_d":
        comparison_target = "cohens_d_approx"
        reconstructed_for_comparison = cohens_d
    else:
        comparison_target = "hedges_g_approx"
        reconstructed_for_comparison = hedges_g
    absolute_difference = (
        abs(reconstructed_for_comparison - reported_effect)
        if reported_effect is not None
        else None
    )
    consistent_with_tolerance = (
        absolute_difference <= tolerance
        if absolute_difference is not None
        else None
    )

    return {
        "mean_difference": mean_difference,
        "denominator_sd": denominator_sd,
        "n_treatment": n_treatment,
        "n_control": n_control,
        "degrees_of_freedom": degrees_of_freedom,
        "df_source": df_source,
        "validity_scope": validity_scope,
        "cohens_d": cohens_d,
        "cohens_d_approx": cohens_d,
        "j_correction": j_correction,
        "j_correction_approx": j_correction,
        "hedges_g": hedges_g,
        "hedges_g_approx": hedges_g,
        "reported_effect": reported_effect,
        "reported_metric": reported_metric,
        "comparison_target": comparison_target,
        "tolerance": tolerance,
        "absolute_difference": absolute_difference,
        "consistent_with_tolerance": consistent_with_tolerance,
        "consistent_with_tolerance_note": (
            "This is an arithmetic check only (proximity to a tolerance); it is not an "
            "equivalence test, confirmation of the model, or validation of "
            "the reported effect."
        ),
        "approximate": True,
        "approximation_label": "approximate",
        "approximation_note": (
            "Cohen's d and Hedges' g are reconstructed from the supplied mean "
            "difference and denominator SD; the denominator definition, "
            "degrees-of-freedom source, covariance, model, and reported effect "
            "context may differ."
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    ci_parser = subparsers.add_parser(
        "ci", help="reconstruct approximate statistics from a confidence interval"
    )
    ci_parser.add_argument("estimate", type=float)
    ci_parser.add_argument("lower", type=float)
    ci_parser.add_argument("upper", type=float)
    ci_parser.add_argument("--confidence", type=float, default=0.95)
    ci_parser.add_argument("--json", action="store_true", help="emit JSON")

    changes_parser = subparsers.add_parser(
        "changes", help="check raw changes and an optional adjusted estimate"
    )
    changes_parser.add_argument("baseline_t", type=float)
    changes_parser.add_argument("endpoint_t", type=float)
    changes_parser.add_argument("baseline_c", type=float)
    changes_parser.add_argument("endpoint_c", type=float)
    changes_parser.add_argument("--adjusted-estimate", type=float, default=None)
    changes_parser.add_argument("--json", action="store_true", help="emit JSON")

    standardized_parser = subparsers.add_parser(
        "standardized", help="check approximate Cohen's d and Hedges' g"
    )
    standardized_parser.add_argument("mean_difference", type=float)
    standardized_parser.add_argument("denominator_sd", type=float)
    standardized_parser.add_argument("n_treatment", type=int)
    standardized_parser.add_argument("n_control", type=int)
    standardized_parser.add_argument("--degrees-of-freedom", type=float, default=None)
    standardized_parser.add_argument("--reported-effect", type=float, default=None)
    standardized_parser.add_argument(
        "--reported-metric", choices=("cohens_d", "hedges_g"), default=None
    )
    standardized_parser.add_argument("--tolerance", type=float, default=0.1)
    standardized_parser.add_argument("--json", action="store_true", help="emit JSON")

    return parser


def _print_ci(result: dict[str, Any]) -> None:
    print("Continuous result reconstruction: approximate")
    print(f"Estimate: {result['estimate']:.6g}")
    print(
        f"Approximate SE: {result['standard_error_approx']:.6g} "
        f"(lower-side {result['standard_error_lower_approx']:.6g}; "
        f"upper-side {result['standard_error_upper_approx']:.6g})"
    )
    print(f"Approximate asymmetry (upper - lower SE): {result['asymmetry_approx']:.6g}")
    print(f"Approximate normal statistic: {result['z_statistic_approx']:.6g}")
    print(f"Approximate two-sided p: {result['p_two_sided_approx']:.6g}")
    print(result["approximation_note"])


def _print_changes(result: dict[str, Any]) -> None:
    print("Change-mean consistency check")
    print(f"Treatment change: {result['change_treatment']:.6g}")
    print(f"Control change: {result['change_control']:.6g}")
    print(f"Raw change contrast: {result['raw_contrast']:.6g}")
    if result["adjusted_estimate"] is None:
        print("Adjusted estimate: not supplied")
    else:
        print(f"Adjusted estimate: {result['adjusted_estimate']:.6g}")
        print(f"Adjusted minus raw contrast: {result['adjusted_minus_raw']:.6g}")
    print(result["estimand_note"])


def _print_standardized(result: dict[str, Any]) -> None:
    print("Standardized effect check: approximate")
    print(f"Cohen's d (approximate): {result['cohens_d_approx']:.6g}")
    print(f"Hedges' g (approximate): {result['hedges_g_approx']:.6g}")
    print(f"Degrees of freedom: {result['degrees_of_freedom']}")
    print(f"df source: {result['df_source']}")
    print(f"Validity scope: {result['validity_scope']}")
    print(f"J correction (approximate): {result['j_correction_approx']:.6g}")
    if result["reported_effect"] is None:
        print("Reported standardized effect: not supplied")
    else:
        print(f"Reported metric: {result['reported_metric']}")
        print(f"Reported standardized effect: {result['reported_effect']:.6g}")
        print(
            f"Absolute difference vs {result['reported_metric']}: "
            f"{result['absolute_difference']:.6g}"
        )
        print(
            "Consistent with tolerance: "
            f"{'yes' if result['consistent_with_tolerance'] else 'no'}"
        )
    print(result["consistent_with_tolerance_note"])
    print(result["approximation_note"])


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "ci":
            result = reconstruct_from_ci(
                args.estimate,
                args.lower,
                args.upper,
                confidence=args.confidence,
            )
        else:
            if args.command == "changes":
                result = check_change_means(
                    args.baseline_t,
                    args.endpoint_t,
                    args.baseline_c,
                    args.endpoint_c,
                    args.adjusted_estimate,
                )
            else:
                result = check_standardized_effect(
                    args.mean_difference,
                    args.denominator_sd,
                    args.n_treatment,
                    args.n_control,
                    reported_effect=args.reported_effect,
                    tolerance=args.tolerance,
                    degrees_of_freedom=args.degrees_of_freedom,
                    reported_metric=args.reported_metric,
                )
    except ValueError as error:
        parser.error(str(error))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))
    elif args.command == "ci":
        _print_ci(result)
    elif args.command == "changes":
        _print_changes(result)
    else:
        _print_standardized(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
