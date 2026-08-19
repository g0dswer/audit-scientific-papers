# Clinical Trial Auditor

A reusable ChatGPT skill for rigorous critical appraisal of clinical trials.

Give it a paper, link, DOI, or uploaded file. The skill guides ChatGPT through the
article, supplementary materials, trial registry, protocol, statistical analysis
plan, and other available evidence before reaching a conclusion.

## What it does

- Reconstructs the primary result and checks the reported calculations.
- Examines missing data, exclusions, multiplicity, subgroup analyses, and outcome
  switching.
- Assesses risk of bias at the result level.
- Distinguishes documented problems from patterns merely compatible with analytic
  flexibility or p-hacking.
- Calculates absolute effects and the number needed to treat or harm when the data
  support those calculations.
- Checks confidence intervals, risk differences, Cohen's d, and Hedges' g with clear
  limits on approximate reconstructions.
- Separates statistical significance from clinical importance.
- Reports what is supported, uncertain, unsupported, or not reproducible from public
  materials.

## Quick start in ChatGPT

In a ChatGPT environment that supports Codex, Work Mode, and personal skills, paste:

```text
Install or import the personal skill from this public repository:

https://github.com/g0dswer/g0dswer-audit-clinical-trials

Read SKILL.md and every file it references. Preserve the repository structure, run
the tests in scripts/test_calculations.py, and validate the skill before using it.

Then use $audit-clinical-trials to critically appraise this study. Retrieve the full
article and all reasonably available supplementary materials, registry history,
protocol, statistical analysis plan, peer-review files, code, and data. Reconstruct
the main results, assess risk of bias, selective reporting, multiplicity, p-hacking
signals, clinical importance, harms, and absolute effects. Calculate the number
needed to treat or harm only when defensible, and clearly separate documented
evidence from suspicion or unavailable information.

Study:
[PASTE THE LINK, DOI, OR ATTACH THE FILE]
```

If personal skill installation is unavailable, paste this instead:

```text
Use SKILL.md and all referenced files from this repository as the mandatory audit
protocol for the following study:

https://github.com/g0dswer/g0dswer-audit-clinical-trials

Study:
[PASTE THE LINK, DOI, OR ATTACH THE FILE]
```

## Expected output

The final report includes:

1. A calibrated overall verdict.
2. Study design, population, intervention, comparator, outcomes, and estimand.
3. Independent reconstruction of the main result where possible.
4. Clinical importance and absolute effects.
5. Number needed to treat or harm, including uncertainty, when valid.
6. Result-level risk-of-bias assessment.
7. Selective-reporting and p-hacking assessment with evidence for and against.
8. Safety, external validity, spin, and reproducibility limitations.
9. Direct links to the evidence used.

## Local validation

The calculation tools use Python 3. SciPy is optional and is used only when available
for the two-sided Fisher exact test.

```bash
git clone https://github.com/g0dswer/g0dswer-audit-clinical-trials.git
cd g0dswer-audit-clinical-trials
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

The current release passes 29 automated tests and the official skill validator. It
was also evaluated with independent fresh-context scenarios covering inconclusive
number-needed-to-treat estimates, p-hacking allegations, subgroup errors,
uncontrolled extensions, and rare safety events.

## Important limitations

- The skill cannot recreate unavailable individual participant data or undocumented
  statistical models.
- A reconstructed aggregate calculation is not automatically equivalent to the
  study's adjusted analysis.
- Multiplicity or a late analysis plan can raise concern but does not, by itself,
  prove intentional p-hacking or misconduct.
- This is a structured appraisal tool, not a substitute for independent statistical,
  clinical, or regulatory judgment.

## License

[MIT License](LICENSE) — Copyright 2026 Thiago Guimarães Gruber.
