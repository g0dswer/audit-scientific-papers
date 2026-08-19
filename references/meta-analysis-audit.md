# Meta-analysis Audit

## Purpose

Use this workflow for systematic reviews with quantitative synthesis and for papers that
reuse published study-level estimates. Audit the review question, search, selection,
row-level data, estimands, dependence, model, and conclusion. Journal prestige and a
random-effects label do not resolve incompatible data.

## 1. Build the review evidence record

Retrieve and date, when available:

- article, correction, supplement, appendices, and every forest plot;
- review protocol and registration, including PROSPERO, Cochrane, Open Science Framework,
  journal protocol, or another field-specific registry;
- complete database search strategies, last-search date, deduplication method, screening
  flow, exclusion list, and automation tools;
- data-extraction forms, risk-of-bias judgments, certainty assessment, code, and datasets;
- each original contributing report needed to verify a headline pooled row;
- prior or companion reviews and duplicate publications that may share cohorts.

Search registry identifiers, title fragments, author names, population, intervention or
exposure, outcome, and funder. Compare dated protocol/registration versions with the final
review. A current record alone does not establish prospective methods.

Audit whether the search covered appropriate databases, trial registries, preprints,
grey literature, non-English sources, citation chasing, and updates. Re-run a targeted
search around the last-search date to look for obviously eligible omitted studies. Do not
claim a complete search merely because the paper calls it comprehensive.

## 2. Define the meta-analytic estimand

For every headline pool, record:

| Field | Required definition |
| --- | --- |
| Population | Eligibility, setting, design, and unit of independence |
| Intervention/exposure | Dose, contrast, category, increment, or transformation |
| Comparator | Reference group or counterfactual |
| Outcome | Exact definition, cause, instrument, and whether composite |
| Time | Follow-up horizon and handling of varying durations |
| Effect measure | Hazard ratio, risk ratio, odds ratio, incidence-rate ratio, mean difference, or standardized mean difference |
| Model | Fixed effect or random effects |
| Heterogeneity | Estimator for between-study variance and reported diagnostics |
| Inference | Normal/Wald, Hartung–Knapp–Sidik–Jonkman, or another method |
| Independent unit | Study, cohort, participant set, arm, sex stratum, or report |

Ask whether every pooled row estimates a sufficiently common quantity. A broad clinical
label is not enough; endpoint definition, follow-up, population, contrast, and adjustment
must also be compatible.

## 3. Reconstruct the published result first

Extract all rows in the published headline forest plot, including the printed estimate,
confidence interval, effect measure, subgroup, and source location. Read
[meta-analysis-extraction.md](meta-analysis-extraction.md) and validate the dataset:

```bash
python3 scripts/validate_meta_dataset.py meta_data.csv --json
```

Then reproduce the article before changing exclusions or methods:

```bash
python3 scripts/reconstruct_meta_analysis.py meta_data.csv \
  --analysis-id HEADLINE_POOL \
  --tau2 DL \
  --allow-mixed-estimands \
  --expected-pooled PUBLISHED_VALUE \
  --json
```

`--allow-mixed-estimands` is permitted only to reconstruct a publication that actually
mixed effect measures. It emits a warning and never validates that choice. Record the
article value, reconstructed value, absolute difference, heterogeneity, and status.

If reproduction fails, stop interpreting sensitivity analyses until likely causes have
been checked: transcription, rounding, confidence level, effect scale, standard-error
derivation, weights, estimator, duplicate rows, subgroup selection, and unavailable data.
Do not tune exclusions until the desired answer appears.

## 4. Audit every pooled row

Trace the forest-plot label to the original report. For each row verify:

- original and pooled outcome definitions;
- original and pooled exposure/intervention definitions;
- effect measure and analysis scale;
- adjusted covariates and reference category;
- sample, events, follow-up, and sex/arm/timepoint strata;
- whether the value is direct, calculated, converted, digitized, or unexplained;
- cohort identity, overlapping recruitment periods, shared controls, and follow-up updates;
- source page/table/figure and any conflict among article, table, supplement, or code.

