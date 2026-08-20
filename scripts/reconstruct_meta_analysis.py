#!/usr/bin/env python3
"""Reconstruct aggregate inverse-variance meta-analyses from a versioned CSV.

The core uses only the Python standard library. Ratio measures are analyzed on
the log scale. Different effect measures are rejected unless an explicit
published-reconstruction override is supplied; that override emits a warning
and does not claim estimand compatibility.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist, median
from typing import Sequence


# The Hartung-Knapp-Sidik-Jonkman scale factor q is exactly the squared ratio of
# the HKSJ standard error to the conventional one: SE_HKSJ = sqrt(q) * SE_conv.
# The floor below is therefore not an arbitrary tolerance -- it is the point at
# which the HKSJ interval would be a millionth of the conventional width, which
# only happens when the study estimates are identical up to rounding. Its
# expected value under the model is 1, so the comparison is scale-free.
_HKSJ_MINIMUM_SCALE_FACTOR = 1e-12

RATIO_MEASURES = {"HR", "RR", "OR", "IRR", "RATIO"}
LINEAR_MEASURES = {"MD", "SMD"}
DIRECT_PROVENANCE = {"DIRECT", "DERIVED_VALID"}
VALID_PROVENANCE = {
    "DIRECT",
    "DERIVED_VALID",
    "DERIVED_ASSUMPTION_DEPENDENT",
    "DERIVED_INVALID_OR_UNJUSTIFIED",
    "UNKNOWN",
}
# The single canonical participant-overlap vocabulary. Rows are rejected at load
# time when the status is outside this set, so a typo can never bypass the
# dependence guardrail below.
VALID_OVERLAP_STATUSES = {
    "none",
    "resolved_independent",
    "resolved_duplicate_removed",
    "modeled",
    "unknown",
    "unresolved",
    "possible",
}
# Statuses that leave a declared possible overlap unresolved.
UNRESOLVED_OVERLAP_STATUSES = {"", "unknown", "unresolved", "possible"}
# Degrees-of-freedom conventions for the random-effects prediction interval.
# "k-2" follows the Cochrane Handbook, Higgins-Thompson-Spiegelhalter (2009), and
# IntHout et al. (2016); "k-1" reproduces the older behaviour of this script.
PREDICTION_DF_CONVENTIONS = ("k-2", "k-1")


class MetaAnalysisError(ValueError):
    """Raised when an aggregate synthesis violates a numerical guardrail."""


@dataclass
class MetaRecord:
    analysis_id: str
    study_id: str
    citation: str
    cohort_id: str
    effect: float
    lower: float
    upper: float
    measure: str
    exposure: str = ""
    outcome_reported_originally: str = ""
    outcome_used_in_meta_analysis: str = ""
    outcome_provenance: str = "UNKNOWN"
    exposure_provenance: str = "UNKNOWN"
    sex: str = ""
    source_location: str = ""
    source_type: str = ""
    source_url: str = ""
    participant_overlap_possible: bool = False
    overlap_status: str = "none"
    include_published: bool = True
    input_confidence: float | None = None
    notes: str = ""


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n", ""}:
        return False
    raise MetaAnalysisError(f"Invalid Boolean value: {value!r}")


def _parse_optional_float(value: object) -> float | None:
    """Parse an optional numeric cell; a blank cell means "use the global default"."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise MetaAnalysisError(f"Invalid numeric value: {value!r}") from exc


def load_records(path: str | Path) -> list[MetaRecord]:
    """Load and type-check a row-level meta-analysis CSV."""
    records: list[MetaRecord] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {
            "analysis_id",
            "study_id",
            "citation",
            "cohort_id",
            "effect",
            "lower",
            "upper",
            "measure",
            "outcome_provenance",
            "exposure_provenance",
        }
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise MetaAnalysisError(f"Missing required CSV columns: {', '.join(sorted(missing))}")
        for line_number, row in enumerate(reader, start=2):
            try:
                record = MetaRecord(
                    analysis_id=row["analysis_id"].strip(),
                    study_id=row["study_id"].strip(),
                    citation=row["citation"].strip(),
                    cohort_id=row["cohort_id"].strip() or row["study_id"].strip(),
                    effect=float(row["effect"]),
                    lower=float(row["lower"]),
                    upper=float(row["upper"]),
                    measure=row["measure"].strip().upper(),
                    exposure=row.get("exposure", "").strip(),
                    outcome_reported_originally=row.get("outcome_reported_originally", "").strip(),
                    outcome_used_in_meta_analysis=row.get("outcome_used_in_meta_analysis", "").strip(),
                    outcome_provenance=row["outcome_provenance"].strip().upper(),
                    exposure_provenance=row["exposure_provenance"].strip().upper(),
                    sex=row.get("sex", "").strip(),
                    source_location=row.get("source_location", "").strip(),
                    source_type=row.get("source_type", "").strip(),
                    source_url=row.get("source_url", "").strip(),
                    participant_overlap_possible=_parse_bool(row.get("participant_overlap_possible", False)),
                    overlap_status=row.get("overlap_status", "none").strip().lower() or "none",
                    include_published=_parse_bool(row.get("include_published", True)),
                    input_confidence=_parse_optional_float(row.get("input_confidence", "")),
                    notes=row.get("notes", "").strip(),
                )
            except (KeyError, ValueError, MetaAnalysisError) as exc:
                raise MetaAnalysisError(f"Invalid row {line_number}: {exc}") from exc
            _validate_record(record, line_number)
            records.append(record)
    if not records:
        raise MetaAnalysisError("The dataset contains no records")
    return records


