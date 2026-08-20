#!/usr/bin/env python3
"""Validate row provenance, effect compatibility, and dependence flags."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Sequence

from reconstruct_meta_analysis import (
    UNRESOLVED_OVERLAP_STATUSES,
    VALID_OVERLAP_STATUSES,
    MetaAnalysisError,
    MetaRecord,
    load_records,
)


def validate_records(records: Sequence[MetaRecord]) -> dict:
    issues: list[dict] = []
    measures_by_analysis: dict[str, set[str]] = defaultdict(set)
    study_keys: Counter[tuple[str, str]] = Counter()
    cohorts_by_analysis: dict[str, Counter[str]] = defaultdict(Counter)
    rows_by_analysis_cohort: dict[tuple[str, str], list[MetaRecord]] = defaultdict(list)

    for record in records:
        measures_by_analysis[record.analysis_id].add(record.measure)
        study_keys[(record.analysis_id, record.study_id)] += 1
        cohorts_by_analysis[record.analysis_id][record.cohort_id] += 1
        rows_by_analysis_cohort[(record.analysis_id, record.cohort_id)].append(record)
        # The vocabulary is owned by the engine, which now rejects unknown values at
        # load time; this check still runs for records built programmatically.
        if record.overlap_status not in VALID_OVERLAP_STATUSES:
            issues.append(
                {
                    "severity": "error",
                    "code": "INVALID_OVERLAP_STATUS",
                    "analysis_id": record.analysis_id,
                    "study_id": record.study_id,
                    "message": f"Unknown overlap status {record.overlap_status!r}.",
                }
            )
        if record.overlap_status == "modeled":
            issues.append(
                {
                    "severity": "error",
                    "code": "DEPENDENCE_MODEL_NOT_SUPPORTED",
                    "analysis_id": record.analysis_id,
                    "study_id": record.study_id,
                    "message": "The included univariate engine does not accept modeled dependence without a covariance-aware external model.",
                }
            )
        if record.overlap_status == "resolved_duplicate_removed" and record.include_published:
            issues.append(
                {
                    "severity": "error",
                    "code": "REMOVED_DUPLICATE_STILL_INCLUDED",
                    "analysis_id": record.analysis_id,
                    "study_id": record.study_id,
                    "message": "A row marked as a removed duplicate cannot remain included.",
                }
            )
        if record.outcome_provenance == "DERIVED_INVALID_OR_UNJUSTIFIED":
            issues.append(
                {
                    "severity": "error",
                    "code": "INVALID_OR_UNJUSTIFIED_OUTCOME",
                    "analysis_id": record.analysis_id,
                    "study_id": record.study_id,
                    "message": "The pooled outcome is not justified by the original study outcome.",
                }
            )
        elif record.outcome_provenance in {"DERIVED_ASSUMPTION_DEPENDENT", "UNKNOWN"}:
            issues.append(
                {
                    "severity": "warning",
                    "code": "UNCERTAIN_OUTCOME_PROVENANCE",
                    "analysis_id": record.analysis_id,
                    "study_id": record.study_id,
                    "message": f"Outcome provenance is {record.outcome_provenance}.",
                }
            )
        if record.exposure_provenance in {
            "DERIVED_ASSUMPTION_DEPENDENT",
            "DERIVED_INVALID_OR_UNJUSTIFIED",
            "UNKNOWN",
        }:
            issues.append(
                {
                    "severity": "warning",
                    "code": "UNCERTAIN_EXPOSURE_PROVENANCE",
                    "analysis_id": record.analysis_id,
                    "study_id": record.study_id,
                    "message": f"Exposure provenance is {record.exposure_provenance}.",
                }
            )
        if record.participant_overlap_possible and record.overlap_status in UNRESOLVED_OVERLAP_STATUSES:
            issues.append(
                {
                    "severity": "error",
                    "code": "UNRESOLVED_DEPENDENCE",
                    "analysis_id": record.analysis_id,
                    "study_id": record.study_id,
                    "message": "Possible participant overlap has not been resolved.",
                }
            )
        if "conflict" in record.notes.lower() or "discrep" in record.notes.lower():
            issues.append(
                {
                    "severity": "warning",
                    "code": "SOURCE_CONFLICT_NOTE",
                    "analysis_id": record.analysis_id,
                    "study_id": record.study_id,
                    "message": record.notes,
                }
            )

    for analysis_id, measures in measures_by_analysis.items():
        if len(measures) > 1:
            issues.append(
                {
                    "severity": "error",
                    "code": "MIXED_EFFECT_MEASURES",
                    "analysis_id": analysis_id,
                    "study_id": None,
                    "message": (
                        f"Effect measures {', '.join(sorted(measures))} are mixed. "
                        "Random effects does not harmonize estimands."
                    ),
                }
            )
    for (analysis_id, study_id), count in study_keys.items():
        if count > 1:
            issues.append(
                {
                    "severity": "warning",
                    "code": "DUPLICATE_STUDY_ID",
                    "analysis_id": analysis_id,
                    "study_id": study_id,
                    "message": f"The study identifier occurs {count} times; verify sex/arm/timepoint dependence.",
                }
            )
    for analysis_id, cohort_counts in cohorts_by_analysis.items():
        for cohort_id, count in cohort_counts.items():
            if count > 1:
                rows = rows_by_analysis_cohort[(analysis_id, cohort_id)]
                resolved = all(row.overlap_status == "resolved_independent" for row in rows)
                issues.append(
                    {
                        "severity": "warning" if resolved else "error",
                        "code": "MULTIPLE_ROWS_RESOLVED_INDEPENDENT" if resolved else "UNRESOLVED_REPEATED_COHORT",
                        "analysis_id": analysis_id,
                        "study_id": None,
                        "message": (
                            f"Cohort {cohort_id} contributes {count} rows with verified disjoint samples."
                            if resolved
                            else f"Cohort {cohort_id} contributes {count} rows without explicit resolved_independent status."
                        ),
                    }
                )

    error_count = sum(issue["severity"] == "error" for issue in issues)
    warning_count = sum(issue["severity"] == "warning" for issue in issues)
    return {
        "records": len(records),
        "analyses": sorted(measures_by_analysis),
        "valid_for_defensible_default_pooling": error_count == 0,
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issues,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = validate_records(load_records(args.dataset))
    except (MetaAnalysisError, OSError) as exc:
        raise SystemExit(f"error: {exc}") from exc
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"Records: {report['records']}; errors: {report['error_count']}; "
            f"warnings: {report['warning_count']}"
        )
        for issue in report["issues"]:
            print(f"[{issue['severity'].upper()}] {issue['code']}: {issue['message']}")
    return 0 if report["error_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
