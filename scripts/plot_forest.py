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
    PREDICTION_DF_CONVENTIONS,
    MetaAnalysisError,
    MetaRecord,
    filter_records,
    load_records,
    meta_analysis,
)


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
    # Weights are matched to rows positionally: study_weights_percent is built by
    # zipping over this same records sequence, and study_id is not unique within a
    # pool (sex, arm, and timepoint strata legitimately repeat it).
    weights = [item["weight"] for item in result["study_weights_percent"]]
    if len(weights) != len(records):
        raise MetaAnalysisError(
            "The plotted rows and the fitted study weights are not aligned; plot the same "
            "records that were passed to meta_analysis"
        )
    largest_weight = max(weights)
    for index, record in enumerate(records):
        y = header + index * row_height
        low_x, high_x, point_x = x_position(record.lower), x_position(record.upper), x_position(record.effect)
        label = record.citation + (f" ({record.sex})" if record.sex and record.sex != "all" else "")
        square_side = 4.0 + 10.0 * math.sqrt(weights[index] / largest_weight)
        lines.extend(
            [
                f'<text x="24" y="{y + 5}" font-family="sans-serif" font-size="12">{html.escape(label)}</text>',
                f'<line x1="{low_x:.2f}" y1="{y}" x2="{high_x:.2f}" y2="{y}" stroke="#222" stroke-width="1.5"/>',
                f'<line x1="{low_x:.2f}" y1="{y - 4}" x2="{low_x:.2f}" y2="{y + 4}" stroke="#222"/>',
                f'<line x1="{high_x:.2f}" y1="{y - 4}" x2="{high_x:.2f}" y2="{y + 4}" stroke="#222"/>',
                f'<rect x="{point_x - square_side / 2:.2f}" y="{y - square_side / 2:.2f}" width="{square_side:.2f}" height="{square_side:.2f}" fill="#2457a7"/>',
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
    prediction_text = (
        f"; prediction interval {result['prediction_lower']:.3f} to {result['prediction_upper']:.3f}"
        if result["prediction_lower"] is not None
        else "; prediction interval not applicable to fixed-effect model"
    )
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
    parser.add_argument("--prediction-df", choices=PREDICTION_DF_CONVENTIONS, default="k-2")
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