def _validate_record(record: MetaRecord, line_number: int | None = None) -> None:
    where = f" at row {line_number}" if line_number else ""
    values = (record.effect, record.lower, record.upper)
    if not all(math.isfinite(value) for value in values):
        raise MetaAnalysisError(f"Non-finite effect or interval{where}")
    if not record.lower < record.effect < record.upper:
        raise MetaAnalysisError(f"Confidence interval must contain the effect{where}")
    if record.measure in RATIO_MEASURES and record.lower <= 0:
        raise MetaAnalysisError(f"Ratio measures require positive values{where}")
    if record.measure not in RATIO_MEASURES | LINEAR_MEASURES:
        raise MetaAnalysisError(f"Unsupported effect measure {record.measure!r}{where}")
    if record.outcome_provenance not in VALID_PROVENANCE:
        raise MetaAnalysisError(f"Unknown outcome provenance {record.outcome_provenance!r}{where}")
    if record.exposure_provenance not in VALID_PROVENANCE:
        raise MetaAnalysisError(f"Unknown exposure provenance {record.exposure_provenance!r}{where}")
    if record.overlap_status not in VALID_OVERLAP_STATUSES:
        raise MetaAnalysisError(
            f"Unknown overlap status {record.overlap_status!r}{where}; expected one of "
            f"{', '.join(sorted(VALID_OVERLAP_STATUSES))}"
        )
    if record.input_confidence is not None and not (
        math.isfinite(record.input_confidence) and 0.0 < record.input_confidence < 1.0
    ):
        raise MetaAnalysisError(
            f"Per-row input_confidence must be strictly between zero and one{where}"
        )


def filter_records(
    records: Sequence[MetaRecord],
    *,
    analysis_id: str | None = None,
    direct_outcomes_only: bool = False,
    direct_exposures_only: bool = False,
    common_measure: str | None = None,
    published_only: bool = True,
) -> list[MetaRecord]:
    """Apply prespecified provenance and effect-measure filters."""
    normalized_measure = common_measure.upper() if common_measure else None
    return [
        record
        for record in records
        if (analysis_id is None or record.analysis_id == analysis_id)
        and (not published_only or record.include_published)
        and (not direct_outcomes_only or record.outcome_provenance in DIRECT_PROVENANCE)
        and (not direct_exposures_only or record.exposure_provenance in DIRECT_PROVENANCE)
        and (normalized_measure is None or record.measure == normalized_measure)
    ]


def _regularized_beta(x: float, a: float, b: float) -> float:
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0

    def continued_fraction(aa: float, bb: float, xx: float) -> float:
        max_iterations = 300
        epsilon = 3e-14
        tiny = 1e-300
        qab = aa + bb
        qap = aa + 1.0
        qam = aa - 1.0
        c = 1.0
        d = 1.0 - qab * xx / qap
        if abs(d) < tiny:
            d = tiny
        d = 1.0 / d
        result = d
        for iteration in range(1, max_iterations + 1):
            m2 = 2 * iteration
            numerator = iteration * (bb - iteration) * xx / ((qam + m2) * (aa + m2))
            d = 1.0 + numerator * d
            if abs(d) < tiny:
                d = tiny
            c = 1.0 + numerator / c
            if abs(c) < tiny:
                c = tiny
            d = 1.0 / d
            result *= d * c
            numerator = -(aa + iteration) * (qab + iteration) * xx / ((aa + m2) * (qap + m2))
            d = 1.0 + numerator * d
            if abs(d) < tiny:
                d = tiny
            c = 1.0 + numerator / c
            if abs(c) < tiny:
                c = tiny
            d = 1.0 / d
            delta = d * c
            result *= delta
            if abs(delta - 1.0) <= epsilon:
                break
        return result

    log_term = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    front = math.exp(log_term)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * continued_fraction(a, b, x) / a
    return 1.0 - front * continued_fraction(b, a, 1.0 - x) / b


def _student_t_cdf(value: float, degrees_of_freedom: int) -> float:
    if degrees_of_freedom <= 0:
        raise MetaAnalysisError("Student t degrees of freedom must be positive")
    if value == 0:
        return 0.5
    x = degrees_of_freedom / (degrees_of_freedom + value * value)
    tail = 0.5 * _regularized_beta(x, degrees_of_freedom / 2.0, 0.5)
    return 1.0 - tail if value > 0 else tail


