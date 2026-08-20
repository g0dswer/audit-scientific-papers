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


_LINEAR_ASYMMETRY_TRIGGER = 0.05
_LOG_SYMMETRY_FRACTION = 0.25

# A normal/Wald standard error cannot be recovered defensibly from an interval
# whose two analysis-scale half-widths differ materially.  A ten-percent
# relative difference is deliberately permissive for published rounding while
# quarantining the much larger asymmetry that can make the reconstructed p
# contradict the reported interval.  This is a relative difference, not the
# old upper/lower ratio, so it is bounded in [0, 1] and is interpretable for
# either the identity or log analysis scale.
CI_ASYMMETRY_RELATIVE_TOLERANCE = 0.10


# Mirrors the effect-measure vocabulary of reconstruct_meta_analysis.py; a test
# asserts the two stay identical. Kept local so the estimate/interval paths stay
# standalone: only the ``row`` subcommand, which reads an extracted dataset,
# imports the meta engine, and it does so lazily.
RATIO_MEASURES = {"HR", "RR", "OR", "IRR", "RATIO"}
LINEAR_MEASURES = {"MD", "SMD"}


def _validate_scale(scale: str) -> str:
    if scale not in ("linear", "ratio"):
        raise ValueError("scale must be 'linear' or 'ratio'")
    return scale


def _resolve_scale(scale: str | None, measure: str | None) -> tuple[str, str | None]:
    """Resolve the analysis scale from exactly one of ``scale`` or ``measure``.

    Naming the measure is preferred: it is the vocabulary the source itself
    uses and the extraction schema audits, so it leaves less room for the
    caller to mis-abstract a hazard ratio into ``linear``.
    """
    if (scale is None) == (measure is None):
        raise ValueError(
            "exactly one of scale ('linear' or 'ratio') or measure "
            "(HR, RR, OR, IRR, RATIO, MD, SMD) must be supplied"
        )
    if scale is not None:
        return _validate_scale(scale), None
    normalized = str(measure).strip().upper()
    if normalized in RATIO_MEASURES:
        return "ratio", normalized
    if normalized in LINEAR_MEASURES:
        return "linear", normalized
    raise ValueError(
        f"unknown effect measure {measure!r}; expected one of "
        f"{', '.join(sorted(RATIO_MEASURES | LINEAR_MEASURES))}"
    )


def _ratio_scale_warning(
    estimate: float,
    lower: float,
    upper: float,
    standard_error_lower: float,
    standard_error_upper: float,
) -> str | None:
    """Warn when a linear-path input looks like an unlogged ratio measure.

    A ratio measure (hazard ratio, odds ratio, risk ratio) is symmetric about
    the estimate on the log scale, which makes it necessarily asymmetric on the
    linear scale: for a log half-width ``h`` the linear half-width ratio is
    ``exp(h)``.  The heuristic compares how far each scale departs from
    symmetry.  It fires only when all three values are strictly positive, the
    linear half-widths differ by more than ``_LINEAR_ASYMMETRY_TRIGGER`` (5%,
    which is well above the rounding noise of published two- and
    three-significant-digit intervals), and the log-scale departure from
    symmetry is at most ``_LOG_SYMMETRY_FRACTION`` (a quarter) of the linear
    one.  A relative comparison is used rather than a fixed log tolerance
    because published ratios are rounded: HR 0.75 (0.60 to 0.94) is 27%
    asymmetric on the linear scale but still 1.2% off log symmetry purely from
    rounding, and a fixed 1% log threshold would miss it.  A genuinely
    asymmetric estimate on a positive scale, such as a bootstrap or
    profile-likelihood interval, stays asymmetric after logging and does not
    fire.  The check only warns: it never changes any reported number.
    """

    if not (estimate > 0.0 and lower > 0.0 and upper > 0.0):
        return None
    if standard_error_lower <= 0.0 or standard_error_upper <= 0.0:
        return None
    linear_ratio = standard_error_upper / standard_error_lower
    log_lower_half_width = math.log(estimate) - math.log(lower)
    log_upper_half_width = math.log(upper) - math.log(estimate)
    if log_lower_half_width <= 0.0 or log_upper_half_width <= 0.0:
        return None
    log_ratio = log_upper_half_width / log_lower_half_width
    linear_departure = abs(linear_ratio - 1.0)
    log_departure = abs(log_ratio - 1.0)
    if linear_departure <= _LINEAR_ASYMMETRY_TRIGGER:
        return None
    if log_departure > _LOG_SYMMETRY_FRACTION * linear_departure:
        return None
    return (
        "This interval is asymmetric on the linear scale but symmetric on the "
        "log scale, which is the signature of a ratio measure (hazard ratio, "
        "odds ratio, risk ratio). The linear path tests against a null of 0 and "
        "reports linear-scale asymmetry, both of which are wrong for a ratio. "
        "Re-run with --scale ratio if this estimate is a ratio measure."
    )


