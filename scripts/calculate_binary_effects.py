#!/usr/bin/env python3
"""Absolute effects for a two-arm binary outcome.

The risk-difference interval uses Newcombe's hybrid score method (method 10),
combining independent Wilson score intervals without a continuity correction.
"""

from __future__ import annotations

import argparse
import json
import math
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


def _ceil_positive(value: float | None) -> int | None:
    """Conservatively round a positive NNT/NNH away from zero."""

    if value is None or not math.isfinite(value) or value <= 0.0:
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


def _fisher_exact_two_sided(e1: int, n1: int, e0: int, n0: int) -> float | None:
    """Return SciPy's optional two-sided Fisher value, or None if unavailable."""

    try:
        from scipy.stats import fisher_exact  # type: ignore
    except ImportError:
        return None
    table = [[e1, n1 - e1], [e0, n0 - e0]]
    return float(fisher_exact(table, alternative="two-sided").pvalue)


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
    return {
        "benefit_from": benefit_from,
        "benefit_to": None if benefit_from is not None else None,
        "harm_from": harm_from,
        "harm_to": None if harm_from is not None else None,
    }


def analyze_binary(
    e1: int,
    n1: int,
    e0: int,
    n0: int,
    confidence: float = 0.95,
    beneficial: bool = True,
) -> dict[str, Any]:
    """Analyze event counts and return absolute and relative effects.

    ``risk_difference`` is always treatment risk minus comparator risk.  When
    ``beneficial`` is false, the clinical sign used for classification and
    NNT/NNH labeling is reversed because a higher event risk is undesirable.
    """

    e1, n1 = _validate_events_total(e1, n1, "e1", "n1")
    e0, n0 = _validate_events_total(e0, n0, "e0", "n0")
    confidence = _validate_confidence(confidence)
    if not isinstance(beneficial, bool):
        raise ValueError("beneficial must be a boolean")

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

    if signed_difference > 0.0:
        point_label = "NNT"
        point_unrounded = 1.0 / signed_difference
    elif signed_difference < 0.0:
        point_label = "NNH"
        point_unrounded = 1.0 / abs(signed_difference)
    else:
        point_label = None
        point_unrounded = None

    point_estimate = {
        "label": point_label,
        "unrounded": point_unrounded,
        "rounded": _ceil_positive(point_unrounded),
        "exploratory": classification == "inconclusive_crosses_zero",
    }
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
        "odds_ratio": _odds_ratio(e1, n1, e0, n0),
        "confidence": confidence,
        "beneficial_event": beneficial,
        "fisher_exact_p_two_sided": _fisher_exact_two_sided(e1, n1, e0, n0),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_treatment", type=int)
    parser.add_argument("total_treatment", type=int)
    parser.add_argument("events_control", type=int)
    parser.add_argument("total_control", type=int)
    parser.add_argument("--harm", action="store_true", help="treat the event as undesirable")
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


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
            beneficial=not args.harm,
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
            print(
                "Split reciprocal interval: "
                f"possible benefit NNT >= {split['benefit_from']}; "
                "no effect at infinity; "
                f"possible harm NNH >= {split['harm_from']}"
            )
        elif result["reciprocal_interval"] is not None:
            interval = result["reciprocal_interval"]
            print(
                f"Reciprocal {result['confidence']:.0%} CI: "
                f"[{interval['lower']:.6g}, {interval['upper']:.6g}]"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