def _student_t_quantile(probability: float, degrees_of_freedom: int) -> float:
    if not 0 < probability < 1:
        raise MetaAnalysisError("Probability must be between zero and one")
    if probability == 0.5:
        return 0.0
    if probability < 0.5:
        return -_student_t_quantile(1.0 - probability, degrees_of_freedom)
    lower, upper = 0.0, 1.0
    while _student_t_cdf(upper, degrees_of_freedom) < probability:
        upper *= 2.0
        if upper > 1e8:
            raise MetaAnalysisError("Student t quantile did not converge")
    for _ in range(120):
        midpoint = (lower + upper) / 2.0
        if _student_t_cdf(midpoint, degrees_of_freedom) < probability:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _weighted_mean(values: Sequence[float], weights: Sequence[float]) -> float:
    total = sum(weights)
    if not math.isfinite(total) or total <= 0:
        raise MetaAnalysisError("Weights must sum to a positive finite value")
    return sum(weight * value for weight, value in zip(weights, values)) / total


def _q_at_tau2(values: Sequence[float], variances: Sequence[float], tau2: float) -> tuple[float, float]:
    weights = [1.0 / (variance + tau2) for variance in variances]
    pooled = _weighted_mean(values, weights)
    q_value = sum(weight * (value - pooled) ** 2 for weight, value in zip(weights, values))
    return q_value, pooled


def _tau2_dl(values: Sequence[float], variances: Sequence[float]) -> float:
    weights = [1.0 / variance for variance in variances]
    pooled = _weighted_mean(values, weights)
    q_value = sum(weight * (value - pooled) ** 2 for weight, value in zip(weights, values))
    total = sum(weights)
    c_value = total - sum(weight * weight for weight in weights) / total
    if c_value <= 0:
        raise MetaAnalysisError("DerSimonian-Laird denominator is not positive")
    return max(0.0, (q_value - (len(values) - 1)) / c_value)


def _tau2_pm(values: Sequence[float], variances: Sequence[float]) -> float:
    target = len(values) - 1
    q_zero, _ = _q_at_tau2(values, variances, 0.0)
    if q_zero <= target:
        return 0.0
    lower, upper = 0.0, max(max(variances), 1e-12)
    while _q_at_tau2(values, variances, upper)[0] > target:
        upper *= 2.0
        if upper > 1e12:
            raise MetaAnalysisError("Paule-Mandel root was not bracketed")
    for _ in range(160):
        midpoint = (lower + upper) / 2.0
        if _q_at_tau2(values, variances, midpoint)[0] > target:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _tau2_reml(values: Sequence[float], variances: Sequence[float]) -> float:
    def objective(tau2: float) -> float:
        weights = [1.0 / (variance + tau2) for variance in variances]
        pooled = _weighted_mean(values, weights)
        residual = sum(weight * (value - pooled) ** 2 for weight, value in zip(weights, values))
        return -0.5 * (
            sum(math.log(variance + tau2) for variance in variances)
            + math.log(sum(weights))
            + residual
        )

    average = sum(values) / len(values)
    observed_variance = sum((value - average) ** 2 for value in values) / max(1, len(values) - 1)
    upper = max(observed_variance, median(variances), 1e-8)
    while objective(upper) > objective(upper / 2.0) and upper < 1e10:
        upper *= 2.0
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    lower = 0.0
    x1 = upper - (upper - lower) / phi
    x2 = lower + (upper - lower) / phi
    f1, f2 = objective(x1), objective(x2)
    for _ in range(180):
        if f1 < f2:
            lower, x1, f1 = x1, x2, f2
            x2 = lower + (upper - lower) / phi
            f2 = objective(x2)
        else:
            upper, x2, f2 = x2, x1, f1
            x1 = upper - (upper - lower) / phi
            f1 = objective(x1)
    estimate = (lower + upper) / 2.0
    return 0.0 if objective(0.0) >= objective(estimate) else max(0.0, estimate)


def _source_critical_z(input_confidence: float) -> float:
    """Return the normal quantile used to invert a printed source interval."""
    if not math.isfinite(input_confidence) or not 0 < input_confidence < 1:
        raise MetaAnalysisError("Input confidence must be between zero and one")
    # Preserve the conventional 1.96 reconstruction used by most printed 95%
    # intervals and by the versioned regression fixture. Use the exact normal
    # quantile for other confidence levels.
    if math.isclose(input_confidence, 0.95, rel_tol=0.0, abs_tol=1e-15):
        return 1.96
    return NormalDist().inv_cdf(1.0 - (1.0 - input_confidence) / 2.0)


