# Meta-analysis Extraction and Provenance

## Extraction hierarchy

Prefer, in order:

1. structured supplementary CSV, spreadsheet, or analysis dataset;
2. executable code plus the exact input file;
3. HTML or PDF table with printed values;
4. forest plot with printed estimates and confidence intervals;
5. graphical digitization only as a last resort.

Cross-check structured data against the displayed forest plot and pooled row. Mark values
transcribed from a figure as `forest_plot` and values obtained by graphical digitization as
`digitized_from_figure`. Never represent a digitized value as an exact source value.

## Required CSV contract

Use one row per displayed estimate. The deterministic scripts require these columns:

```text
analysis_id,study_id,citation,cohort_id,effect,lower,upper,measure,
outcome_provenance,exposure_provenance
```

The full recommended schema is:

```text
analysis_id,study_id,citation,cohort_id,effect,lower,upper,measure,
exposure,outcome_reported_originally,outcome_used_in_meta_analysis,
outcome_provenance,exposure_provenance,sex,source_location,source_type,
source_url,participant_overlap_possible,overlap_status,include_published,notes
```

`input_confidence` is an optional per-row column, read by the scripts, giving the
confidence level of that row's printed interval as a decimal (`0.95`, `0.90`). Leave it
blank to inherit the global `--input-confidence`, which itself defaults to 0.95. Set it
whenever a forest plot mixes interval levels: the standard error is inverted from the
printed bounds, so using 1.96 for a printed 90% interval instead of its 90% critical value
makes the reconstructed standard error 16.1% too low, the variance 29.6% too low, and the
inverse-variance weight 42% too high. This silently misweights the row. Every output lists
the levels it actually used in `input_confidence_levels`; check that list against the source
figure.

Add other review-specific fields when material: follow-up, events, sample size, dose
contrast, reference category, adjusted_age, adjusted_sex, adjusted_smoking, adjusted_bmi,
adjusted_energy, adjusted_physical_activity, adjusted_alcohol, adjusted_socioeconomic,
risk_of_bias, population_applicability, clinical_heterogeneity, and extraction_verifier.
Fields outside the schema above are carried for the human record and are not read by the
scripts. Keep endpoint provenance separate from whether a disease-specific population is
applicable to the review's target population.

## Provenance vocabulary

Assign outcome and exposure provenance independently:

| Value | Meaning |
| --- | --- |
| `DIRECT` | Original report estimates the pooled definition directly |
| `DERIVED_VALID` | Derivation is identified and mathematically valid for the target estimand |
| `DERIVED_ASSUMPTION_DEPENDENT` | Derivation may be usable only under stated, contestable assumptions |
| `DERIVED_INVALID_OR_UNJUSTIFIED` | Derivation does not identify the claimed estimand or lacks justification |
| `UNKNOWN` | Source trail is insufficient |

Examples of red flags include relabeling cause-specific mortality as all-cause mortality,
combining separate exposure associations as if they estimated the association of their
sum, or converting an odds ratio to a risk ratio without the required baseline risk.

For every non-direct row, record the formula, inputs, source, assumptions, and who performed
the derivation. A weighted average of two cause-specific ratios does not reconstruct an
all-cause ratio. Combining coefficients for components does not generally estimate the
coefficient for their total without their joint model and covariance.

## Effect and interval checks

Record the effect measure exactly as reported: `HR`, `RR`, `OR`, `IRR`, `MD`, or `SMD`.
This column is load-bearing beyond the pooling engine: the single-study checker takes the
same vocabulary through `verify_continuous_result.py ci ... --measure`, and derives the
analysis scale from it. A wrong `measure` therefore corrupts both the pool and every
single-study reconstruction built from that row.
For a ratio estimate with a printed two-sided 95% interval, the scripts reconstruct:

```text
y = log(effect)
SE = [log(upper) - log(lower)] / (2 * 1.96)
variance = SE^2
```

The divisor is the normal quantile for that row's interval level. For a printed 95%
interval the scripts use the conventional 1.96 rather than 1.959964, because that is the
value the published interval was almost certainly rounded with; for any other level, and
for a row carrying its own `input_confidence`, the exact normal quantile is used.

This is an aggregate-data reconstruction from rounded bounds. It is not the original
model standard error. Preserve extra digits when supplied; do not infer them from a plot.

## Duplicate cohorts and dependence

Create a stable `cohort_id` based on cohort name, recruitment period, centers, and source
population—not just publication author/year. Search for companion reports and follow-up
updates. Record possible overlap and its resolution:

- `none`: no plausible overlap identified;
- `resolved_independent`: distinct participant sets verified;
- `resolved_duplicate_removed`: duplicate or overlapping row excluded;
- `modeled`: dependence represented in a valid covariance/multilevel model;
- `unresolved`: overlap remains plausible;
- `possible`: overlap is suspected but not yet investigated;
- `unknown`: the source trail does not say either way.

This vocabulary is closed. The loader rejects any other value with a row-numbered error
rather than accepting it, because an unrecognized status used to slip past the dependence
guard silently: a row flagged `participant_overlap_possible` with a mistyped status was
pooled as though the overlap had been resolved. Treat a typo as a blocking error, not a
formatting preference.

`none` is an assertion that you looked and found no plausible overlap. If you have not
looked, the honest value is `unknown` or `possible`, both of which block default pooling
when `participant_overlap_possible` is true.

`overlap_status` is the canonical state; the Boolean is retained for compatibility and
must agree with it. Thus `none` requires `participant_overlap_possible=false`, unresolved
states require `true`, and a row marked `resolved_duplicate_removed` cannot remain included.
The aggregate engine also rejects `modeled`: that state describes work done in a separate
covariance- or multilevel-aware analysis whose uncertainty cannot be reconstructed by this
univariate inverse-variance engine.

Multiple rows from one cohort may be valid strata, but they are not automatically
independent. Leave-one-out diagnostics should delete the cohort cluster, not just one row.

## Dual verification

For headline pools, use a second independent extractor or verifier when available. Compare
study ID, effect, interval, measure, outcome, exposure, cohort, and inclusion flag. Resolve
differences against the primary source rather than averaging transcriptions. Preserve a
note when sources conflict.

The Naghshi 2020 fixture in `tests/fixtures/` is a regression fixture, not a universal
template for substantive exclusions. Its two clean plant targets deliberately retain an
approximate tolerance because the proposed targets and the versioned provenance rule do
not produce identical exact pools. Never change row eligibility merely to satisfy a target.
