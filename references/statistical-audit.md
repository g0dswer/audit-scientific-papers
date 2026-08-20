# Statistical Audit and Reproducibility

## Contents

1. Audit target and estimand
2. Design, population, and participant flow
3. Outcome and timepoint specification
4. Randomization and analysis populations
5. Internal arithmetic checks
6. Continuous outcomes
7. Binary outcomes and absolute effects
8. Model specification and adjustment
9. Missing data and intercurrent events
10. Power, multiplicity, and subgroup analyses
11. Clinical importance and minimal important difference
12. Safety analysis
13. Reproducibility grading
14. Statistical audit worksheet
15. Methodological links

## 1. Audit target and estimand

State the decision question before reading a favored result. Define population,
intervention, comparator, outcome, timepoint, analysis population, and summary measure.
Then identify the estimand: the treatment effect in a specified population, for a
specified outcome, under a specified handling of intercurrent events, summarized by a
specified contrast.

Use the ICH E9(R1) estimand framework to distinguish treatment-policy, hypothetical,
while-on-treatment, composite, and principal-stratum strategies. Do not call an
unadjusted endpoint contrast the primary treatment effect when the prespecified analysis
was adjusted or model-based. Report the mismatch and its consequence.

An estimand worksheet should include:

| Element | Audit question |
| --- | --- |
| Population | Who was eligible, randomized, treated, and analyzed? |
| Treatment | What intervention, dose, schedule, and adherence rule were used? |
| Comparator | What placebo, usual care, or active control was delivered? |
| Variable | What was measured, with what instrument and direction? |
| Intercurrent events | How were rescue therapy, discontinuation, death, or relapse handled? |
| Population-level summary | Difference, ratio, odds ratio, mean change, or another contrast? |