def _two_sided_normal_p(z_statistic: float) -> float:
    """Return a stable two-sided standard-normal tail probability.

    ``NormalDist.cdf`` used to underflow to exactly zero for moderately large
    z statistics on some supported Python versions.  ``erfc`` evaluates the
    survival tail directly, so the result remains useful for values such as
    z=8.5 (approximately 1.9e-17) and does not depend on that implementation
    detail of ``statistics.NormalDist``.
    """

    return math.erfc(abs(z_statistic) / math.sqrt(2.0))


def reconstruct_from_ci(
    estimate: float,
    lower: float,
    upper: float,
    confidence: float = 0.95,
    *,
    scale: str | None = None,
    measure: str | None = None,
) -> dict[str, Any]:
    """Reconstruct approximate SE, normal statistic, and two-sided p-value.

    The lower and upper half-widths are converted to separate approximate
    standard errors, then averaged to obtain the central approximate SE:

        SE ~= ((estimate - lower) + (upper - estimate)) / (2 * z_critical)

    Exactly one of ``scale`` or ``measure`` is required; neither has a
    default.  ``measure`` is preferred: it takes the effect measure as the
    source reports it (``HR``, ``RR``, ``OR``, ``IRR``, ``RATIO``, ``MD``,
    ``SMD``), the same vocabulary the extraction schema already audits row by
    row, and derives the scale from it.  ``scale`` takes the analysis scale
    directly and is the escape hatch for a measure outside that vocabulary.

    On the linear scale the estimate is a difference measure tested against a
    null of 0 on the reported scale.  On the ratio scale the estimate is a
    ratio measure, all three values must be strictly positive, the
    reconstruction is performed on the natural-log scale, and the null value
    is 1.  Ratio measures must never be sent through the linear path: their
    null is not 0 and their intervals are symmetric only after logging.

    There is no default because the heuristic in ``_ratio_scale_warning``
    cannot catch every mislabeled ratio.  A ratio close to the null with a
    narrow interval -- HR 0.98 (0.94 to 1.02), the shape of the largest and
    most heavily weighted cohort studies -- is very nearly symmetric on both
    scales, so no warning can fire, yet the linear path reports z = 48 where
    the truth is z = -0.97.  Forcing the caller to name the measure or the
    scale replaces a silent default with a decision the caller has to make.

    This deliberately uses a normal approximation and does not infer degrees
    of freedom or claim exact reproduction of the published model. If the
    confidence interval is materially asymmetric on the selected analysis
    scale, the reconstructed z and p are retained only as diagnostic arithmetic
    and the p-value is suppressed (quarantined) by default. The named
    ``CI_ASYMMETRY_RELATIVE_TOLERANCE`` allows only small asymmetry consistent
    with published rounding.
    """

    estimate = _validate_real(estimate, "estimate")
    lower = _validate_real(lower, "lower")
    upper = _validate_real(upper, "upper")
    confidence = _validate_confidence(confidence)
    scale, measure = _resolve_scale(scale, measure)
    if not lower < upper:
        raise ValueError("lower must be strictly less than upper")
    if not lower <= estimate <= upper:
        raise ValueError("estimate must lie between lower and upper")
    if scale == "ratio" and not (estimate > 0.0 and lower > 0.0 and upper > 0.0):
        source = f"measure {measure}" if measure else "ratio scale"
        raise ValueError(
            f"{source} requires strictly positive estimate, lower, and upper"
        )

    if scale == "ratio":
        analysis_scale = "log"
        null_value = 1.0
        analysis_null_value = 0.0
        analysis_estimate = math.log(estimate)
        analysis_lower = math.log(lower)
        analysis_upper = math.log(upper)
    else:
        analysis_scale = "identity"
        null_value = 0.0
        analysis_null_value = 0.0
        analysis_estimate = estimate
        analysis_lower = lower
        analysis_upper = upper

    critical_value = _critical_value(confidence)
    lower_half_width = analysis_estimate - analysis_lower
    upper_half_width = analysis_upper - analysis_estimate
    standard_error_lower = lower_half_width / critical_value
    standard_error_upper = upper_half_width / critical_value
    standard_error = (standard_error_lower + standard_error_upper) / 2.0
    if standard_error <= 0.0:
        raise ValueError("confidence interval must have positive average width")

    z_statistic = (analysis_estimate - analysis_null_value) / standard_error
    asymmetry = standard_error_upper - standard_error_lower
    asymmetry_ratio = (
        standard_error_upper / standard_error_lower
        if standard_error_lower > 0.0
        else None
    )
    asymmetry_relative = abs(upper_half_width - lower_half_width) / (
        upper_half_width + lower_half_width
    )
    asymmetry_material = (
        asymmetry_relative > CI_ASYMMETRY_RELATIVE_TOLERANCE
    )
    asymmetry_status = "material" if asymmetry_material else "within_tolerance"
    null_in_interval = analysis_lower <= analysis_null_value <= analysis_upper
    diagnostic_scale = "linear" if scale == "linear" else "log"
    if asymmetry_material:
        p_two_sided = None
        p_two_sided_status = "suppressed_material_asymmetry"
        inferential_status = "quarantined"
        asymmetry_diagnostic = (
            "Material confidence-interval asymmetry on the "
            f"{diagnostic_scale} analysis scale ({analysis_scale} coordinates): "
            "relative half-width difference "
            f"{asymmetry_relative:.6g} exceeds the named tolerance "
            f"{CI_ASYMMETRY_RELATIVE_TOLERANCE:.6g}. A single Wald standard "
            "error cannot be recovered defensibly; the approximate z and "
            "two-sided p are quarantined. Recover the source standard error, "
            "variance, test statistic, or model output before making an "
            "inferential claim."
        )
    else:
        p_two_sided = _two_sided_normal_p(z_statistic)
        p_two_sided_status = "available_approximation"
        inferential_status = "approximate"
        asymmetry_diagnostic = (
            "Confidence-interval asymmetry on the "
            f"{diagnostic_scale} analysis scale ({analysis_scale} coordinates) "
            "is within the named rounding "
            f"tolerance ({asymmetry_relative:.6g} <= "
            f"{CI_ASYMMETRY_RELATIVE_TOLERANCE:.6g}); the p-value remains an "
            "approximate plausibility check, not an exact reconstruction."
        )

    if scale == "ratio":
        scale_warning = None
        # Back-transformed companions to the log-scale intermediates above.
        # A ratio interval that is exactly symmetric on the log scale has an
        # interval geometric mean equal to the reported estimate.
        back_transformed = {
            "estimate": estimate,
            "lower": lower,
            "upper": upper,
            "interval_geometric_mean": math.exp(
                (analysis_lower + analysis_upper) / 2.0
            ),
            "standard_error_multiplicative": math.exp(standard_error),
        }
    else:
        scale_warning = _ratio_scale_warning(
            estimate, lower, upper, standard_error_lower, standard_error_upper
        )
        back_transformed = None

    return {
        "estimate": estimate,
        "lower": lower,
        "upper": upper,
        "confidence": confidence,
        "scale": scale,
        "measure": measure,
        "scale_source": "measure" if measure else "scale",
        "analysis_scale": analysis_scale,
        "null_value": null_value,
        "analysis_estimate": analysis_estimate,
        "analysis_lower": analysis_lower,
        "analysis_upper": analysis_upper,
        "back_transformed": back_transformed,
        "critical_value_approx": critical_value,
        "lower_half_width_approx": lower_half_width,
        "upper_half_width_approx": upper_half_width,
        "standard_error_approx": standard_error,
        "standard_error_lower_approx": standard_error_lower,
        "standard_error_upper_approx": standard_error_upper,
        "asymmetry_approx": asymmetry,
        "asymmetry_ratio_approx": asymmetry_ratio,
        "asymmetry_relative_approx": asymmetry_relative,
        "asymmetry_tolerance": CI_ASYMMETRY_RELATIVE_TOLERANCE,
        "asymmetry_status": asymmetry_status,
        "asymmetry_diagnostic": asymmetry_diagnostic,
        "null_in_interval": null_in_interval,
        "z_statistic_approx": z_statistic,
        "absolute_z_statistic_approx": abs(z_statistic),
        "p_two_sided_approx": p_two_sided,
        "p_two_sided_status": p_two_sided_status,
        "inferential_status": inferential_status,
        "scale_warning": scale_warning,
        "approximate": True,
        "approximation_label": "approximate",
        "approximation_note": (
            "Reconstructed from the confidence-interval width using a normal "
            "critical value; exact standard error, degrees of freedom, and "
            "model-based p-value are not inferred."
        ),
        "scale_note": (
            "Ratio scale: the estimate and interval are analysed on the "
            "natural-log scale and tested against a null of 1; standard "
            "errors and asymmetry below are log-scale quantities."
            if scale == "ratio"
            else "Linear scale: the estimate is tested against a null of 0 on "
            "the reported scale. Ratio measures (hazard, odds, or risk "
            "ratios) must be run with --scale ratio instead."
        ),
    }