def _analysis_vectors(
    records: Sequence[MetaRecord], input_confidence: float
) -> tuple[list[float], list[float], str, list[float]]:
    # Validate the global default even when every row overrides it.
    _source_critical_z(input_confidence)
    measure_families = {"ratio" if record.measure in RATIO_MEASURES else "linear" for record in records}
    if len(measure_families) != 1:
        raise MetaAnalysisError("Ratio and linear effect scales cannot be pooled")
    scale = next(iter(measure_families))
    values: list[float] = []
    variances: list[float] = []
    row_confidences: list[float] = []
    for record in records:
        # A per-row input_confidence column wins over the global default so that a
        # dataset mixing 95% and 90% printed intervals is inverted row by row.
        row_confidence = (
            record.input_confidence if record.input_confidence is not None else input_confidence
        )
        z_value = _source_critical_z(row_confidence)
        if scale == "ratio":
            value = math.log(record.effect)
            standard_error = (math.log(record.upper) - math.log(record.lower)) / (2.0 * z_value)
        else:
            value = record.effect
            standard_error = (record.upper - record.lower) / (2.0 * z_value)
        if not math.isfinite(standard_error) or standard_error <= 0:
            raise MetaAnalysisError(f"Invalid reconstructed standard error for {record.study_id}")
        values.append(value)
        variances.append(standard_error * standard_error)
        row_confidences.append(row_confidence)
    return values, variances, scale, row_confidences


