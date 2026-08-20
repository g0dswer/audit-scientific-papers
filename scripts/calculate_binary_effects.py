#!/usr/bin/env python3
"""Absolute effects for a two-arm binary outcome.

The risk-difference interval uses Newcombe's hybrid score method (method 10),
combining independent Wilson score intervals without a continuity correction.
"""

from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
from numbers import Integral, Real
from statistics import NormalDist
from typing import Any


def _validate_confidence(confidence: float) -> float:
    if isinstance(confidence, bool) or not isinstance(confidence, Real):
        raise ValueError("confidence must be a finite number in (0, 1)")
    confidence = float(confidence)
    if not math.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be a finite number in (0, 1)")
    return confidence


def _validate_count(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    value = int(value)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _validate_events_total(events: int, total: int, events_name: str, total_name: str) -> tuple[int, int]:
    events = _validate_count(events, events_name)
    total = _validate_count(total, total_name)
    if total == 0:
        raise ValueError(f"{total_name} must be greater than zero")
    if events > total:
        raise ValueError(f"{events_name} cannot exceed {total_name}")
    return events, total


def _z_value(confidence: float) -> float:
    confidence = _validate_confidence(confidence)
    return NormalDist().inv_cdf(0.5 + confidence / 2.0)


def wilson_interval(events: int, total: int, confidence: float) -> tuple[float, float]:
    """Return the Wilson score interval for one binomial risk."""

    events, total = _validate_events_total(events, total, "events", "total")
    z = _z_value(confidence)
    z2 = z * z
    risk = events / total
    denominator = 1.0 + z2 / total
    centre = (risk + z2 / (2.0 * total)) / denominator
    half_width = (
        z
        * math.sqrt(risk * (1.0 - risk) / total + z2 / (4.0 * total * total))
        / denominator
    )
    lower = centre - half_width
    upper = centre + half_width
    if math.isclose(lower, 0.0, abs_tol=1e-15):
        lower = 0.0
    if math.isclose(upper, 1.0, abs_tol=1e-15):
        upper = 1.0
    return max(0.0, lower), min(1.0, upper)


def newcombe_difference_interval(
    e1: int, n1: int, e0: int, n0: int, confidence: float
) -> tuple[float, float]:
    """Return Newcombe method 10's score interval for risk1 minus risk0.

    This is the hybrid score construction from the two independent Wilson
    intervals, without continuity correction.
    """

    e1, n1 = _validate_events_total(e1, n1, "e1", "n1")
    e0, n0 = _validate_events_total(e0, n0, "e0", "n0")
    _validate_confidence(confidence)

    risk1 = e1 / n1
    risk0 = e0 / n0
    lower1, upper1 = wilson_interval(e1, n1, confidence)
    lower0, upper0 = wilson_interval(e0, n0, confidence)
    difference = risk1 - risk0

    lower = difference - math.sqrt((risk1 - lower1) ** 2 + (upper0 - risk0) ** 2)
    upper = difference + math.sqrt((upper1 - risk1) ** 2 + (risk0 - lower0) ** 2)
    return max(-1.0, lower), min(1.0, upper)


def _ceil_positive(value: float | Fraction | None) -> int | None:
    """Conservatively round a positive NNT/NNH away from zero."""

    if value is None or value <= 0:
        return None
    if isinstance(value, Fraction):
        # NNT/NNH values computed from integer counts are exact rational
        # numbers.  Taking the ceiling while they are still a Fraction avoids
        # turning an exact integer such as 12 into 12.000000000000004.
        return (value.numerator + value.denominator - 1) // value.denominator
    if not math.isfinite(value):
        return None
    nearest_integer = round(value)
    if nearest_integer > 0 and abs(value - nearest_integer) <= math.ulp(float(nearest_integer)):
        value = float(nearest_integer)
    return int(math.ceil(value))


def _risk_ratio(risk1: float, risk0: float) -> float | None:
    if risk0 == 0.0:
        return None
    return risk1 / risk0


def _odds_ratio(e1: int, n1: int, e0: int, n0: int) -> float | None:
    numerator = e1 * (n0 - e0)
    denominator = (n1 - e1) * e0
    if denominator == 0:
        return None
    return numerator / denominator


def _risk_ratio_interval(
    e1: int, n1: int, e0: int, n0: int, confidence: float
) -> dict[str, Any] | None:
    """Katz large-sample interval: SE(log RR) = sqrt(1/e1 - 1/n1 + 1/e0 - 1/n0).

    A zero event count in either arm makes the log-scale variance undefined.
    The interval is then an explicit null: no continuity correction is added,
    matching the point estimate's contract.
    """

    risk_ratio = _risk_ratio(e1 / n1, e0 / n0)
    if risk_ratio is None or e1 == 0:
        return None
    standard_error = math.sqrt(1.0 / e1 - 1.0 / n1 + 1.0 / e0 - 1.0 / n0)
    z = _z_value(confidence)
    log_estimate = math.log(risk_ratio)
    return {
        "lower": math.exp(log_estimate - z * standard_error),
        "upper": math.exp(log_estimate + z * standard_error),
        "log_estimate": log_estimate,
        "log_standard_error": standard_error,
        "method": "katz_log",
        "approximate": True,
    }


def _odds_ratio_interval(
    e1: int, n1: int, e0: int, n0: int, confidence: float
) -> dict[str, Any] | None:
    """Woolf large-sample interval: SE(log OR) = sqrt(1/a + 1/b + 1/c + 1/d).

    Any zero cell makes the log-scale variance undefined.  The interval is then
    an explicit null: no continuity correction is added, matching the point
    estimate's contract.
    """

    odds_ratio = _odds_ratio(e1, n1, e0, n0)
    cells = (e1, n1 - e1, e0, n0 - e0)
    if odds_ratio is None or odds_ratio <= 0.0 or any(cell == 0 for cell in cells):
        return None
    standard_error = math.sqrt(sum(1.0 / cell for cell in cells))
    z = _z_value(confidence)
    log_estimate = math.log(odds_ratio)
    return {
        "lower": math.exp(log_estimate - z * standard_error),
        "upper": math.exp(log_estimate + z * standard_error),
        "log_estimate": log_estimate,
        "log_standard_error": standard_error,
        "method": "woolf_log",
        "approximate": True,
    }


def _fisher_exact_two_sided(e1: int, n1: int, e0: int, n0: int) -> float | None:
    """Return SciPy's optional two-sided Fisher value, or None if unavailable.

    SciPy is an optional dependency.  Only an actually missing SciPy import is
    treated as an unavailable optional result.  A broken installation, an
    incompatible API, or a calculation failure is allowed to propagate so
    that callers can distinguish "not installed" from a programming or
    numerical error.  SciPy 1.10 and later return a ``SignificanceResult``
    carrying ``.pvalue``; earlier releases returned a bare
    ``(odds_ratio, p_value)`` tuple.  Both shapes are accepted.
    """

    try:
        from scipy.stats import fisher_exact  # type: ignore
    except ModuleNotFoundError as error:
        # Do not mask a missing transitive dependency (for example numpy) or
        # any other import problem as if SciPy simply were not installed.
        if error.name == "scipy" or (error.name and error.name.startswith("scipy.")):
            return None
        raise
    except ImportError as error:
        # A genuine missing SciPy package can be reported as ImportError by a
        # custom importer.  Import errors from an installed/broken package are
        # deliberately not swallowed.
        if error.name == "scipy" or (error.name and error.name.startswith("scipy.")):
            return None
        raise

    table = [[e1, n1 - e1], [e0, n0 - e0]]
    outcome = fisher_exact(table, alternative="two-sided")
    p_value = getattr(outcome, "pvalue", None)
    if p_value is None:
        # Legacy SciPy (< 1.10) returned a plain (odds_ratio, p_value) tuple.
        p_value = outcome[1]
    p_value = float(p_value)
    if not math.isfinite(p_value):
        raise ValueError("SciPy returned a non-finite Fisher exact p-value")
    return p_value


def _reciprocal_interval(
    signed_lower: float, signed_upper: float
) -> dict[str, Any] | None:
    if signed_lower > 0.0:
        lower = 1.0 / signed_upper
        upper = 1.0 / signed_lower
        return {
            "lower": lower,
            "upper": upper,
            "rounded_lower": _ceil_positive(lower),
            "rounded_upper": _ceil_positive(upper),
        }
    if signed_upper < 0.0:
        lower = 1.0 / abs(signed_lower)
        upper = 1.0 / abs(signed_upper)
        return {
            "lower": lower,
            "upper": upper,
            "rounded_lower": _ceil_positive(lower),
            "rounded_upper": _ceil_positive(upper),
        }
    return None


def _split_reciprocal_interval(signed_lower: float, signed_upper: float) -> dict[str, int | None]:
    benefit_from = _ceil_positive(1.0 / signed_upper) if signed_upper > 0.0 else None
    harm_from = _ceil_positive(1.0 / abs(signed_lower)) if signed_lower < 0.0 else None
    # Each side of a split reciprocal interval runs out to infinity at the
    # no-effect boundary, so the upper bounds are deliberately unbounded and
    # are emitted as explicit nulls rather than a finite number.
    return {
        "benefit_from": benefit_from,
        "benefit_to": None,
        "harm_from": harm_from,
        "harm_to": None,
    }


def analyze_binary(
    e1: int,
    n1: int,
    e0: int,
    n0: int,
    confidence: float = 0.95,
    beneficial: bool | None = None,
) -> dict[str, Any]:
    """Analyze event counts and return absolute and relative effects.

    ``risk_difference`` is always treatment risk minus comparator risk.  When
    ``beneficial`` is false, the clinical sign used for classification and
    NNT/NNH labeling is reversed because a higher event risk is undesirable.

    ``beneficial`` defaults to ``None``, meaning the event direction was not
    stated.  The historical default (event treated as desirable) is then kept,
    but the result carries an explicit notice, because most audited binary
    outcomes are harms and an unstated direction silently inverts the NNT/NNH
    labels.
    """

    e1, n1 = _validate_events_total(e1, n1, "e1", "n1")
    e0, n0 = _validate_events_total(e0, n0, "e0", "n0")
    confidence = _validate_confidence(confidence)
    if beneficial is not None and not isinstance(beneficial, bool):
        raise ValueError("beneficial must be a boolean or None")
    direction_specified = beneficial is not None
    if beneficial is None:
        beneficial = True
    direction_notice = (
        None
        if direction_specified
        else (
            "EVENT DIRECTION NOT SPECIFIED: the counted event was assumed to be "
            "BENEFICIAL (desirable), so NNT and NNH labels follow that "
            "assumption. Most audited binary outcomes are harms (death, "
            "infarction, relapse). Pass --harm for an undesirable event or "
            "--benefit to state the assumption explicitly."
        )
    )

    risk1 = e1 / n1
    risk0 = e0 / n0
    risk_difference = risk1 - risk0
    ci_lower, ci_upper = newcombe_difference_interval(e1, n1, e0, n0, confidence)

    sign = 1.0 if beneficial else -1.0
    signed_difference = sign * risk_difference
    signed_lower = sign * ci_lower if sign > 0 else -ci_upper
    signed_upper = sign * ci_upper if sign > 0 else -ci_lower

    if signed_lower > 0.0:
        classification = "clear_benefit"
    elif signed_upper < 0.0:
        classification = "clear_harm"
    else:
        classification = "inconclusive_crosses_zero"

    # Keep the point reciprocal on an exact count-derived scale.  The float
    # risk difference above remains the public numerical effect, but using it
    # for the reciprocal can turn an exact integer (for example 1/(5/10-5/12)
    # = 12) into a value infinitesimally above the integer and incorrectly
    # round it up.
    exact_risk_difference = Fraction(e1, n1) - Fraction(e0, n0)
    exact_signed_difference = (1 if beneficial else -1) * exact_risk_difference
    if exact_signed_difference > 0:
        point_label = "NNT"
        point_unrounded_exact = Fraction(1, 1) / exact_signed_difference
    elif exact_signed_difference < 0:
        point_label = "NNH"
        point_unrounded_exact = Fraction(1, 1) / abs(exact_signed_difference)
    else:
        point_label = None
        point_unrounded_exact = None

    point_unrounded = (
        float(point_unrounded_exact) if point_unrounded_exact is not None else None
    )

    point_estimate = {
        "label": point_label,
        "unrounded": point_unrounded,
        "rounded": _ceil_positive(point_unrounded_exact),
        "exploratory": classification == "inconclusive_crosses_zero",
    }
    if point_unrounded_exact is not None:
        point_estimate["exact_fraction"] = str(point_unrounded_exact)
    reciprocal_interval = _reciprocal_interval(signed_lower, signed_upper)
    split_interval = (
        _split_reciprocal_interval(signed_lower, signed_upper)
        if classification == "inconclusive_crosses_zero"
        else None
    )

    return {
        "events_treatment": e1,
        "total_treatment": n1,
        "events_control": e0,
        "total_control": n0,
        "risk_treatment": risk1,
        "risk_control": risk0,
        "risk_difference": risk_difference,
        "risk_difference_ci": {"lower": ci_lower, "upper": ci_upper},
        "clinical_risk_difference": signed_difference,
        "clinical_risk_difference_ci": {"lower": signed_lower, "upper": signed_upper},
        "classification": classification,
        "point_estimate": point_estimate,
        "reciprocal_interval": reciprocal_interval,
        "split_interval": split_interval,
        "risk_ratio": _risk_ratio(risk1, risk0),
        "risk_ratio_ci": _risk_ratio_interval(e1, n1, e0, n0, confidence),
        "odds_ratio": _odds_ratio(e1, n1, e0, n0),
        "odds_ratio_ci": _odds_ratio_interval(e1, n1, e0, n0, confidence),
        "relative_effect_note": (
            "Risk-ratio and odds-ratio intervals are large-sample "
            "approximations computed on the log scale (Katz and Woolf "
            "respectively) and back-transformed. No continuity correction is "
            "applied: when a cell entering the standard error is zero the "
            "interval is an explicit null, not a hidden finite estimate."
        ),
        "confidence": confidence,
        "beneficial_event": beneficial,
        "event_direction": "beneficial" if beneficial else "harmful",
        "event_direction_specified": direction_specified,
        "event_direction_notice": direction_notice,
        "fisher_exact_p_two_sided": _fisher_exact_two_sided(e1, n1, e0, n0),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_treatment", type=int)
    parser.add_argument("total_treatment", type=int)
    parser.add_argument("events_control", type=int)
    parser.add_argument("total_control", type=int)
    direction = parser.add_mutually_exclusive_group()
    direction.add_argument("--harm", action="store_true", help="treat the event as undesirable")
    direction.add_argument(
        "--benefit",
        action="store_true",
        help="treat the event as desirable (the assumed default, stated explicitly)",
    )
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def _print_relative_effect(
    label: str, estimate: float | None, interval: dict[str, Any] | None, confidence: float
) -> None:
    if estimate is None:
        print(f"{label}: undefined (zero cell; no continuity correction applied)")
        return
    if interval is None:
        print(
            f"{label}: {estimate:.6g} "
            f"({confidence:.0%} CI undefined: zero cell, no continuity correction applied)"
        )
        return
    print(
        f"{label}: {estimate:.6g} "
        f"(large-sample {confidence:.0%} CI [{interval['lower']:.6g}, "
        f"{interval['upper']:.6g}], {interval['method']})"
    )


def _cli_direction(harm: bool, benefit: bool) -> bool | None:
    """Map the mutually exclusive direction flags onto ``beneficial``."""

    if harm:
        return False
    if benefit:
        return True
    return None


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = analyze_binary(
            args.events_treatment,
            args.total_treatment,
            args.events_control,
            args.total_control,
            confidence=args.confidence,
            beneficial=_cli_direction(args.harm, args.benefit),
        )
    except ValueError as error:
        parser.error(str(error))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))
    else:
        if result["classification"] == "inconclusive_crosses_zero":
            print("Binary effect inconclusive: risk-difference interval crosses zero")
        else:
            print(f"Binary effect: {result['classification']}")
        print(f"Event direction: {result['event_direction']}")
        if result["event_direction_notice"] is not None:
            print("NOTICE: " + result["event_direction_notice"])
        print(f"Treatment risk: {result['risk_treatment']:.6g}")
        print(f"Control risk: {result['risk_control']:.6g}")
        print(f"Risk difference: {result['risk_difference']:.6g}")
        ci = result["risk_difference_ci"]
        print(f"Risk-difference {result['confidence']:.0%} CI: [{ci['lower']:.6g}, {ci['upper']:.6g}]")
        estimate = result["point_estimate"]
        if estimate["label"] is None:
            print("Point reciprocal: undefined (zero risk difference)")
        else:
            print(f"{estimate['label']}: {estimate['unrounded']:.6g} (rounded {estimate['rounded']})")
        if result["split_interval"] is not None:
            split = result["split_interval"]
            benefit_side = (
                f"possible benefit NNT >= {split['benefit_from']}"
                if split["benefit_from"] is not None
                else "no possible benefit side (interval bound at zero)"
            )
            harm_side = (
                f"possible harm NNH >= {split['harm_from']}"
                if split["harm_from"] is not None
                else "no possible harm side (interval bound at zero)"
            )
            print(
                "Split reciprocal interval: "
                f"{benefit_side}; no effect at infinity; {harm_side}"
            )
        elif result["reciprocal_interval"] is not None:
            interval = result["reciprocal_interval"]
            print(
                f"Reciprocal {result['confidence']:.0%} CI: "
                f"[{interval['lower']:.6g}, {interval['upper']:.6g}]"
            )
        _print_relative_effect(
            "Risk ratio", result["risk_ratio"], result["risk_ratio_ci"], result["confidence"]
        )
        _print_relative_effect(
            "Odds ratio", result["odds_ratio"], result["odds_ratio_ci"], result["confidence"]
        )
        print(result["relative_effect_note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
