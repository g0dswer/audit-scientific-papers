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
    dependency_state_issues,
    load_records,
)


def validate_records(records: Sequence[MetaRecord]) -> dict:
    records = list(records)
    included_records = [record for record in records if record.include_published]
    issues: list[dict] = []

    def add_issue(
        *,
        scope: str,
        severity: str,
        code: str,
        analysis_id: str | None,
        study_id: str | None,
        message: str,
    ) -> None:
        issues.append(
            {
                "scope": scope,
                "severity": severity,
                "code": code,
                "analysis_id": analysis_id,
                "study_id": study_id,
                "message": message,
            }
        )

    def check_rows(rows: Sequence[MetaRecord], scope: str, *, empty_pool_is_error: bool = False) -> None:
        measures_by_analysis: dict[str, set[str]] = defaultdict(set)
        study_keys: Counter[tuple[str, str]] = Counter()
        cohorts_by_analysis: dict[str, Counter[str]] = defaultdict(Counter)
        rows_by_analysis_cohort: dict[tuple[str, str], list[MetaRecord]] = defaultdict(list)

        if empty_pool_is_error and not rows:
            add_issue(
                scope=scope,
                severity="error",
                code="EMPTY_INCLUDED_POOL",
                analysis_id=None,
                study_id=None,
                message="No rows are marked include_published=true; a default pool cannot be fitted.",
            )
        for record in rows:
            measures_by_analysis[record.analysis_id].add(record.measure)
            study_keys[(record.analysis_id, record.study_id)] += 1
            cohorts_by_analysis[record.analysis_id][record.cohort_id] += 1
            rows_by_analysis_cohort[(record.analysis_id, record.cohort_id)].append(record)
            if record.overlap_status not in VALID_OVERLAP_STATUSES:
                add_issue(
                    scope=scope,
                    severity="error",
                    code="INVALID_OVERLAP_STATUS",
                    analysis_id=record.analysis_id,
                    study_id=record.study_id,
                    message=f"Unknown overlap status {record.overlap_status!r}.",
                )
            for dependency_issue in dependency_state_issues(record):
                add_issue(
                    scope=scope,
                    severity="error",
                    code=dependency_issue["code"],
                    analysis_id=record.analysis_id,
                    study_id=record.study_id,
                    message=dependency_issue["message"],
                )
            if record.outcome_provenance == "DERIVED_INVALID_OR_UNJUSTIFIED":
                add_issue(
                    scope=scope,
                    severity="error",
                    code="INVALID_OR_UNJUSTIFIED_OUTCOME",
                    analysis_id=record.analysis_id,
                    study_id=record.study_id,
                    message="The pooled outcome is not justified by the original study outcome.",
                )
            elif record.outcome_provenance in {"DERIVED_ASSUMPTION_DEPENDENT", "UNKNOWN"}:
                add_issue(
                    scope=scope,
                    severity="warning",
                    code="UNCERTAIN_OUTCOME_PROVENANCE",
                    analysis_id=record.analysis_id,
                    study_id=record.study_id,
                    message=f"Outcome provenance is {record.outcome_provenance}.",
                )
            if record.exposure_provenance in {
                "DERIVED_ASSUMPTION_DEPENDENT",
                "DERIVED_INVALID_OR_UNJUSTIFIED",
                "UNKNOWN",
            }:
                add_issue(
                    scope=scope,
                    severity="warning",
                    code="UNCERTAIN_EXPOSURE_PROVENANCE",
                    analysis_id=record.analysis_id,
                    study_id=record.study_id,
                    message=f"Exposure provenance is {record.exposure_provenance}.",
                )
            if record.participant_overlap_possible and record.overlap_status in UNRESOLVED_OVERLAP_STATUSES:
                add_issue(
                    scope=scope,
                    severity="error",
                    code="UNRESOLVED_DEPENDENCE",
                    analysis_id=record.analysis_id,
                    study_id=record.study_id,
                    message="Possible participant overlap has not been resolved.",
                )
            if "conflict" in record.notes.lower() or "discrep" in record.notes.lower():
                add_issue(
                    scope=scope,
                    severity="warning",
                    code="SOURCE_CONFLICT_NOTE",
                    analysis_id=record.analysis_id,
                    study_id=record.study_id,
                    message=record.notes,
                )

        for analysis_id, measures in measures_by_analysis.items():
            if len(measures) > 1:
                add_issue(
                    scope=scope,
                    severity="error",
                    code="MIXED_EFFECT_MEASURES",
                    analysis_id=analysis_id,
                    study_id=None,
                    message=(
                        f"Effect measures {', '.join(sorted(measures))} are mixed. "
                        "Random effects does not harmonize estimands."
                    ),
                )
        for (analysis_id, study_id), count in study_keys.items():
            if count > 1:
                add_issue(
                    scope=scope,
                    severity="warning",
                    code="DUPLICATE_STUDY_ID",
                    analysis_id=analysis_id,
                    study_id=study_id,
                    message=f"The study identifier occurs {count} times; verify sex/arm/timepoint dependence.",
                )
        for analysis_id, cohort_counts in cohorts_by_analysis.items():
            for cohort_id, count in cohort_counts.items():
                if count > 1:
                    rows_for_cohort = rows_by_analysis_cohort[(analysis_id, cohort_id)]
                    resolved = all(row.overlap_status == "resolved_independent" for row in rows_for_cohort)
                    add_issue(
                        scope=scope,
                        severity="warning" if resolved else "error",
                        code="MULTIPLE_ROWS_RESOLVED_INDEPENDENT" if resolved else "UNRESOLVED_REPEATED_COHORT",
                        analysis_id=analysis_id,
                        study_id=None,
                        message=(
                            f"Cohort {cohort_id} contributes {count} rows with verified disjoint samples."
                            if resolved
                            else f"Cohort {cohort_id} contributes {count} rows without explicit resolved_independent status."
                        ),
                    )

    # Inventory integrity includes every extracted row, including deliberately
    # excluded provenance/duplicate rows.  Pool validity is evaluated separately
    # on include_published=true rows only.
    check_rows(records, "inventory")
    check_rows(included_records, "included_pool", empty_pool_is_error=True)

    inventory_errors = sum(issue["scope"] == "inventory" and issue["severity"] == "error" for issue in issues)
    inventory_warnings = sum(issue["scope"] == "inventory" and issue["severity"] == "warning" for issue in issues)
    pool_errors = sum(issue["scope"] == "included_pool" and issue["severity"] == "error" for issue in issues)
    pool_warnings = sum(issue["scope"] == "included_pool" and issue["severity"] == "warning" for issue in issues)
    error_count = inventory_errors + pool_errors
    warning_count = inventory_warnings + pool_warnings
    return {
        "records": len(records),
        "included_records": len(included_records),
        "excluded_records": len(records) - len(included_records),
        "analyses": sorted({record.analysis_id for record in records}),
        "valid_for_inventory_integrity": inventory_errors == 0,
        "inventory_integrity_valid": inventory_errors == 0,
        "valid_for_included_pool": bool(included_records) and pool_errors == 0,
        "included_pool_valid": bool(included_records) and pool_errors == 0,
        # Backward-compatible name: it now correctly refers only to the
        # selected included pool, not to excluded inventory rows.
        "valid_for_defensible_default_pooling": bool(included_records) and pool_errors == 0,
        "inventory_error_count": inventory_errors,
        "inventory_warning_count": inventory_warnings,
        "included_pool_error_count": pool_errors,
        "included_pool_warning_count": pool_warnings,
        "inventory": {
            "records": len(records),
            "valid": inventory_errors == 0,
            "error_count": inventory_errors,
            "warning_count": inventory_warnings,
        },
        "included_pool": {
            "records": len(included_records),
            "valid": bool(included_records) and pool_errors == 0,
            "error_count": pool_errors,
            "warning_count": pool_warnings,
        },
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