def meta_analysis(
    records: Sequence[MetaRecord],
    *,
    model: str = "random",
    tau2_method: str = "DL",
    inference: str = "normal",
    confidence: float = 0.95,
    input_confidence: float = 0.95,
    prediction_df: str = "k-2",
    allow_mixed_estimands: bool = False,
    allow_dependence: bool = False,
    leave_one_out: bool = False,
) -> dict:
    """Fit an intercept-only aggregate inverse-variance meta-analysis."""
    if len(records) < 2:
        raise MetaAnalysisError("At least two study estimates are required")
    analysis_ids = {record.analysis_id for record in records}
    if len(analysis_ids) > 1:
        raise MetaAnalysisError(
            "Multiple analysis_id values cannot be pooled together; select one headline pool"
        )
    for record in records:
        _validate_record(record)
    measures = sorted({record.measure for record in records})
    warnings: list[str] = []
    if len(measures) > 1:
        if set(measures).issubset(LINEAR_MEASURES):
            raise MetaAnalysisError(
                "Different linear effect measures such as MD and SMD are on different units, are not commensurable, and cannot use the mixed-estimand override"
            )
        if not set(measures).issubset(RATIO_MEASURES):
            raise MetaAnalysisError(
                "Ratio measures cannot be pooled with linear measures such as MD or SMD: the two effect scales are not commensurable and the mixed-estimand override does not apply"
            )
        if not allow_mixed_estimands:
            raise MetaAnalysisError(
                "Mixed effect measures are not pooled by default; analyze a common estimand or use the explicit published-reconstruction override"
            )
        warnings.append(
            "Mixed hazard ratios, risk ratios, or odds ratios: a random-effects model does not harmonize estimands; this override is for published reconstruction only."
        )
    unresolved = [
        record.study_id
        for record in records
        if record.participant_overlap_possible and record.overlap_status in UNRESOLVED_OVERLAP_STATUSES
    ]
    if unresolved:
        if not allow_dependence:
            raise MetaAnalysisError(
                "Possible unresolved participant dependence or cohort overlap; deduplicate, delete by cluster, or use a dependence-aware model"
            )
        warnings.append(
            "Possible unresolved dependence was explicitly allowed for reconstruction; conventional inverse-variance uncertainty may be too narrow."
        )
    cohort_counts: dict[str, int] = {}
    for record in records:
        cohort_counts[record.cohort_id] = cohort_counts.get(record.cohort_id, 0) + 1
    unresolved_repeated = sorted(
        {
            record.cohort_id
            for record in records
            if cohort_counts[record.cohort_id] > 1
            and record.overlap_status != "resolved_independent"
        }
    )
    if unresolved_repeated:
        if not allow_dependence:
            raise MetaAnalysisError(
                "Repeated cohort rows have unresolved dependence; mark verified disjoint samples as resolved_independent, deduplicate, or use a dependence-aware model"
            )
        warnings.append(
            "Repeated cohort rows without verified independence were explicitly allowed for published reconstruction."
        )
    invalid_outcomes = sum(
        record.outcome_provenance == "DERIVED_INVALID_OR_UNJUSTIFIED" for record in records
    )
    assumption_exposures = sum(
        record.exposure_provenance == "DERIVED_ASSUMPTION_DEPENDENT" for record in records
    )
    if invalid_outcomes:
        warnings.append(f"{invalid_outcomes} row(s) have invalid or unjustified outcome provenance.")
    if assumption_exposures:
        warnings.append(f"{assumption_exposures} row(s) have assumption-dependent exposure provenance.")

    values, variances, scale, row_confidences = _analysis_vectors(records, input_confidence)
    fixed_weights = [1.0 / variance for variance in variances]
    fixed_estimate = _weighted_mean(values, fixed_weights)
    q_value = sum(
        weight * (value - fixed_estimate) ** 2
        for weight, value in zip(fixed_weights, values)
    )
    degrees_of_freedom = len(values) - 1
    i2 = max(0.0, (q_value - degrees_of_freedom) / q_value) * 100.0 if q_value > 0 else 0.0

    normalized_model = model.strip().lower()
    method = tau2_method.strip().upper()
    normalized_inference = inference.strip().upper()
    if normalized_model == "fixed" and normalized_inference == "HKSJ":
        raise MetaAnalysisError("HKSJ inference is implemented only for random-effects models")
    if normalized_model == "fixed":
        tau2 = 0.0
        method = "NONE"
    elif normalized_model == "random":
        estimators = {"DL": _tau2_dl, "PM": _tau2_pm, "REML": _tau2_reml}
        if method not in estimators:
            raise MetaAnalysisError("tau2_method must be DL, PM, or REML")
        tau2 = estimators[method](values, variances)
    else:
        raise MetaAnalysisError("model must be fixed or random")

    weights = [1.0 / (variance + tau2) for variance in variances]
    pooled_linear = _weighted_mean(values, weights)
    conventional_se = math.sqrt(1.0 / sum(weights))
    hksj_q = None
    if normalized_inference == "NORMAL":
        standard_error = conventional_se
        critical = NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)
    elif normalized_inference == "HKSJ":
        hksj_q = sum(
            weight * (value - pooled_linear) ** 2
            for weight, value in zip(weights, values)
        ) / degrees_of_freedom
        if not math.isfinite(hksj_q) or hksj_q <= _HKSJ_MINIMUM_SCALE_FACTOR:
            raise MetaAnalysisError(
                "The Hartung-Knapp-Sidik-Jonkman scale factor is "
                f"{hksj_q:.3g}, so the interval would be at least "
                f"{1.0 / math.sqrt(_HKSJ_MINIMUM_SCALE_FACTOR):.0f} times narrower than the "
                "conventional interval: the study estimates carry no residual dispersion "
                "distinguishable from rounding, the interval is not estimable, and a "
                "collapsed interval will not be reported"
            )
        standard_error = math.sqrt(hksj_q / sum(weights))
        critical = _student_t_quantile(1.0 - (1.0 - confidence) / 2.0, degrees_of_freedom)
        if hksj_q < 1.0:
            warnings.append(
                "Unmodified Hartung-Knapp-Sidik-Jonkman scale factor is below one; the interval can be narrower than the conventional interval."
            )
    else:
        raise MetaAnalysisError("inference must be normal or HKSJ")

    lower_linear = pooled_linear - critical * standard_error
    upper_linear = pooled_linear + critical * standard_error

    prediction_convention = str(prediction_df).strip().lower()
    if prediction_convention not in PREDICTION_DF_CONVENTIONS:
        raise MetaAnalysisError("prediction_df must be k-2 or k-1")
    prediction_degrees_of_freedom: int | None = len(values) - (
        2 if prediction_convention == "k-2" else 1
    )
    prediction_reason: str | None = None
    prediction_lower_linear = None
    prediction_upper_linear = None
    if normalized_model != "random":
        prediction_degrees_of_freedom = None
        prediction_reason = "A fixed-effect model has no between-study distribution to predict"
    elif prediction_degrees_of_freedom < 1:
        prediction_reason = (
            f"A prediction interval on {prediction_convention} degrees of freedom is not "
            f"estimable with k={len(values)}"
        )
        prediction_degrees_of_freedom = None
    else:
        prediction_critical = _student_t_quantile(
            1.0 - (1.0 - confidence) / 2.0, prediction_degrees_of_freedom
        )
        # A prediction interval describes the distribution of true effects, so it is
        # always built from the conventional inverse-variance standard error and never
        # from an inference-specific (for example HKSJ) standard error.
        prediction_se = math.sqrt(conventional_se * conventional_se + tau2)
        prediction_lower_linear = pooled_linear - prediction_critical * prediction_se
        prediction_upper_linear = pooled_linear + prediction_critical * prediction_se

    transform = math.exp if scale == "ratio" else lambda value: value
    cohort_cluster_count = len({record.cohort_id for record in records})
    if normalized_model == "random" and cohort_cluster_count < 5:
        warnings.append(
            "The random-effects prediction interval is highly unstable with fewer than five cohort clusters."
        )
    result = {
        "k": len(records),
        "cohort_clusters": cohort_cluster_count,
        "model": normalized_model,
        "tau2_method": method,
        "inference": normalized_inference,
        "confidence": confidence,
        "input_confidence": input_confidence,
        "input_confidence_levels": sorted(set(row_confidences)),
        "scale": "log_ratio" if scale == "ratio" else "linear",
        "measures": measures,
        "pooled_linear": pooled_linear,
        "standard_error_linear": standard_error,
        "conventional_standard_error_linear": conventional_se,
        "pooled": transform(pooled_linear),
        "ci_lower": transform(lower_linear),
        "ci_upper": transform(upper_linear),
        "Q": q_value,
        "Q_degrees_of_freedom": degrees_of_freedom,
        "tau2": tau2,
        "I2_percent": i2,
        "hksj_scale_q": hksj_q,
        "prediction_df_convention": prediction_convention,
        "prediction_interval_df": prediction_degrees_of_freedom,
        "prediction_not_estimable_reason": prediction_reason,
        "prediction_lower": transform(prediction_lower_linear) if prediction_lower_linear is not None else None,
        "prediction_upper": transform(prediction_upper_linear) if prediction_upper_linear is not None else None,
        "warnings": warnings,
        "study_weights_percent": [
            {"study_id": record.study_id, "cohort_id": record.cohort_id, "weight": weight / sum(weights) * 100.0}
            for record, weight in zip(records, weights)
        ],
    }
    if leave_one_out:
        result["leave_one_out"] = _leave_one_cluster_out(
            records,
            model=normalized_model,
            tau2_method=tau2_method,
            inference=inference,
            confidence=confidence,
            input_confidence=input_confidence,
            prediction_df=prediction_convention,
            allow_mixed_estimands=allow_mixed_estimands,
            allow_dependence=allow_dependence,
            full_result=result,
        )
    return result


