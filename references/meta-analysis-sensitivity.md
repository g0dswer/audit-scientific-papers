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

The ladder is cumulative where its labels imply cumulative cleaning. S6 through S8 start
from S5's defensible-exposure subset; changing the variance estimator, inference method,
or omitted cohort must not silently reintroduce assumption-dependent exposure rows.

## Heterogeneity and prediction

Report Cochran's Q, between-study variance (`tau²`), and the proportion of observed
variation attributed to heterogeneity (`I²`) with caveats. The engine reports
`I2_method` explicitly because its Q-based I² is not estimator-specific even when DL, PM,
and REML produce different tau² values. Numerical thresholds for `I²` are not a substitute
for clinical and methodological assessment.

For a random-effects synthesis with enough independent studies, calculate a prediction
interval on the analysis scale and document the degrees-of-freedom convention. A prediction
interval describes the modeled distribution of true effects in a comparable future study;
it does not fix incompatible estimands and can be unstable when studies are few.

### Degrees-of-freedom convention

The script builds the prediction interval on the analysis scale from
`sqrt(SE_conventional² + tau²)`. It states the degrees-of-freedom convention, multiplier
distribution, and named method in `prediction_df_convention`, `prediction_interval_df`,
`prediction_multiplier_distribution`, and `prediction_interval_method`.

| Convention | df | Source | Flag |
| --- | --- | --- | --- |
| Current Cochrane / Review Manager | Wald: normal multiplier; HKSJ: `t(k - 1)` | Cochrane Handbook 10.10.4.3 and current Review Manager implementation notes | `--prediction-df k-1` (default) |
| Historical Higgins–Thompson–Spiegelhalter | `t(k - 2)` | Higgins, Thompson & Spiegelhalter (2009); IntHout et al. (2016) | `--prediction-df k-2` |

The default is the current Cochrane/Review Manager behavior. The historical `k - 2`
option remains available only for explicit reproduction; with two studies it has zero
degrees of freedom, so no prediction interval is produced and the output says why. When
you report a published review's prediction interval, state which convention and inference
method the authors used — if they do not say, treat the interval as unverifiable rather
than assuming it matches yours.

### Prediction intervals and the confidence-interval method

The prediction standard error always uses the **conventional** inverse-variance standard
error, even when `--inference HKSJ` is selected for the confidence interval. The multiplier
does follow the selected current method: Wald uses the normal quantile, while HKSJ uses
Student's t with `k - 1` degrees of freedom. This matches the current Cochrane/Review
Manager distinction without substituting the HKSJ confidence-interval standard error into
the prediction standard error.

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
