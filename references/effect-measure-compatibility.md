# Effect-measure and Estimand Compatibility

## Governing rule

**A random-effects model does not make different estimands commensurable. Heterogeneity
modeling is not estimand harmonization.**

Before pooling, check outcome definition, follow-up, population, intervention/exposure
contrast, comparator, effect measure, and adjustment target. A shared ratio scale is not
enough.

## Default compatibility matrix

| Combination | Default action |
| --- | --- |
| Risk ratio + risk ratio | Pool only if outcome, horizon, contrast, and populations are compatible |
| Odds ratio + odds ratio | Pool only under compatible outcome and sampling definitions |
| Hazard ratio + hazard ratio | Pool only if endpoint and time-to-event estimand are compatible; assess proportional-hazards concerns |
| Incidence-rate ratio + incidence-rate ratio | Pool only if event process and person-time definitions are compatible |
| Mean difference + mean difference | Pool only on the same instrument and units |
| Standardized mean difference + standardized mean difference | Pool only when constructs and variance definitions are comparable |
| Odds ratio + risk ratio | Do not pool by default; conversion needs justified baseline risk and assumptions |
| Hazard ratio + risk ratio | Estimand mismatch; analyze separately by default |
| Hazard ratio + odds ratio | Estimand mismatch; analyze separately by default |
| Ratio measure + mean difference | Incompatible scales; do not pool |

## Measure-specific cautions

- A hazard ratio describes relative instantaneous event rates over follow-up and commonly
  relies on proportional-hazards interpretation. It is not a risk ratio at a fixed time.
- An odds ratio can materially differ from a risk ratio when outcomes are common and is
  often misinterpreted as one.
- A risk ratio depends on a defined cumulative-risk horizon.
- Rate ratios allow recurrent/person-time contributions that may not match first-event
  risks.
- Standardized mean differences can differ because study variances differ, not only
  because treatment effects differ.

Do not automatically convert hazard ratios, risk ratios, and odds ratios. If a conversion
is scientifically required, document its formula, baseline risk, time horizon, assumptions,
and sensitivity. Prefer separate native-measure pools or structured narrative synthesis.

## Observational adjustment sets

Adjusted estimates with materially different covariate sets need not target the same
conditional association. Build an adjustment matrix and identify confounders, mediators,
colliders, and unavailable variables. Prefer the estimate specified by the review protocol
and justified by a causal model; do not automatically choose the most adjusted estimate.

If compatible native estimates cannot be isolated, do not manufacture a common effect.
Use a structured synthesis without meta-analysis and state why quantitative pooling is
not defensible.