def reconstruct_from_row(
    dataset: str,
    study_id: str,
    *,
    analysis_id: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Reconstruct one row of an extracted dataset, reading its own metadata.

    Nothing about the estimate is retyped.  The effect, interval, effect
    measure, and source interval level all come from the row, which has
    already been traced to the original report and validated by the same
    loader the pooling engine uses.  That removes the last place where the
    analysis scale depended on the auditor transcribing a measure correctly.

    ``confidence`` overrides the row's interval level and is for a source that
    prints a level the dataset does not record; leave it unset to use the
    row's own ``input_confidence``, or the 0.95 default when the column is
    absent or blank.
    """

    # Imported here so the estimate/interval paths stay dependency-free.
    from reconstruct_meta_analysis import MetaAnalysisError, load_records

    # OSError covers a missing, unreadable, or directory-valued path; without it
    # the CLI would print a traceback where every other dataset entry point
    # prints a clean diagnostic.
    try:
        records = load_records(dataset)
    except (MetaAnalysisError, OSError) as error:
        raise ValueError(f"could not load {dataset}: {error}") from error

    matches = [
        record
        for record in records
        if record.study_id == study_id
        and (analysis_id is None or record.analysis_id == analysis_id)
    ]
    if not matches:
        scope = f" in analysis {analysis_id!r}" if analysis_id else ""
        available = sorted({record.study_id for record in records})
        raise ValueError(
            f"no row with study_id {study_id!r}{scope}; the dataset has "
            f"{', '.join(available)}"
        )
    if len(matches) > 1:
        pools = sorted({record.analysis_id for record in matches})
        if len(pools) > 1:
            raise ValueError(
                f"study_id {study_id!r} appears in more than one analysis "
                f"({', '.join(pools)}); pass --analysis-id to choose one"
            )
        raise ValueError(
            f"study_id {study_id!r} occurs {len(matches)} times in analysis "
            f"{pools[0]!r}; the identifier is not unique, so the intended row "
            "cannot be selected. Resolve the duplicate in the dataset first"
        )

    record = matches[0]
    row_confidence = confidence if confidence is not None else record.input_confidence
    result = reconstruct_from_ci(
        record.effect,
        record.lower,
        record.upper,
        confidence=0.95 if row_confidence is None else row_confidence,
        measure=record.measure,
    )
    result["row"] = {
        "analysis_id": record.analysis_id,
        "study_id": record.study_id,
        "citation": record.citation,
        "cohort_id": record.cohort_id,
        "measure": record.measure,
        # Code scanning classifies any field named `sex` as private personal
        # data and flags this row and the header print below. It is a false
        # positive, dismissed on the repository: the value is a published
        # subgroup label -- "all", "men", "women" -- transcribed from a forest
        # plot to identify which stratum of a study a row came from. This tool
        # reads aggregate published estimates only and never holds
        # participant-level data. Inline suppression comments are not honoured
        # by GitHub code scanning, so the dismissal lives in the security tab
        # and this note records the reasoning next to the code.
        "sex": record.sex,
        "outcome_reported_originally": record.outcome_reported_originally,
        "outcome_used_in_meta_analysis": record.outcome_used_in_meta_analysis,
        "outcome_provenance": record.outcome_provenance,
        "exposure_provenance": record.exposure_provenance,
        "source_location": record.source_location,
        "source_url": record.source_url,
        "notes": record.notes,
        "input_confidence_source": (
            "override"
            if confidence is not None
            else "row" if record.input_confidence is not None else "default"
        ),
    }
    result["scale_source"] = "row_measure"
    provenance_warnings = []
    if record.outcome_provenance not in {"DIRECT", "DERIVED_VALID"}:
        provenance_warnings.append(
            f"Outcome provenance is {record.outcome_provenance}: this row's outcome "
            "is not a direct or validly derived measurement of the pooled definition."
        )
    if record.exposure_provenance not in {"DIRECT", "DERIVED_VALID"}:
        provenance_warnings.append(
            f"Exposure provenance is {record.exposure_provenance}: this row's exposure "
            "contrast is not a direct or validly derived match."
        )
    result["provenance_warnings"] = provenance_warnings
    return result


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
    scale_group = ci_parser.add_mutually_exclusive_group(required=True)
    scale_group.add_argument(
        "--measure",
        choices=tuple(sorted(RATIO_MEASURES | LINEAR_MEASURES)),
        help=(
            "the effect measure as the source reports it; the analysis scale "
            "is derived from it. Preferred over --scale, because it is the "
            "vocabulary the extraction schema already audits row by row"
        ),
    )
    scale_group.add_argument(
        "--scale",
        choices=("linear", "ratio"),
        help=(
            "the analysis scale directly, for a measure outside the --measure "
            "vocabulary: linear for difference measures tested against a null "
            "of 0; ratio for multiplicative measures, analysed on the log "
            "scale against a null of 1"
        ),
    )
    ci_parser.add_argument("--json", action="store_true", help="emit JSON")

    row_parser = subparsers.add_parser(
        "row",
        help=(
            "reconstruct one row of an extracted dataset, taking its effect, "
            "interval, measure, and interval level from the row itself"
        ),
    )
    row_parser.add_argument("dataset")
    row_parser.add_argument("study_id")
    row_parser.add_argument(
        "--analysis-id",
        default=None,
        help="required when the study_id appears in more than one pool",
    )
    row_parser.add_argument(
        "--confidence",
        type=float,
        default=None,
        help=(
            "override the row's source interval level; omit to use the row's "
            "input_confidence, or 0.95 when that column is absent"
        ),
    )
    row_parser.add_argument("--json", action="store_true", help="emit JSON")

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


def _print_row_header(result: dict[str, Any]) -> None:
    row = result["row"]
    print(f"Row: {row['study_id']} in analysis {row['analysis_id']}")
    # The stratum label is aggregate published metadata, not personal data; see
    # the note beside "sex" in reconstruct_from_row.
    stratum = f" ({row['sex']})" if row["sex"] else ""
    print(f"Citation: {row['citation']}{stratum}")
    print(f"Measure as reported: {row['measure']} (read from the dataset, not retyped)")
    if row["outcome_reported_originally"] or row["outcome_used_in_meta_analysis"]:
        print(
            f"Outcome originally reported: {row['outcome_reported_originally'] or 'not recorded'}"
            f"; used as: {row['outcome_used_in_meta_analysis'] or 'not recorded'}"
        )
    print(
        f"Source interval level: {result['confidence']:.0%} "
        f"(from {row['input_confidence_source']})"
    )
    if row["source_location"] or row["source_url"]:
        print(f"Source: {row['source_location']} {row['source_url']}".strip())


def _print_ci(result: dict[str, Any]) -> None:
    print("Continuous result reconstruction: approximate")
    origin = (
        f"from measure {result['measure']}"
        if result["measure"]
        else "given directly"
    )
    print(
        f"Scale: {result['scale']} ({origin}; analysis scale: "
        f"{result['analysis_scale']})"
    )
    print(f"Null value: {result['null_value']:.6g}")
    print(f"Estimate: {result['estimate']:.6g}")
    if result["scale"] == "ratio":
        print(
            f"Log-scale estimate: {result['analysis_estimate']:.6g} "
            f"(log interval {result['analysis_lower']:.6g} to "
            f"{result['analysis_upper']:.6g})"
        )
    label = "log-scale " if result["scale"] == "ratio" else ""
    print(
        f"Approximate {label}SE: {result['standard_error_approx']:.6g} "
        f"(lower-side {result['standard_error_lower_approx']:.6g}; "
        f"upper-side {result['standard_error_upper_approx']:.6g})"
    )
    print(
        f"Approximate {label}asymmetry (upper - lower SE): "
        f"{result['asymmetry_approx']:.6g}"
    )
    print(
        "Relative analysis-scale asymmetry: "
        f"{result['asymmetry_relative_approx']:.6g} "
        f"(status: {result['asymmetry_status']}; tolerance: "
        f"{result['asymmetry_tolerance']:.6g})"
    )
    print(f"Approximate normal statistic: {result['z_statistic_approx']:.6g}")
    if result["p_two_sided_approx"] is None:
        print(
            "Approximate two-sided p: SUPPRESSED "
            f"({result['p_two_sided_status']})"
        )
    else:
        print(f"Approximate two-sided p: {result['p_two_sided_approx']:.6g}")
    print("Inference status: " + result["inferential_status"])
    print("Asymmetry diagnostic: " + result["asymmetry_diagnostic"])
    if result["back_transformed"] is not None:
        back = result["back_transformed"]
        print(
            "Back-transformed: estimate "
            f"{back['estimate']:.6g}, interval [{back['lower']:.6g}, "
            f"{back['upper']:.6g}], interval geometric mean "
            f"{back['interval_geometric_mean']:.6g}, multiplicative SE "
            f"{back['standard_error_multiplicative']:.6g}"
        )
    if result["scale_warning"] is not None:
        print("WARNING: " + result["scale_warning"])
    print(result["scale_note"])
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
                scale=args.scale,
                measure=args.measure,
            )
        elif args.command == "row":
            result = reconstruct_from_row(
                args.dataset,
                args.study_id,
                analysis_id=args.analysis_id,
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
    elif args.command in ("ci", "row"):
        if args.command == "row":
            _print_row_header(result)
        _print_ci(result)
        for warning in result.get("provenance_warnings", []):
            print(f"PROVENANCE: {warning}")
    elif args.command == "changes":
        _print_changes(result)
    else:
        _print_standardized(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