Never assume that a forest-plot label is the outcome or exposure originally reported by
the contributing study. Never assume independence merely because reports have different
first authors or years.

## 5. Audit methods and bias

Compare protocol/registration with the final review for databases, dates, eligibility,
outcomes, subgroups, effect measures, risk-of-bias tools, synthesis model, heterogeneity
estimator, publication-bias methods, and certainty framework. Classify deviations as
documented, compatible with analytic flexibility, or not demonstrated; do not infer motive.

Use a design-appropriate risk-of-bias tool at study/result level. Do not replace domain
judgments with a total quality score. Check whether high-risk studies dominate weights,
whether observational adjustment sets target comparable associations, and whether
selective availability of estimates can affect the pool.

Small-study and publication-bias methods are exploratory, especially with few studies or
heterogeneity. Funnel asymmetry is not proof of publication bias; absence of asymmetry is
not proof of its absence. Do not use trim-and-fill as an automatic correction for truth.

## 6. Run the prespecified sensitivity ladder

Read [meta-analysis-sensitivity.md](meta-analysis-sensitivity.md). At minimum compare:

1. exact published reconstruction;
2. directly measured or validly derived outcomes;
3. a common effect measure/estimand;
4. direct outcomes plus common measure;
5. defensible exposure derivations only;
6. DerSimonian–Laird, Paule–Mandel, and restricted maximum likelihood;
7. Hartung–Knapp–Sidik–Jonkman inference;
8. prediction intervals;
9. leave-one-cohort-cluster-out refits;
10. high-risk-of-bias and unresolved-overlap exclusions when prespecified and meaningful.

Use:

```bash
python3 scripts/reconstruct_meta_analysis.py meta_data.csv \
  --analysis-id HEADLINE_POOL \
  --common-measure HR \
  --sensitivity all \
  --allow-mixed-estimands \
  --json

python3 scripts/compare_meta_models.py meta_data.csv \
  --analysis-id HEADLINE_POOL \
  --common-measure HR \
  --direct-outcomes-only \
  --json
```

The standard-library engine reconstructs aggregate inverse-variance models; it is not an
individual-participant-data engine and does not fit multivariate covariance models. When
dependence remains unresolved, deduplicate/select one estimate, obtain a sampling
covariance matrix and use a suitable multilevel/multivariate method, or do not pool.

The source confidence level used to reconstruct each standard error is separate from the
requested output confidence level. The scripts default source intervals to 95%; pass
`--input-confidence` when the rows use another level. Changing the output confidence level
must not change study weights or between-study variance.

## 7. Grade the conclusion

Use one category and explain the evidence:

- **ROBUST:** direction, magnitude, and inference remain materially similar across the
  defensible sensitivity set.
- **DIRECTIONALLY_ROBUST_INFERENCE_SENSITIVE:** direction and magnitude are similar, but
  confidence or prediction intervals cross the null under reasonable methods.
- **NON_ROBUST:** the headline conclusion materially changes after questionable rows or
  methods are removed.
- **NOT_ASSESSABLE:** data or method details are insufficient for a defensible comparison.

Do not classify robustness by a single value of p. Compare magnitude, direction,
confidence interval, prediction interval, heterogeneity, influential clusters, and the
scientific compatibility of the retained estimand.

## 8. Report aggregate-data limits

State whether the work is an exact reconstruction, partial aggregate-data reanalysis,
plausibility check, or not reproducible. Aggregate data usually cannot recover participant
overlap, time-varying hazards, covariate interactions, missing-data mechanisms, original
event counts, or within-study covariance without additional data.

Finish with the mandatory **Reanalysis recommendation** from
[reporting-contract.md](reporting-contract.md). Recommend only an analysis that the
available data can identify.

## Methodological anchors

- [Cochrane Handbook, Chapter 10](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-10)
- [Cochrane Handbook, Chapter 23: multiple outcomes and dependence](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-23)
- [metafor `rma.uni` documentation](https://wviechtb.github.io/metafor/reference/rma.uni.html)
- [PRISMA 2020](https://www.prisma-statement.org/prisma-2020)
