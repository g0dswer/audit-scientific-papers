#!/usr/bin/env python3
"""Compare tau-squared estimators and inference methods for one audited pool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from reconstruct_meta_analysis import filter_records, load_records, meta_analysis


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--analysis-id")
    parser.add_argument("--common-measure")
    parser.add_argument("--direct-outcomes-only", action="store_true")
    parser.add_argument("--direct-exposures-only", action="store_true")
    parser.add_argument("--allow-mixed-estimands", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    records = filter_records(
        load_records(args.dataset),
        analysis_id=args.analysis_id,
        common_measure=args.common_measure,
        direct_outcomes_only=args.direct_outcomes_only,
        direct_exposures_only=args.direct_exposures_only,
    )
    output = []
    for method in ("DL", "PM", "REML"):
        for inference in ("normal", "HKSJ"):
            result = meta_analysis(
                records,
                tau2_method=method,
                inference=inference,
                allow_mixed_estimands=args.allow_mixed_estimands,
            )
            output.append(
                {
                    "tau2_method": method,
                    "inference": inference,
                    "pooled": result["pooled"],
                    "ci_lower": result["ci_lower"],
                    "ci_upper": result["ci_upper"],
                    "prediction_lower": result["prediction_lower"],
                    "prediction_upper": result["prediction_upper"],
                    "tau2": result["tau2"],
                    "I2_percent": result["I2_percent"],
                    "measures": result["measures"],
                    "warnings": result["warnings"],
                }
            )
    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        print("tau2\tinference\tpooled\tci\tprediction interval\tI2%")
        for row in output:
            print(
                f"{row['tau2_method']}\t{row['inference']}\t{row['pooled']:.6g}\t"
                f"{row['ci_lower']:.6g} to {row['ci_upper']:.6g}\t"
                f"{row['prediction_lower']:.6g} to {row['prediction_upper']:.6g}\t"
                f"{row['I2_percent']:.2f}"
            )
            for warning in row["warnings"]:
                print(f"  WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