Reference: [ICH E9(R1) estimands and sensitivity analysis](https://www.ema.europa.eu/en/ich-e9-statistical-principles-clinical-trials-scientific-guideline).

## 2. Design, population, and participant flow

Record design, setting, recruitment dates, eligibility, intervention duration, follow-up,
and whether the trial is randomized, nonrandomized, blinded, open-label, parallel,
crossover, cluster, or adaptive. Map the flow from screened to enrolled, randomized,
allocated, treated, followed, and analyzed.

Reconcile every denominator across the article, supplement, registry, protocol, and SAP.
Separate exclusions known before randomization from post-randomization exclusions. A
complete flow audit asks:

- How many were screened and why were exclusions made?
- How many were randomized to each arm?
- How many received the assigned intervention?
- How many withdrew, crossed over, or received rescue treatment?
- How many contributed the primary outcome and each safety analysis?
- Were missing outcomes observed after treatment discontinuation?
- Do analysis denominators vary by outcome or timepoint?

Do not assume that a per-protocol denominator estimates the randomized treatment-policy
effect. Label any complete-case or observed-case result accordingly.

## 3. Outcome and timepoint specification

For each outcome, record definition, direction, instrument, assessor, threshold, timepoint,
and whether it was primary, key secondary, exploratory, safety, or post hoc. Identify the
primary estimand before examining secondary outcomes, subgroup plots, biomarkers, or
mechanistic claims.

For scales, record range, scoring direction, responder or remission cutoff, validation
population, and evidence for a minimal important difference. A statistically significant
change can be too small to matter to patients; a clinically meaningful difference can be
imprecise.

For binary outcomes, record the event definition, denominator, observation window,
competing risks, repeated-event rule, and whether counts are actual or inferred from
percentages. Do not calculate a number needed to treat from a continuous standardized
effect without an explicitly requested model-based conversion and disclosed assumptions.

## 4. Randomization and analysis populations

Check sequence generation, allocation concealment, implementation, baseline balance as a
diagnostic rather than a proof, and whether knowledge of allocation could influence
enrollment or treatment. Record whether the analysis preserves randomization.

Separate the analysis population from the estimand’s intercurrent-event strategy. They
answer different questions and must be recorded in different fields:

- **Analysis population:** the participants included in the analysis, such as all
  randomized participants (often described as intention-to-treat), a modified
  intention-to-treat set with a stated post-randomization eligibility rule, a
  per-protocol set after adherence-related exclusions, or a safety set after at least
  one dose. The label alone does not establish the inclusion rule or causal target.
- **Treatment-policy strategy:** the effect of assignment regardless of intercurrent
  events, with outcomes after discontinuation, rescue therapy, or switching handled by a
  prespecified rule. It may be estimated in an intention-to-treat population, but
  intention-to-treat and treatment-policy are not synonyms.
- **Hypothetical strategy:** the effect under a specified counterfactual in which an
  intercurrent event did not occur. State the counterfactual and modeling assumptions;
  it is not defined by using a per-protocol population.
- **While-on-treatment strategy:** the effect during treatment exposure before a stated
  intercurrent event. State censoring, truncation, and post-event handling; it is not
  equivalent to per-protocol or intention-to-treat analysis.
- **Composite strategy:** the intercurrent event is incorporated into a combined
  outcome, with the component definition and ordering stated.
- **Principal-stratum strategy:** the effect within a post-randomization stratum defined
  by potential response to an intercurrent event. State the stratum and identifying
  assumptions; it is not observed simply by selecting completers.
- **Extension or open-label population:** analyze descriptively unless a valid randomized
  contrast remains, and do not treat its participant set as an estimand strategy.

For every result, report both fields explicitly: “analysis population = …” and “estimand
strategy = …”. If only aggregate information is available, state which checks are exact,
partial, or impossible. Never use a population label as shorthand for an estimand
strategy.

## 5. Internal arithmetic checks

Reconstruct, when possible:

1. raw within-arm changes and the between-arm change contrast;
2. risks, risk differences, risk ratios, and odds ratios;
3. standard errors from reported confidence intervals;
4. test statistics and two-sided values of p;
5. standardized effects and their direction, as a manual plausibility check unless the
   required denominator and correction are available;
6. event counts from percentages only when denominators make them unique;
7. participant flow and safety denominators.

Use published adjusted estimates for the confirmatory conclusion. An unadjusted
reconstruction is a plausibility check, not a substitute for ANCOVA, mixed models,
time-to-event models, or other prespecified analyses.

The continuous checker can be used as follows:

```bash
python3 scripts/verify_continuous_result.py ci ESTIMATE LOWER UPPER --scale linear --json
python3 scripts/verify_continuous_result.py ci RATIO LOWER UPPER --scale ratio --json
python3 scripts/verify_continuous_result.py changes BT ET BC EC --adjusted-estimate VALUE --json
python3 scripts/verify_continuous_result.py standardized MEAN_DIFFERENCE DENOMINATOR_SD N_TREATMENT N_CONTROL --degrees-of-freedom DF --reported-effect VALUE --reported-metric hedges_g --tolerance 0.1 --json
```

`--scale` is a **required** argument with no default: the command fails rather than guess.
The linear path is for difference measures (mean differences, risk differences) and tests
the estimate against a null of **0** on the reported scale. Ratio measures — hazard ratios, odds ratios, risk
ratios, rate ratios, and any other multiplicative estimate — must **never** be passed to
the linear path: their null is 1, not 0, and their intervals are symmetric only after
logging. Sending a ratio through the linear path fabricates two false findings at once, a
spuriously extreme p-value and a spurious interval asymmetry.

With `--scale ratio` the estimate, lower, and upper bounds must all be strictly positive.
The tool then computes `SE(log ratio) = (log(upper) - log(lower)) / (2*z)`, tests
`z = log(estimate) / SE` against a null of **1**, and reports asymmetry on the log scale.
The output labels every quantity by scale: the log-scale intermediates
(`analysis_estimate`, `analysis_lower`, `analysis_upper`, the standard errors, and the
asymmetry) and the back-transformed companions (`back_transformed`, including the interval
geometric mean, which equals the reported ratio when the interval is exactly log
symmetric). For example HR 0.75 (0.60 to 0.94) gives SE(log HR) 0.11453, z -2.512,
p 0.012, and essentially zero log-scale asymmetry; the linear path on the same numbers
reports p < 0.001 and a large fake asymmetry.

The `null_value` field is always emitted (0 for linear, 1 for ratio) so the tested
assumption is never invisible. The linear path also carries a heuristic guard: when the
estimate and both bounds are positive, the interval is materially asymmetric on the linear
scale, and the log-scale departure from symmetry is at most a quarter of the linear one,
the output emits a `scale_warning` in both the text and the JSON naming `--scale ratio`.
The warning never changes a computed number; treat it as a prompt to confirm the measure
type, and re-run on the ratio path if the estimate is multiplicative.

**The guard is a second net, not the primary defence.** It cannot fire on a ratio close to
the null with a narrow interval, because such an interval is very nearly symmetric on both
scales. Against the 38 ratio rows of the repository's own Naghshi 2020 fixture the guard
misses six, including HR 0.98 (0.94 to 1.02) and HR 1.00 (0.98 to 1.02) — the shape of the
largest and most heavily weighted cohort studies, and the rows whose weight most influences
a pooled result. On HR 0.98 (0.94 to 1.02) the linear path reports `z = 48.02` where the
truth is `z = -0.97`, with no warning available. That is why `--scale` is required rather
than defaulted: identify the effect measure yourself, every time.

Values reconstructed from an interval are approximate. Do not infer degrees of freedom,
the exact model, or the published p-value from a confidence interval alone. Inspect
asymmetry and report when a normal approximation is only a plausibility check. Judge
asymmetry on the analysis scale: a ratio interval that is asymmetric on the linear scale
is not a red flag, only a consequence of the log scale.

The continuous checker can calculate an approximate Cohen’s d and Hedges’ g when the
caller supplies the mean difference, denominator SD, and valid arm sample sizes:

It uses `d = mean_difference / denominator_sd` and
`J = 1 - 3 / (4*df - 1)`, then reports `g = J*d`. When `--degrees-of-freedom` is omitted,
the classical two-independent-groups
value `n_treatment + n_control - 2` is used and the output marks
`df_source=two_independent_groups`; this scope is valid only when the denominator SD
matches that classical model. A supplied finite df >1, including a non-integer, is marked
`df_source=user_supplied` and is valid only when it matches the denominator, covariance,
and model.

If `--reported-effect` is supplied, `--reported-metric` is mandatory and must be either
`cohens_d` or `hedges_g`; ambiguous combinations are rejected. The reported value is
compared with the corresponding reconstructed metric, not automatically with Hedges’ g.
The absolute difference and `consistent_with_tolerance` are an arithmetic check only:
they are not an equivalence test, confirmation of the model, or validation of the reported
effect. If the denominator definition, SD/SE, covariance information, sample sizes, or
correction rule is unavailable, report the standardized effect as unavailable rather than
promising exact verification.

## 6. Continuous outcomes

Distinguish endpoint analysis, change-score analysis, ANCOVA adjusted for baseline,
repeated-measures models, mixed models, generalized estimating equations, and multiple
imputation. Record covariance structure, time-by-treatment interaction, baseline
adjustment, degrees of freedom, estimation method, and missing-data assumptions.

For a reported estimate and confidence interval, compute an approximate standard error
and normal statistic only as a consistency check. Choose the scale before the check:
`--scale linear` for difference measures against a null of 0, `--scale ratio` for hazard,
odds, risk, or rate ratios, which are analysed on the log scale against a null of 1.
Passing a ratio measure to the linear path is an error, not a conservative
approximation: it invents both a false p-value and a false asymmetry. If the interval is
asymmetric **on the analysis scale**, retain separate lower- and upper-side widths and
state the asymmetry; a ratio interval is expected to look asymmetric on the linear scale
and symmetric after logging, and only log-scale asymmetry is a reportable signal. Always
state the null value the reported p-value was tested against. Never present an
approximate reconstruction as exact reanalysis or as an automated standardized-effect
verification.

For change means, calculate the raw treatment change minus control change, then compare
it with the adjusted estimate. Explain that these can target different estimands and
are not interchangeable.

For repeated outcomes, ask whether the selected timepoint, model covariance, contrast,
and multiplicity adjustment were prespecified. A favorable plot at one timepoint is not
the same as a prespecified treatment-by-time effect.

## 7. Binary outcomes and absolute effects

When valid two-arm counts exist, run:

```bash
python3 scripts/calculate_binary_effects.py E1 N1 E0 N0 --json
```

State the event direction explicitly on every run: `--harm` for an undesirable event
(death, infarction, relapse) and `--benefit` for a desirable one. The two flags are
mutually exclusive. If neither is given the calculator keeps its historical assumption
that the event is desirable, but flags it: `event_direction_specified` is false and an
`event_direction_notice` appears in both the text and the JSON. Never accept an
unspecified direction in a finished audit, because it silently inverts the NNT and NNH
labels. Inspect definitions, time horizon, denominators, competing risks, and whether
counts are unique before calculating.

The calculator reports risks, risk difference, relative effects, Newcombe--Wilson
intervals, reciprocal effects, and an optional two-sided Fisher value of p when SciPy is
available. Relative effects are reported with intervals, never as naked point estimates:
`risk_ratio_ci` uses the Katz large-sample method,
`SE(log RR) = sqrt(1/e1 - 1/n1 + 1/e0 - 1/n0)`, and `odds_ratio_ci` uses Woolf's method,
`SE(log OR) = sqrt(1/a + 1/b + 1/c + 1/d)`; both are computed on the log scale and
back-transformed, and both are labeled large-sample approximations. It does not add a
continuity correction to RR or OR. Mathematically undefined relative effects — and the
intervals of any table with a zero cell entering the standard error — are explicit null
values, not hidden finite estimates.

Number-needed-to-treat/harm rules are strict:

- If the risk-difference interval excludes zero, report the point NNT/NNH and reciprocal
  interval with the event direction and time horizon.
- If the interval crosses zero, lead with **binary effect inconclusive**. Label the point
  reciprocal exploratory and show possible benefit, no effect at infinity, and possible
  harm separately.
- Never report a finite single NNT confidence interval across zero.
- Do not convert a standardized continuous effect into NNT without an explicitly
  requested model-based conversion and stated baseline-risk and distributional
  assumptions.

When rounding positive reciprocals, round conservatively away from zero and preserve
the unrounded value. An interval crossing zero is a precision problem, not evidence that
the point reciprocal is a reliable patient-level benefit.

## 8. Model specification and adjustment

Compare article methods with the registry, protocol, and SAP. Check baseline covariates,
interaction terms, transformation, link function, robust variance, clustering, weighting,
degrees of freedom, estimand, contrasts, and multiplicity adjustments.

Ask whether the model was chosen before outcome inspection, whether the reported model
was one of several plausible specifications, and whether sensitivity analyses weaken or
strengthen the conclusion. A late analysis plan may be legitimate but is not equivalent
to prospective prespecification.

Do not treat a statistically significant within-arm change and a nonsignificant control
change as a treatment interaction. Require a direct between-arm contrast or a valid
group-by-time interaction.

## 9. Missing data and intercurrent events

Record missingness by arm, outcome, and timepoint. Identify withdrawals, loss to follow-
up, treatment discontinuation, rescue therapy, and protocol deviations. State whether
the analysis assumes missing at random, uses multiple imputation, uses mixed models,
uses last observation carried forward, or is complete-case.

Examine sensitivity to missing-not-at-random scenarios when relevant. A high completion
rate does not prove missingness is harmless, and a differential withdrawal pattern can
change the estimand.

Under treatment-policy strategies, participants who discontinue may still contribute
outcomes. Under hypothetical or while-on-treatment strategies, explain the target and
the assumptions. Do not silently combine these strategies.

## 10. Power, multiplicity, and subgroup analyses

Record the sample-size target, assumed effect, variance or event rate, alpha, power,
allocation, attrition allowance, interim rules, and whether the calculation matches the
primary estimand. A post hoc power calculation is not evidence that a null result is
true or that a positive result is unbiased.

Map every primary, key secondary, exploratory, timepoint, subgroup, biomarker, and safety
comparison. Record multiplicity control, hierarchy, gatekeeping, false-discovery rules,
or the absence of adjustment. Multiplicity increases the chance of a false positive but
does not by itself prove intentional p-hacking.

For subgroups, check prespecification, interaction tests, sample size, plausibility,
direction, and consistency. Never infer an interaction from significance in one subgroup
and nonsignificance in another.

## 11. Clinical importance and minimal important difference

Separate statistical significance, magnitude, precision, and patient importance. Identify
the minimal important difference or responder threshold from validated external evidence
when possible. If no trustworthy threshold exists, say so and use a range of plausible
thresholds rather than inventing one.

For scale outcomes, report the instrument, direction, range, baseline, endpoint or change,
between-arm contrast, confidence interval, and whether the interval overlaps a clinically
important threshold. For binary outcomes, describe the event meaning, absolute risk, time
horizon, and consequences of benefit or harm.

## 12. Safety analysis

Analyze harms separately from efficacy. Give denominators, exposure time, severity,
seriousness, discontinuations, adverse events of special interest, and arm-specific
counts. Distinguish treatment-emergent events from all events and distinguish patients
with at least one event from event totals.

Zero observed serious events in a small, short trial are imprecise absence of observation,
not proof of safety. State the follow-up and denominator and, when useful, provide a
binomial upper bound or a qualitative warning about rare-harm uncertainty.

Review harms relevant to mechanism and population, including psychiatric activation,
impulsivity, suicidality, cardiovascular events, laboratory abnormalities, withdrawal,
and interactions when applicable. Do not use a favorable within-arm safety pattern to
claim comparative safety without a between-arm contrast.

## 13. Reproducibility grading

Use one of these labels:

- **Exact:** public data, code, model specification, and analytic outputs permit the same
  estimand and result to be reproduced.
- **Partial:** key counts or summary statistics permit selected checks, but individual
  data, model outputs, or full code are missing.
- **Plausibility-only:** arithmetic checks are possible, but the published analysis cannot
  be independently recreated.
- **Impossible from public materials:** critical inputs or definitions are unavailable.

Use “reconstructed,” “approximate,” or “reported” precisely. Do not infer exact
reanalysis from a calculator output that uses a different estimand or unadjusted data.

## 14. Statistical audit worksheet

Complete these fields before writing the verdict:

- [ ] Design, setting, recruitment, intervention, comparator, and time horizon.
- [ ] Primary estimand and analysis population.
- [ ] Participant flow and all post-randomization exclusions.
- [ ] Outcome definition, direction, instrument, threshold, and timepoint.
- [ ] Published estimate, uncertainty, value of p, and denominator checked.
- [ ] Registry, protocol, SAP, and article compared by date.
- [ ] Missingness, intercurrent events, adjustment, covariance, and degrees of freedom.
- [ ] Multiplicity, subgroups, interim analyses, and analytic flexibility.
- [ ] Clinical importance and MID status.
- [ ] Efficacy and safety analyzed separately.
- [ ] Absolute effects calculated only from defensible binary events.
- [ ] Reproducibility tier and unavailable inputs stated.

## 15. Methodological links

- [CONSORT 2025](https://www.consort-spirit.org/)
- [ICH E9(R1) statistical principles](https://www.ema.europa.eu/en/ich-e9-statistical-principles-clinical-trials-scientific-guideline)
- [Cochrane RoB 2 tool](https://www.riskofbias.info/welcome/rob-2-0-tool)
- [ClinicalTrials.gov history guidance](https://clinicaltrials.gov/submit-studies/prs-help/how-edit-record)
- [JBI critical appraisal tools](https://jbi.global/critical-appraisal-tools)
- [CEBM critical appraisal tools](https://www.cebm.ox.ac.uk/resources/ebm-tools/critical-appraisal-tools)

These sources guide method selection and reporting. The study-specific evidence remains
the article, its dated supplements, registry history, protocol, SAP, and accessible data.

## Meta-analysis routing

This file governs primary-study and clinical-trial statistical checks. For any systematic
review or meta-analysis, also read `meta-analysis-audit.md`,
`meta-analysis-extraction.md`, `effect-measure-compatibility.md`, and
`meta-analysis-sensitivity.md` in full. Use their row-provenance, effect-compatibility,
dependence, heterogeneity, prediction-interval, and sensitivity requirements. Do not adapt
a two-arm trial calculator as a substitute for an inverse-variance meta-analysis.