def _leave_one_cluster_out(
    records: Sequence[MetaRecord],
    *,
    model: str,
    tau2_method: str,
    inference: str,
    confidence: float,
    input_confidence: float,
    prediction_df: str,
    allow_mixed_estimands: bool,
    allow_dependence: bool,
    full_result: dict,
) -> list[dict]:
    output: list[dict] = []
    null = 1.0 if full_result["scale"] == "log_ratio" else 0.0
    full_excludes_null = not (full_result["ci_lower"] <= null <= full_result["ci_upper"])
    for cohort_id in dict.fromkeys(record.cohort_id for record in records):
        retained = [record for record in records if record.cohort_id != cohort_id]
        if len(retained) < 2:
            output.append({"deleted_cohort_id": cohort_id, "status": "not_estimable"})
            continue
        fitted = meta_analysis(
            retained,
            model=model,
            tau2_method=tau2_method,
            inference=inference,
            confidence=confidence,
            input_confidence=input_confidence,
            prediction_df=prediction_df,
            allow_mixed_estimands=allow_mixed_estimands,
            allow_dependence=allow_dependence,
            leave_one_out=False,
        )
        excludes_null = not (fitted["ci_lower"] <= null <= fitted["ci_upper"])
        output.append(
            {
                "deleted_cohort_id": cohort_id,
                "deleted_study_ids": [record.study_id for record in records if record.cohort_id == cohort_id],
                "pooled": fitted["pooled"],
                "ci_lower": fitted["ci_lower"],
                "ci_upper": fitted["ci_upper"],
                "tau2": fitted["tau2"],
                "I2_percent": fitted["I2_percent"],
                "changes_null_exclusion": excludes_null != full_excludes_null,
            }
        )
    return output


