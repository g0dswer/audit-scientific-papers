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

## Heterogeneity and prediction

Report Cochran's Q, between-study variance (`tau²`), and the proportion of observed
variation attributed to heterogeneity (`I²`) with caveats. Numerical thresholds for `I²`
are not a substitute for clinical and methodological assessment.

For a random-effects synthesis with enough independent studies, calculate a prediction
interval on the analysis scale and document the degrees-of-freedom convention. A prediction
interval describes the modeled distribution of true effects in a comparable future study;
it does not fix incompatible estimands and can be unstable when studies are few.

Compare conventional normal/Wald inference with unmodified
Hartung–Knapp–Sidik–Jonkman inference when appropriate. If its scale factor is below one,
say that the unmodified interval can become narrower; any ad hoc modification must be
labeled and reported separately, not silently substituted.

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
