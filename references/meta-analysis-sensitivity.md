# Meta-analysis Sensitivity and Reanalysis

## Reproduce, then challenge

The first model must reconstruct the publication with its displayed rows and stated method.
Only after reproduction passes should a defensibility ladder be interpreted. If it fails,
investigate the discrepancy before choosing alternative exclusions or estimators.

## Standard sensitivity ladder

| ID | Analysis | Question answered |
| --- | --- | --- |
| S1 | Published reconstruction | Can the displayed headline number be reproduced? |
| S2 | Direct/valid outcomes | Does relabeling or unjustified derivation drive the result? |
| S3 | Common native effect measure | Does effect-measure mixing drive the result? |
| S4 | Direct outcome + common measure | What is the cleanest comparable aggregate pool? |
| S5 | Defensible exposure derivations only | Do constructed exposures drive the result? |
| S6 | DL, PM, and REML between-study variance | Is the point/heterogeneity conclusion estimator-sensitive? |
| S7 | Hartung–Knapp–Sidik–Jonkman | Is random-effects inference sensitive to small-sample uncertainty? |
| S8 | Leave one cohort cluster out | Does one independent participant source drive the result? |
| S9 | Exclude high-risk-of-bias results | Does internal validity drive the conclusion? |
| S10 | Remove or model overlapping cohorts | Does non-independence narrow uncertainty or shift the estimate? |

DL means DerSimonian–Laird, PM means Paule–Mandel, and REML means restricted maximum
likelihood. Do not use abbreviations without defining them in the user-facing report.

The included script automates S1 through S8 when the required row fields are available.
S9 and S10 require substantive risk-of-bias and dependence judgments; never infer them
from effect size alone.

The ladder honours the model you asked for. Under `--model fixed`, rungs S1 to S5 and S8
are refitted as fixed-effect models, so the rung labelled published reconstruction
reproduces the same model the reproduction gate validated. S6 (between-study variance
estimators) and S7 (Hartung–Knapp–Sidik–Jonkman) are meaningful only for random effects,
so under a fixed-effect request they return `NOT_ASSESSABLE` with a reason rather than
publishing random-effects numbers under a fixed-effect heading. Every rung reports the
model that produced it; never quote a rung without it.

## Heterogeneity and prediction

Report Cochran's Q, between-study variance (`tau²`), and the proportion of observed
variation attributed to heterogeneity (`I²`) with caveats. Numerical thresholds for `I²`
are not a substitute for clinical and methodological assessment.

For a random-effects synthesis with enough independent studies, calculate a prediction
interval on the analysis scale and document the degrees-of-freedom convention. A prediction
interval describes the modeled distribution of true effects in a comparable future study;
it does not fix incompatible estimands and can be unstable when studies are few.

### Degrees-of-freedom convention

The script builds the prediction interval as
`pooled ± t(df) * sqrt(SE_conventional² + tau²)` on the analysis scale, and states the
convention it used in every output (`prediction_df_convention` and
`prediction_interval_df`).

| Convention | df | Source | Flag |
| --- | --- | --- | --- |
| Cochrane / Higgins–Thompson–Spiegelhalter | `k - 2` | Cochrane Handbook 10.10.4.3; Higgins, Thompson & Spiegelhalter (2009); IntHout et al. (2016) | `--prediction-df k-2` (default) |
| Model degrees of freedom | `k - 1` | Some software reports `k - p` for an intercept-only model | `--prediction-df k-1` |

The default is `k - 2`, because it is the convention the Cochrane Handbook specifies and
this skill audits reviews against Cochrane conventions. The `k - 1` interval is narrower;
on a 13-study pool the difference is roughly one percent of interval width, but it grows
quickly as `k` falls. Under `k - 2` a two-study pool has zero degrees of freedom, so no
prediction interval is produced and the output says why. When you report a published
review's prediction interval, state which convention the authors used — if they do not
say, treat the interval as unverifiable rather than assuming it matches yours.

### Prediction intervals do not depend on the confidence-interval method

The prediction interval is always built from the **conventional** inverse-variance standard
error, even when `--inference HKSJ` is selected for the confidence interval. A prediction
interval describes the modeled distribution of true effects; it is not a property of how
you chose to construct the interval around the mean. Reporting an HKSJ-inflated prediction
interval alongside an HKSJ confidence interval double-counts the same small-sample
adjustment.

Compare conventional normal/Wald inference with unmodified
Hartung–Knapp–Sidik–Jonkman inference when appropriate. If its scale factor is below one,
say that the unmodified interval can become narrower; any ad hoc modification must be
labeled and reported separately, not silently substituted. If the scale factor is exactly
zero — every study estimate identical, so `Q = 0` — the method is not estimable and the
script refuses rather than emitting a zero-width interval.

## Influence

Refit the complete selected model after deleting each independent cohort cluster. Report
change in pooled estimate, interval, `tau²`, `I²`, and whether the interval's relationship
to the null changes. This is an influence diagnostic, not a license to delete an
unfavorable study. Prespecify exclusions where possible and explain every substantive
decision.

## Robustness categories

- `ROBUST`: all defensible analyses preserve materially similar direction, magnitude,
  and inferential conclusion.
- `DIRECTIONALLY_ROBUST_INFERENCE_SENSITIVE`: direction/magnitude are similar but a
  reasonable confidence or prediction interval crosses the null.
- `NON_ROBUST`: a defensible provenance, estimand, bias, or dependence correction changes
  the material conclusion.
- `NOT_ASSESSABLE`: missing data or unresolved methods prevent a defensible ladder.

Set materiality using clinical/domain context, not a mechanical percentage or value of p.

## Mandatory reanalysis recommendation

Every audit ends with one recommendation category:

1. **Feasible now with public aggregate data.** Name the exact rows, estimand, model,
   sensitivity ladder, and expected decision value.
2. **Feasible only with specified additional data.** List the participant-level or
   aggregate inputs, covariance, coding, follow-up, missingness, or versioned code required.
3. **Not defensible as a quantitative reanalysis.** Explain the identification barrier and
   recommend the best alternative: separate native-measure pools, structured narrative
   synthesis, Synthesis Without Meta-analysis, updated search, or independent replication.

Also state what the proposed reanalysis could change. Do not recommend complex modeling
that cannot answer a decision-relevant question or that the available data cannot support.
