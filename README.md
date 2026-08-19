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

https://github.com/g0dswer/statistical-audit-scientific-papers

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

https://github.com/g0dswer/statistical-audit-scientific-papers

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

## Optional Luna Max subagent

If your Codex environment supports reusable custom subagents and `gpt-5.6-luna` is
available, create `~/.codex/agents/luna-worker.toml` with:

```toml
name = "luna_worker"
description = "Focused execution worker for clear, bounded delegated tasks with concise evidence-backed handoff."
model = "gpt-5.6-luna"
model_reasoning_effort = "max"

developer_instructions = """
Work only on the concrete task delegated by the parent agent.

- Confirm the task boundary from the prompt and do not expand into adjacent work.
- Inspect only the inputs needed to complete the assignment.
- Preserve unrelated user changes and settings. Never reset, clean, or rewrite unrelated work.
- When edits are authorized, touch only the assigned files and make the smallest defensible change.
- Do not commit, push, deploy, publish, message external parties, or perform destructive actions unless the delegated task explicitly authorizes that exact action.
- Do not spawn additional agents. Stop and report if the task requires broader scope, new authority, or unavailable input.
- Validate the result in proportion to the change, using targeted checks rather than broad unrelated work.
- Return a concise handoff containing: outcome, evidence or checks run, files changed, and any remaining caveats.
"""
```

The parent agent may delegate one clearly bounded audit module at a time to
`luna_worker`. Luna remains an optional execution worker: the parent must independently
verify important calculations and resolve disagreements. If custom agents or this model
are unavailable, the skill uses other independent agents or runs the same modules
sequentially.

See [the complete subagent protocol](references/subagent-protocol.md) for role prompts,
evidence boundaries, fallback behavior, and adjudication rules.

## Local validation

The calculation tools use Python 3. SciPy is optional and is used only when available
for the two-sided Fisher exact test.

```bash
git clone https://github.com/g0dswer/statistical-audit-scientific-papers.git
cd statistical-audit-scientific-papers
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
