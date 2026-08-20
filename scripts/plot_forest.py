#!/usr/bin/env python3
"""Create a dependency-free SVG forest plot from an audited meta-analysis CSV."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Sequence

from reconstruct_meta_analysis import (
    CURRENT_PREDICTION_DF,
    PREDICTION_DF_CONVENTIONS,
    MetaAnalysisError,
    MetaRecord,
    filter_records,
    load_records,
    meta_analysis,
    record_row_key,
)


def _row_key(record: MetaRecord) -> object:
    """Return the stable key emitted with a fitted study weight.

    A forest plot is only valid when the rows and weights came from the same
    fitted dataset in the same order.  ``study_id`` is intentionally not a
    fallback: it is not unique for legitimate strata and cannot detect a
    changed row with the same label.
    """

    key = getattr(record, "row_key", None)
    if key is None:
        # MetaRecord remains a source-row dataclass; the fitted result carries
        # the stable key computed by the meta engine's shared helper.  A local
        # attribute is accepted for callers that materialize that contract on
        # records themselves, while the helper keeps normal loaded records
        # aligned with study_weights_percent.
        try:
            key = record_row_key(record)
        except (TypeError, ValueError, KeyError) as exc:
            raise MetaAnalysisError(
                "Cannot verify forest rows: no stable row_key is available"
            ) from exc
    if key is None or (isinstance(key, str) and not key.strip()):
        raise MetaAnalysisError(
            "Cannot verify forest rows: MetaRecord.row_key is missing; rerun meta_analysis "
            "with row-key support"
        )
    try:
        hash(key)
    except TypeError as exc:
        raise MetaAnalysisError("Cannot verify forest rows: row_key must be hashable") from exc
    return key


def _aligned_weights(records: Sequence[MetaRecord], result: dict) -> list[float]:
    """Validate row identity/order and return the corresponding fitted weights."""

    entries = result.get("study_weights_percent")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise MetaAnalysisError(
            "The fitted result has no study_weights_percent row-key contract; refusing to plot"
        )
    if len(entries) != len(records):
        raise MetaAnalysisError(
            "The plotted rows and the fitted study weights are not aligned; plot the same "
            "records that were passed to meta_analysis"
        )

    record_keys = [_row_key(record) for record in records]
    weight_keys: list[object] = []
    weights: list[float] = []
    for entry in entries:
        if not isinstance(entry, dict) or "row_key" not in entry:
            raise MetaAnalysisError(
                "Cannot verify forest rows: every study weight must include row_key"
            )
        key = entry["row_key"]
        if key is None or (isinstance(key, str) and not key.strip()):
            raise MetaAnalysisError("Cannot verify forest rows: study weight row_key is empty")
        try:
            hash(key)
        except TypeError as exc:
            raise MetaAnalysisError("Cannot verify forest rows: row_key must be hashable") from exc
        try:
            weight = float(entry["weight"])
        except (TypeError, ValueError) as exc:
            raise MetaAnalysisError("Study weights must be finite non-negative numbers") from exc
        if not math.isfinite(weight) or weight < 0.0:
            raise MetaAnalysisError("Study weights must be finite non-negative numbers")
        weight_keys.append(key)
        weights.append(weight)

    if len(set(record_keys)) != len(record_keys) or len(set(weight_keys)) != len(weight_keys):
        raise MetaAnalysisError("Cannot verify forest rows: row_key values must be unique")
    if record_keys != weight_keys:
        raise MetaAnalysisError(
            "The plotted dataset does not match the fitted study weights by row_key; "
            "refusing to plot reordered or changed rows"
        )
    if not weights or max(weights) <= 0.0:
        raise MetaAnalysisError("Study weights must contain at least one positive value")
    return weights


def write_forest_svg(
    records: Sequence[MetaRecord],
    result: dict,
    destination: str | Path,
    *,
    title: str = "Meta-analysis reconstruction",
) -> Path:
    if not records:
        raise MetaAnalysisError("Cannot plot an empty forest")
    is_ratio = result["scale"] == "log_ratio"
    interval_values = [result["ci_lower"], result["ci_upper"]]
    if result["prediction_lower"] is not None:
        interval_values.extend([result["prediction_lower"], result["prediction_upper"]])
    raw_min = min([record.lower for record in records] + interval_values)
    raw_max = max([record.upper for record in records] + interval_values)
    if is_ratio:
        axis_min, axis_max = math.log(raw_min), math.log(raw_max)
        null_value = 0.0
        convert = math.log
    else:
        axis_min, axis_max = raw_min, raw_max
        null_value = 0.0
        convert = lambda value: value
    source_levels = result.get("input_confidence_levels") or [result["input_confidence"]]
    source_label = (
        f"source {source_levels[0]:.0%} CI"
        if len(source_levels) == 1
        else "mixed source CI levels: "
        + ", ".join(f"{level:.0%}" for level in source_levels)
    )
    padding = max((axis_max - axis_min) * 0.06, 1e-9)
    axis_min -= padding
    axis_max += padding
    width = 980
    left = 330
    right = 830
    row_height = 30
    header = 90
    footer = 110 + 18 * min(len(result["warnings"]), 4)
    height = header + row_height * (len(records) + 2) + footer

    def x_position(value: float) -> float:
        transformed = convert(value)
        return left + (transformed - axis_min) / (axis_max - axis_min) * (right - left)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="24" y="34" font-family="sans-serif" font-size="22" font-weight="bold">{html.escape(title)}</text>',
        '<text x="24" y="66" font-family="sans-serif" font-size="13">Study</text>',
        f'<text x="{right + 20}" y="66" font-family="sans-serif" font-size="13">Effect ({html.escape(source_label)})</text>',
    ]
    # Omit the null line when the null value falls outside the plotted range; an
    # unclamped line lands on top of the numeric text column and misleads.
    if axis_min <= null_value <= axis_max:
        null_x = left + (null_value - axis_min) / (axis_max - axis_min) * (right - left)
        lines.append(
            f'<line x1="{null_x:.2f}" y1="{header - 12}" x2="{null_x:.2f}" y2="{height - footer + 5}" stroke="#777" stroke-dasharray="4 4"/>'
        )
    weights = _aligned_weights(records, result)
    largest_weight = max(weights)
    for index, record in enumerate(records):
        y = header + index * row_height
        low_x, high_x, point_x = x_position(record.lower), x_position(record.upper), x_position(record.effect)
        label = record.citation + (f" ({record.sex})" if record.sex and record.sex != "all" else "")
        # Marker *area* is proportional to the fitted weight.  The side is
        # therefore proportional to sqrt(weight), with no additive baseline.
        # Keep enough decimal precision in the SVG attributes that serialization
        # does not materially disturb the proportionality.
        square_side = 14.0 * math.sqrt(weights[index] / largest_weight)
        lines.extend(
            [
                f'<text x="24" y="{y + 5}" font-family="sans-serif" font-size="12">{html.escape(label)}</text>',
                f'<line x1="{low_x:.2f}" y1="{y}" x2="{high_x:.2f}" y2="{y}" stroke="#222" stroke-width="1.5"/>',
                f'<line x1="{low_x:.2f}" y1="{y - 4}" x2="{low_x:.2f}" y2="{y + 4}" stroke="#222"/>',
                f'<line x1="{high_x:.2f}" y1="{y - 4}" x2="{high_x:.2f}" y2="{y + 4}" stroke="#222"/>',
                f'<rect x="{point_x - square_side / 2:.10f}" y="{y - square_side / 2:.10f}" width="{square_side:.10f}" height="{square_side:.10f}" fill="#2457a7"/>',
                f'<text x="{right + 20}" y="{y + 5}" font-family="monospace" font-size="12">{record.effect:.3f} ({record.lower:.3f}, {record.upper:.3f})</text>',
            ]
        )
    pooled_y = header + len(records) * row_height + 12
    center_x = x_position(result["pooled"])
    lower_x = x_position(result["ci_lower"])
    upper_x = x_position(result["ci_upper"])
    diamond = f"{lower_x:.2f},{pooled_y} {center_x:.2f},{pooled_y - 8} {upper_x:.2f},{pooled_y} {center_x:.2f},{pooled_y + 8}"
    lines.extend(
        [
            f'<text x="24" y="{pooled_y + 5}" font-family="sans-serif" font-size="13" font-weight="bold">Pooled ({html.escape(result["tau2_method"])})</text>',
            f'<polygon points="{diamond}" fill="#b52626"/>',
            f'<text x="{right + 20}" y="{pooled_y + 5}" font-family="monospace" font-size="12" font-weight="bold">{result["pooled"]:.3f} ({result["ci_lower"]:.3f}, {result["ci_upper"]:.3f}) [{result["confidence"]:.0%} CI]</text>',
            f'<line x1="{left}" y1="{height - footer + 25}" x2="{right}" y2="{height - footer + 25}" stroke="#111"/>',
        ]
    )
    for index in range(5):
        tick_transformed = axis_min + index * (axis_max - axis_min) / 4.0
        tick_value = math.exp(tick_transformed) if is_ratio else tick_transformed
        tick_x = left + index * (right - left) / 4.0
        axis_y = height - footer + 25
        lines.extend(
            [
                f'<line x1="{tick_x:.2f}" y1="{axis_y}" x2="{tick_x:.2f}" y2="{axis_y + 6}" stroke="#111"/>',
                f'<text x="{tick_x:.2f}" y="{axis_y + 21}" text-anchor="middle" font-family="sans-serif" font-size="10">{tick_value:.3g}</text>',
            ]
        )
    if result["prediction_lower"] is not None:
        prediction_text = (
            f"; prediction interval {result['prediction_lower']:.3f} to "
            f"{result['prediction_upper']:.3f}"
        )
    else:
        prediction_reason = result.get("prediction_not_estimable_reason") or "not estimable"
        prediction_text = f"; prediction interval not estimable: {html.escape(str(prediction_reason))}"
    lines.append(
        f'<text x="24" y="{height - footer + 65}" font-family="sans-serif" font-size="11">Q={result["Q"]:.3f}; tau²={result["tau2"]:.5f}; I²={result["I2_percent"]:.1f}%{prediction_text}</text>'
    )
    for index, warning in enumerate(result["warnings"][:4]):
        lines.append(
            f'<text x="24" y="{height - footer + 84 + index * 16}" font-family="sans-serif" font-size="10" fill="#9b1c1c">WARNING: {html.escape(warning)}</text>'
        )
    lines.append('</svg>')
    output = Path(destination)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--analysis-id")
    parser.add_argument("--tau2", choices=("DL", "PM", "REML"), default="DL")
    parser.add_argument("--inference", choices=("normal", "HKSJ"), default="normal")
    parser.add_argument("--common-measure")
    parser.add_argument("--model", choices=("fixed", "random"), default="random")
    parser.add_argument("--input-confidence", type=float, default=0.95)
    parser.add_argument(
        "--prediction-df",
        choices=PREDICTION_DF_CONVENTIONS,
        default=CURRENT_PREDICTION_DF,
    )
    parser.add_argument("--allow-mixed-estimands", action="store_true")
    parser.add_argument("--allow-dependence", action="store_true")
    parser.add_argument("--title", default="Meta-analysis reconstruction")
    args = parser.parse_args(argv)
    try:
        records = filter_records(
            load_records(args.dataset),
            analysis_id=args.analysis_id,
            common_measure=args.common_measure,
        )
        result = meta_analysis(
            records,
            model=args.model,
            tau2_method=args.tau2,
            inference=args.inference,
            input_confidence=args.input_confidence,
            prediction_df=args.prediction_df,
            allow_mixed_estimands=args.allow_mixed_estimands,
            allow_dependence=args.allow_dependence,
        )
        output = write_forest_svg(records, result, args.destination, title=args.title)
    except (MetaAnalysisError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    print(
        json.dumps(
            {
                "forest_file": str(output),
                "pooled": result["pooled"],
                "measures": result["measures"],
                "warnings": result["warnings"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
