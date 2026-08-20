#!/usr/bin/env python3
"""Compare tau-squared estimators and inference methods for one audited pool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from reconstruct_meta_analysis import (
    CURRENT_PREDICTION_DF,
    PREDICTION_DF_CONVENTIONS,
    MetaAnalysisError,
    filter_records,
    load_records,
    meta_analysis,
)


def _format_interval(lower: float | None, upper: float | None) -> str:
    if lower is None or upper is None:
        return "not estimable"
    return f"{lower:.6g} to {upper:.6g}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--analysis-id")
    parser.add_argument("--common-measure")
    parser.add_argument("--direct-outcomes-only", action="store_true")
    parser.add_argument("--direct-exposures-only", action="store_true")
    parser.add_argument("--input-confidence", type=float, default=0.95)
    parser.add_argument(
        "--prediction-df",
        choices=PREDICTION_DF_CONVENTIONS,
        default=CURRENT_PREDICTION_DF,
    )
    parser.add_argument("--allow-mixed-estimands", action="store_true")
    parser.add_argument("--allow-dependence", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    output = []
    try:
        records = filter_records(
            load_records(args.dataset),
            analysis_id=args.analysis_id,
            common_measure=args.common_measure,
            direct_outcomes_only=args.direct_outcomes_only,
            direct_exposures_only=args.direct_exposures_only,
        )
        for method in ("DL", "PM", "REML"):
            for inference in ("normal", "HKSJ"):
                result = meta_analysis(
                    records,
                    tau2_method=method,
                    inference=inference,
                    input_confidence=args.input_confidence,
                    prediction_df=args.prediction_df,
                    allow_mixed_estimands=args.allow_mixed_estimands,
                    allow_dependence=args.allow_dependence,
                )
                output.append(
                    {
                        "model": result["model"],
                        "tau2_method": method,
                        "inference": inference,
                        "pooled": result["pooled"],
                        "ci_lower": result["ci_lower"],
                        "ci_upper": result["ci_upper"],
                        "prediction_df_convention": result["prediction_df_convention"],
                        "prediction_interval_df": result["prediction_interval_df"],
                        "prediction_multiplier_distribution": result[
                            "prediction_multiplier_distribution"
                        ],
                        "prediction_interval_method": result["prediction_interval_method"],
                        "prediction_lower": result["prediction_lower"],
                        "prediction_upper": result["prediction_upper"],
                        "tau2": result["tau2"],
                        "I2_percent": result["I2_percent"],
                        "I2_method": result["I2_method"],
                        "measures": result["measures"],
                        "warnings": result["warnings"],
                    }
                )
    except (MetaAnalysisError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print("model\ttau2\tinference\tpooled\tci\tprediction interval\tI2%\tI2 method")
        for row in output:
            print(
                f"{row['model']}\t{row['tau2_method']}\t{row['inference']}\t{row['pooled']:.6g}\t"
                f"{row['ci_lower']:.6g} to {row['ci_upper']:.6g}\t"
                f"{_format_interval(row['prediction_lower'], row['prediction_upper'])}\t"
                f"{row['I2_percent']:.2f}\t{row['I2_method']}"
            )
            for warning in row["warnings"]:
                print(f"  WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
