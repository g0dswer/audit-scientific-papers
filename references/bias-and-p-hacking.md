# Risk of Bias, Selective Reporting, and Analytic Flexibility

## Contents

1. Scope and result-level judgment
2. RoB 2 domain 1: randomization process
3. RoB 2 domain 2: deviations from intended interventions
4. RoB 2 domain 3: missing outcome data
5. RoB 2 domain 4: outcome measurement
6. RoB 2 domain 5: selection of the reported result
7. Overall judgment and applicability
8. P-hacking evidence vocabulary
9. Multiplicity and analytic flexibility
10. Difference-in-significance error
11. Extensions, safety, and rare harms
12. Evidence against p-hacking
13. Bias worksheet
14. Methodological links

## 1. Scope and result-level judgment

Apply Cochrane Risk of Bias 2 (RoB 2) to a specific result, outcome, timepoint, and
analysis population. Do not assign one reassuring label to an entire trial when bias
differs across outcomes or analyses. A randomized design does not by itself guarantee
valid inference.

Use signaling questions and record the evidence that supports each answer. Distinguish
low risk, some concerns, and high risk. Explain the pathway from a design or reporting
feature to the direction and likely magnitude of bias. Do not average domain judgments
into a numerical score.

The result-level unit should state:

| Field | Example content |
| --- | --- |
| Outcome | Primary depression scale response |
| Timepoint | Prespecified week 8 |
| Contrast | Randomized treatment-policy difference |
| Population | All randomized participants or stated alternative |
| Evidence | Article table, registry version, protocol, or supplement |
| Judgment | Low, some concerns, or high risk with rationale |