def run_sensitivity_ladder(
    records: Sequence[MetaRecord],
    *,
    model: str = "random",
    tau2_method: str = "DL",
    common_measure: str | None = None,
    confidence: float = 0.95,
    input_confidence: float = 0.95,
    prediction_df: str = "k-2",
    allow_dependence: bool = False,
    allow_mixed_estimands: bool = False,
) -> list[dict]:
    """Run a deterministic provenance/estimand/method sensitivity ladder."""
    if not records:
        raise MetaAnalysisError("The sensitivity ladder has no records")
    normalized_model = str(model).strip().lower()
    if normalized_model not in {"fixed", "random"}:
        raise MetaAnalysisError("model must be fixed or random")
    measure = common_measure.upper() if common_measure else None
    if len({record.measure for record in records}) > 1 and measure is None:
        raise MetaAnalysisError("A common_measure is required for a mixed-measure sensitivity ladder")

    def fit(subset: Sequence[MetaRecord], **options: object) -> dict:
        # Every rung reproduces the model the caller validated at the reproduction
        # gate unless a rung explicitly overrides it, and every returned payload
        # states which model produced it.
        rung_model = str(options.pop("model", normalized_model))
        try:
            return meta_analysis(
                subset,
                model=rung_model,
                tau2_method=str(options.pop("tau2_method", tau2_method)),
                confidence=confidence,
                input_confidence=input_confidence,
                prediction_df=prediction_df,
                allow_mixed_estimands=bool(options.pop("allow_mixed_estimands", False)),
                allow_dependence=bool(options.pop("allow_dependence", False)),
                **options,
            )
        except MetaAnalysisError as exc:
            return {
                "status": "NOT_ASSESSABLE",
                "model": rung_model,
                "reason": str(exc),
                "k": len(subset),
            }

    # S6 compares between-study variance estimators and S7 is HKSJ inference; both
    # are defined only for random-effects synthesis, so a fixed-effect request must
    # skip them rather than silently publish random-effects numbers.
    random_only_skip = {
        "status": "NOT_ASSESSABLE",
        "model": normalized_model,
        "reason": (
            "This rung is defined only for random-effects synthesis and was skipped because the "
            "requested model is fixed effect; rerun with --model random to assess it."
        ),
    }

    direct_outcomes = filter_records(records, direct_outcomes_only=True, published_only=False)
    common = filter_records(records, common_measure=measure, published_only=False) if measure else list(records)
    direct_common = filter_records(
        records,
        direct_outcomes_only=True,
        common_measure=measure,
        published_only=False,
    )
    direct_exposure = filter_records(
        direct_common,
        direct_exposures_only=True,
        published_only=False,
    )
    ladder = [
        {
            "id": "S1_published_reconstruction",
            "description": "All published rows; mixed-measure override only when needed",
            "result": fit(
                records,
                allow_mixed_estimands=allow_mixed_estimands,
                allow_dependence=allow_dependence,
            ),
        },
        {
            "id": "S2_direct_outcomes",
            "description": "Only direct or validly derived outcomes",
            "result": fit(
                direct_outcomes,
                allow_mixed_estimands=allow_mixed_estimands,
            ),
        },
        {
            "id": "S3_common_measure",
            "description": f"Only the prespecified common measure ({measure or 'not specified'})",
            "result": fit(common, allow_mixed_estimands=measure is None and len({item.measure for item in common}) > 1),
        },
        {
            "id": "S4_direct_outcome_common_measure",
            "description": "Direct outcomes and a common effect measure",
            "result": fit(direct_common, allow_mixed_estimands=measure is None and len({item.measure for item in direct_common}) > 1),
        },
        {
            "id": "S5_direct_exposure",
            "description": "Also remove assumption-dependent or unjustified exposure derivations",
            "result": fit(direct_exposure, allow_mixed_estimands=measure is None and len({item.measure for item in direct_exposure}) > 1),
        },
        {
            "id": "S6_alternative_tau2",
            "description": "Compare DerSimonian-Laird, Paule-Mandel, and restricted maximum likelihood",
            "result": dict(random_only_skip)
            if normalized_model == "fixed"
            else {
                method: fit(direct_common, tau2_method=method, allow_mixed_estimands=False)
                for method in ("DL", "PM", "REML")
            },
        },
        {
            "id": "S7_hksj",
            "description": "Hartung-Knapp-Sidik-Jonkman inference on the clean common-measure model",
            "result": dict(random_only_skip)
            if normalized_model == "fixed"
            else fit(direct_common, inference="HKSJ", allow_mixed_estimands=False),
        },
        {
            "id": "S8_leave_one_cluster_out",
            "description": "Delete and refit one independent cohort cluster at a time",
            "result": fit(direct_common, leave_one_out=True, allow_mixed_estimands=False),
        },
    ]
    for step in ladder:
        step["model"] = normalized_model
    return ladder


def _human_summary(result: dict) -> str:
    lines = [
        f"Pooled effect: {result['pooled']:.6g} ({result['confidence']:.0%} CI {result['ci_lower']:.6g} to {result['ci_upper']:.6g})",
        f"Model: {result['model']}; tau-squared method: {result['tau2_method']}; inference: {result['inference']}",
        f"k={result['k']}; Q={result['Q']:.6g}; tau-squared={result['tau2']:.6g}; I-squared={result['I2_percent']:.2f}%",
    ]
    if result["prediction_lower"] is not None:
        lines.append(
            f"Prediction interval: {result['prediction_lower']:.6g} to {result['prediction_upper']:.6g} "
            f"(Student t on {result['prediction_interval_df']} degrees of freedom; "
            f"convention {result['prediction_df_convention']})"
        )
    elif result.get("prediction_not_estimable_reason"):
        lines.append(
            f"Prediction interval: not reported ({result['prediction_not_estimable_reason']})"
        )
    if result["warnings"]:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result["warnings"])
    return "\n".join(lines)


def _human_sensitivity_summary(payload: dict) -> str:
    reproduction = payload.get("published_reproduction")
    lines = [f"Sensitivity status: {payload['sensitivity_status']}"]
    if reproduction:
        lines.append(
            f"Published reconstruction: {reproduction['status']} "
            f"(observed {reproduction['observed']:.6g}; expected {reproduction['expected']:.6g}; "
            f"absolute difference {reproduction['absolute_difference']:.6g})"
        )
    for step in payload.get("sensitivity_ladder", []):
        result = step["result"]
        model = step.get("model") or (result.get("model") if isinstance(result, dict) else None)
        label = f"{step['id']} [{model or 'unspecified model'}]"
        if isinstance(result, dict) and "pooled" in result:
            lines.append(
                f"{label}: {result['pooled']:.6g} "
                f"({result['ci_lower']:.6g} to {result['ci_upper']:.6g})"
            )
        elif isinstance(result, dict) and result.get("status"):
            lines.append(f"{label}: {result['status']}: {result.get('reason', '')}")
        else:
            lines.append(f"{label}: model comparison or influence output")
    if payload["sensitivity_status"].startswith("BLOCKED"):
        lines.append("Do not interpret sensitivity analyses until the reproduction discrepancy is explained.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--analysis-id")
    parser.add_argument("--model", choices=("fixed", "random"), default="random")
    parser.add_argument("--tau2", choices=("DL", "PM", "REML"), default="DL")
    parser.add_argument("--inference", choices=("normal", "HKSJ"), default="normal")
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument(
        "--input-confidence",
        type=float,
        default=0.95,
        help="Confidence level of the source intervals used to reconstruct standard errors",
    )
    parser.add_argument(
        "--prediction-df",
        choices=PREDICTION_DF_CONVENTIONS,
        default="k-2",
        help=(
            "Degrees-of-freedom convention for the random-effects prediction interval: "
            "k-2 follows the Cochrane Handbook and Higgins-Thompson-Spiegelhalter; k-1 "
            "reproduces the earlier behaviour of this script"
        ),
    )
    parser.add_argument("--direct-outcomes-only", action="store_true")
    parser.add_argument("--direct-exposures-only", action="store_true")
    parser.add_argument("--common-measure")
    parser.add_argument("--allow-mixed-estimands", action="store_true")
    parser.add_argument("--allow-dependence", action="store_true")
    parser.add_argument("--leave-one-out", action="store_true")
    parser.add_argument("--sensitivity", choices=("all",))
    parser.add_argument("--forest", type=Path)
    parser.add_argument("--title", default="Meta-analysis reconstruction")
    parser.add_argument("--expected-pooled", type=float)
    parser.add_argument("--reproduction-tolerance", type=float, default=0.005)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    exit_status = 0
    try:
        loaded_records = load_records(args.dataset)
        base_records = filter_records(loaded_records, analysis_id=args.analysis_id)
        if not base_records:
            raise MetaAnalysisError("No records remain after filtering")
        if args.sensitivity:
            if len({record.measure for record in base_records}) > 1 and not args.allow_mixed_estimands:
                raise MetaAnalysisError(
                    "Sensitivity analysis must explicitly use --allow-mixed-estimands to reconstruct a mixed published pool"
                )
            if len({record.measure for record in base_records}) > 1 and not args.common_measure:
                raise MetaAnalysisError("--common-measure is required for mixed-measure sensitivity analysis")
            published = meta_analysis(
                base_records,
                model=args.model,
                tau2_method=args.tau2,
                inference=args.inference,
                confidence=args.confidence,
                input_confidence=args.input_confidence,
                prediction_df=args.prediction_df,
                allow_mixed_estimands=args.allow_mixed_estimands,
                allow_dependence=args.allow_dependence,
            )
            reproduction = None
            if args.expected_pooled is not None:
                absolute_difference = abs(published["pooled"] - args.expected_pooled)
                reproduction = {
                    "observed": published["pooled"],
                    "expected": args.expected_pooled,
                    "absolute_difference": absolute_difference,
                    "tolerance": args.reproduction_tolerance,
                    "status": "PASS" if absolute_difference <= args.reproduction_tolerance else "FAIL",
                }
            if reproduction and reproduction["status"] == "FAIL":
                exit_status = 2
                result = {
                    "published_reconstruction": reproduction,
                    "sensitivity_status": "BLOCKED_REPRODUCTION_FAILURE",
                    "sensitivity_ladder": [],
                }
            else:
                result = {
                    "published_reconstruction": reproduction,
                    "sensitivity_status": "READY",
                    "sensitivity_ladder": run_sensitivity_ladder(
                        base_records,
                        model=args.model,
                        tau2_method=args.tau2,
                        common_measure=args.common_measure,
                        confidence=args.confidence,
                        input_confidence=args.input_confidence,
                        prediction_df=args.prediction_df,
                        allow_dependence=args.allow_dependence,
                        allow_mixed_estimands=args.allow_mixed_estimands,
                    ),
                }
        else:
            records = filter_records(
                base_records,
                direct_outcomes_only=args.direct_outcomes_only,
                direct_exposures_only=args.direct_exposures_only,
                common_measure=args.common_measure,
                published_only=False,
            )
            if not records:
                raise MetaAnalysisError("No records remain after filtering")
            result = meta_analysis(
                records,
                model=args.model,
                tau2_method=args.tau2,
                inference=args.inference,
                confidence=args.confidence,
                input_confidence=args.input_confidence,
                prediction_df=args.prediction_df,
                allow_mixed_estimands=args.allow_mixed_estimands,
                allow_dependence=args.allow_dependence,
                leave_one_out=args.leave_one_out,
            )
            if args.expected_pooled is not None:
                absolute_difference = abs(result["pooled"] - args.expected_pooled)
                result["published_reproduction"] = {
                    "expected": args.expected_pooled,
                    "absolute_difference": absolute_difference,
                    "tolerance": args.reproduction_tolerance,
                    "status": "PASS" if absolute_difference <= args.reproduction_tolerance else "FAIL",
                }
                if result["published_reproduction"]["status"] == "FAIL":
                    exit_status = 2
            if args.forest:
                from plot_forest import write_forest_svg

                write_forest_svg(records, result, args.forest, title=args.title)
                result["forest_file"] = str(args.forest)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        elif args.sensitivity:
            print(_human_sensitivity_summary(result))
        else:
            print(_human_summary(result))
        return exit_status
    except (MetaAnalysisError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