Reference: [Cochrane RoB 2 tool](https://www.riskofbias.info/welcome/rob-2-0-tool).

## 2. RoB 2 domain 1: randomization process

Ask whether the allocation sequence was random, whether allocation was concealed until
assignment, and whether baseline imbalances suggest a problem. Random-sequence generation
can be adequate while concealment is unclear. Baseline imbalance is a signal, not proof
of failed randomization.

Check:

- sequence generation method and who generated it;
- block, stratification, or minimization rules;
- concealment mechanism and who controlled access;
- timing of consent, eligibility confirmation, and assignment;
- whether recruiters could predict the next assignment;
- baseline variables by arm and the number of measurements examined;
- post-randomization exclusions that could create imbalance.

Do not infer adequate concealment from the word “randomized.” If the method is omitted,
record the absence and downgrade certainty rather than assuming the best case.

## 3. RoB 2 domain 2: deviations from intended interventions

Assess blinding of participants, carers, intervention providers, and outcome assessors,
as relevant to the outcome. Record whether deviations were balanced, whether they arose
because of knowledge of assignment, and whether the analysis estimates the intended
treatment-policy effect.

For placebo-controlled trials, inspect treatment guesses, side-effect profiles, rescue
therapy, cointerventions, adherence, dose changes, and unblinding after adverse events.
Participant or clinician belief can alter reporting, behavior, dropout, and cointervention
use even when the nominal intervention is identical.

If unblinding is plausible, ask whether subjective outcomes are more vulnerable than
objective outcomes. Analyze an intention-to-treat treatment-policy result separately from
per-protocol or while-on-treatment results. Do not treat a per-protocol result as a clean
randomized estimate when exclusions depend on post-randomization behavior.

## 4. RoB 2 domain 3: missing outcome data

Describe the amount, reasons, timing, and arm imbalance of missingness. Separate missing
primary outcomes from missing safety data and assess whether missingness depends on
prognosis, adverse effects, treatment response, or assignment.

Check the assumptions and implementation of:

- mixed models and repeated-measures likelihood;
- multiple imputation and imputation model variables;
- complete-case analysis;
- last observation carried forward;
- tipping-point or pattern-mixture sensitivity analyses;
- discontinuation and rescue-treatment rules.

High completion does not prove that missingness is harmless. If the outcome is subjective,
loss after perceived lack of benefit or adverse effects can be especially consequential.
State whether the result remains plausible under reasonable departures from the primary
missing-data assumption.

## 5. RoB 2 domain 4: outcome measurement

Assess whether the outcome was appropriate, measured consistently, and likely influenced
by knowledge of intervention. Record the instrument, assessor training, timing, threshold,
scoring direction, and whether the measurement differs from the prespecified outcome.

For subjective outcomes, inspect assessor blinding, participant self-report, treatment
guessing, adverse-effect cues, and differential encouragement. For objective outcomes,
check device calibration, laboratory methods, adjudication, and missing measurements.

Do not replace a registered instrument, cutoff, or timepoint with a more favorable one
without recording the deviation. A valid measurement can still be selectively reported.

## 6. RoB 2 domain 5: selection of the reported result

Compare the article with the registry, protocol, SAP, supplements, preprint, peer-review
file, and dated amendments. Look for multiple eligible outcomes, scales, timepoints,
subgroups, models, covariate sets, and handling of missing data.

Ask whether the reported result appears selected after examining the data. A late analysis
plan, unreported outcome, changed primary endpoint, omitted negative analysis, or unexplained
denominator change is evidence to investigate. It is not automatically proof of intent.

Preserve the distinction between a documented deviation and an inference about motive.
Record which result was prespecified, which was reported, and whether the difference
changes the clinical conclusion.

## 7. Overall judgment and applicability

Overall RoB 2 judgment should follow the most concerning relevant domain and the target
result, not an average. Explain whether concerns are serious enough to change the direction
or certainty of the conclusion.

Cross-check applicability using [JBI critical appraisal tools](https://jbi.global/critical-appraisal-tools)
and [CEBM critical appraisal tools](https://www.cebm.ox.ac.uk/resources/ebm-tools/critical-appraisal-tools).
These tools complement, but do not replace, a result-level RoB 2 judgment.

External validity is separate from internal risk of bias. Record differences in age,
severity, comorbidity, treatment setting, concomitant therapy, recruitment method,
follow-up, and outcome ascertainment. A low-bias trial can still have limited applicability.

## 8. P-hacking evidence vocabulary

Use three calibrated categories:

### Documented

Use this only for a dated protocol or registry change, undisclosed analysis change, omitted
registered outcome, post hoc model, or reproducible discrepancy supported by a source.

### Compatible with analytic flexibility

Use this for multiple uncorrected tests, selected timepoints, stepwise modeling, subgroup
proliferation, a late analysis plan, selective emphasis, or other patterns with both benign
and problematic explanations. Describe the pattern and its impact without attributing
intent.

### Not demonstrated

Use this for intentional manipulation, fabrication, access to unblinded results before a
decision, or suppression of unknown negative analyses when no evidence supports the claim.
Lack of proof of misconduct is not proof that every analysis was prespecified.

Never state that p-hacking occurred merely because there are many values of p. Multiplicity
is a statistical risk; misconduct is a separate evidentiary claim.

## 9. Multiplicity and analytic flexibility

Map the analytic search space:

- primary, key secondary, exploratory, and safety outcomes;
- scales, responder thresholds, and remission definitions;
- follow-up timepoints and windows;
- adjusted and unadjusted models;
- covariate sets and interaction terms;
- subgroup and moderator analyses;
- missing-data and outlier rules;
- one-sided versus two-sided testing;
- interim looks and stopping decisions;
- selective table, figure, and narrative emphasis.

Record the prespecified multiplicity strategy, hierarchy, alpha allocation, gatekeeping,
or absence of control. Explain how multiplicity affects false-positive uncertainty. A
single stable prospective primary outcome and robust sensitivity analyses weigh against a
strong p-hacking allegation, although they do not erase other concerns.

## 10. Difference-in-significance error

Do not infer a treatment effect because the treatment arm changed significantly from
baseline while the control arm did not, or because one value of p is below 0.05 and the
other is not. The relevant question is the direct between-arm contrast or the interaction
term.

Required check:

1. identify the within-arm estimates and values of p;
2. locate the direct between-arm estimate and confidence interval;
3. locate a group-by-time interaction if a longitudinal claim is made;
4. if neither exists, label the causal comparison unsupported or incomplete.

This applies equally to biomarkers, inflammation markers, imaging, safety signals, and
mechanistic outcomes.

## 11. Extensions, safety, and rare harms

Treat uncontrolled open-label extensions as descriptive. Without a concurrent randomized
comparator, changes can reflect regression to the mean, natural history, selective entry,
survivor bias, expectations, treatment changes, and attrition. Do not claim maintenance,
durability, or comparative efficacy from completers alone.

Analyze safety with denominators, exposure time, serious events, withdrawals, and events
of special interest. Zero observed serious events in a small, short study are imprecise
absence of observation, not proof that the treatment is safe or that rare harm is absent.

Do not infer comparative safety from a within-arm absence of events. Use exact or binomial
precision where appropriate and state the follow-up horizon.

## 12. Evidence against p-hacking

Every p-hacking section should actively report counterevidence:

- a stable prospective primary outcome;
- agreement between registry, SAP, and article;
- consistent direction across prespecified reasonable analyses;
- robustness to plausible covariate, missing-data, and model choices;
- corrections or revisions that weaken rather than strengthen significance;
- transparent reporting of null secondary and safety results.

State when counterevidence is unavailable because a protocol, SAP, version history, or
analysis code could not be accessed. Missing evidence is an uncertainty, not evidence for
or against intent.

## 13. Bias worksheet

For each target result, complete:

- [ ] Random sequence and concealment evidence.
- [ ] Baseline imbalance as a diagnostic, not a proof.
- [ ] Blinding, treatment guesses, adverse-effect cues, and cointerventions.
- [ ] Adherence, deviations, rescue therapy, and estimand alignment.
- [ ] Missing outcome amount, reasons, patterns, and assumptions.
- [ ] Outcome measurement blinding, validity, and consistency.
- [ ] Registry/protocol/SAP comparison and selected result concerns.
- [ ] RoB 2 judgment with evidence and rationale.
- [ ] Applicability limitations using JBI/CEBM principles where useful.
- [ ] Multiplicity and analytic-flexibility map.
- [ ] Evidence for and against p-hacking.
- [ ] Direct interaction test for any treatment-contrast claim.
- [ ] Extension and rare-harm claims labeled appropriately.

## 14. Methodological links

- [CONSORT 2025](https://www.consort-spirit.org/)
- [ICH E9(R1) statistical principles](https://www.ema.europa.eu/en/ich-e9-statistical-principles-clinical-trials-scientific-guideline)
- [Cochrane RoB 2 tool](https://www.riskofbias.info/welcome/rob-2-0-tool)
- [ClinicalTrials.gov history guidance](https://clinicaltrials.gov/submit-studies/prs-help/how-edit-record)
- [JBI critical appraisal tools](https://jbi.global/critical-appraisal-tools)
- [CEBM critical appraisal tools](https://www.cebm.ox.ac.uk/resources/ebm-tools/critical-appraisal-tools)

These sources support structured appraisal. They do not convert an incomplete public record
into certainty about the underlying trial.
