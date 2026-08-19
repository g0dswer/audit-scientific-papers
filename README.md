# Audit Scientific Papers

A reusable skill for rigorous, source-backed appraisal of clinical studies, systematic
reviews, and meta-analyses.

Give it a paper, link, DOI, or uploaded file. The skill guides ChatGPT or another LLM provider through the article's supplements,protocol or registration history, statistical analysis plan, peer-review material, code, data, and other public evidence before judging the claims. 

Works on ChatGPT, Claude Anthropic and Grok, did NOT work(for me) on Gemini.

Providers i recommnend because the output was more rigorous and reliable: OpenAI(better on Work mode or Codex) or Anthropic(better on Cowork, Code or Science).

## What it does

- builds a dated evidence manifest instead of relying on the article alone;
- searches trial and review registries, protocols, supplements, code, and data;
- reconstructs headline statistical results when the public inputs permit it;
- audits missing data, exclusions, multiplicity, selective reporting, spin, and p-hacking
  signals without inferring misconduct from weak evidence;
- assesses result-level risk of bias, clinical importance, safety, and external validity;
- calculates absolute effects and number needed to treat or harm only when valid binary
  data support them;
- audits meta-analysis searches, row-level provenance, mixed effect measures, duplicate
  cohorts, heterogeneity, prediction intervals, and influence;
- runs fixed-effect and random-effects aggregate meta-analysis using
  DerSimonian–Laird, Paule–Mandel, or restricted maximum likelihood, with conventional or
  Hartung–Knapp–Sidik–Jonkman inference;
- ends with a concrete reanalysis recommendation: feasible now, feasible with specified
  additional data, or not quantitatively defensible with a better alternative.

## Use it in ChatGPT, Work mode or Codex

Paste this prompt:

```text
Install or import the Audit Scientific Papers skill from:
https://github.com/g0dswer/audit-scientific-papers

Read SKILL.md and every referenced file, preserve the repository structure, run all
tests, and validate the skill. Then use Audit Scientific Papers to audit this study:

[PASTE DOI OR URL, OR ATTACH THE PAPER]
```

If your interface supports skill mentions, select `@Audit Scientific Papers`. In Codex,
the installed skill may be invoked as `$audit-scientific-papers`.

If personal skill installation is unavailable, paste this instead:

```text
Open https://github.com/g0dswer/audit-scientific-papers

Use SKILL.md and all referenced files from this repository as the mandatory audit
protocol for the following study:

[PASTE THE LINK, DOI, OR ATTACH THE FILE]
```

## Use it in Claude(Cowork, Code or Science)

If you're a Claude Code user click here on the repo in CODE(green) then Download ZIP.

Now in Claude Code click in Customize on the top left, go to Skills, click Add then Upload a skill.

Then you select the ZIP file you downloaded.

Now just paste this prompt:

```text
  /audit-scientific-papers 
  
  [PASTE THE LINK, DOI, OR ATTACH THE FILE]
```  

## Expected report

The report contains:

1. a calibrated verdict;
2. study design and exact estimand;
3. source manifest and prespecification timeline;
4. independent numerical reconstruction where possible;
5. clinical importance, absolute effects, and valid number needed to treat or harm;
6. result-level risk of bias;
7. selective-reporting and p-hacking evidence, including counterevidence;
8. safety, external validity, spin, and reproducibility limits;
9. supported, uncertain, and unsupported claims;
10. a specific reanalysis recommendation;
11. direct links to the evidence used.

For meta-analyses it also reports row provenance, effect-measure compatibility, cohort
overlap, alternative random-effects models, Hartung–Knapp–Sidik–Jonkman intervals,
prediction intervals, leave-one-cohort-out influence, and conclusion robustness.

## Quantitative tools

The tools require Python 3 and use the standard library for the meta-analysis engine.
SciPy is optional and is used only for the binary calculator's Fisher exact test when
available.

```bash
git clone https://github.com/g0dswer/audit-scientific-papers.git
cd audit-scientific-papers

# Run every test
python3 -m unittest discover -s scripts -p 'test_*.py' -v

# Validate a row-level meta-analysis dataset
python3 scripts/validate_meta_dataset.py meta_data.csv --json

# Reconstruct a published pool
python3 scripts/reconstruct_meta_analysis.py meta_data.csv \
  --analysis-id primary_pool \
  --tau2 DL \
  --expected-pooled 0.94 \
  --json

# Run the provenance and model sensitivity ladder
python3 scripts/reconstruct_meta_analysis.py meta_data.csv \
  --analysis-id primary_pool \
  --common-measure HR \
  --sensitivity all \
  --allow-mixed-estimands \
  --json
```

Use `--allow-mixed-estimands` only when the published forest plot itself mixed native
ratio measures and the first step must reproduce that choice. It does not make the pooled
estimand scientifically valid. The source intervals are assumed to be 95% intervals by
default; use `--input-confidence` when they are not. `--confidence` controls the requested
output interval without changing the reconstructed study variances.

The repository includes a versioned Naghshi 2020 fixture as a regression test. It checks
published reconstruction and cleaner provenance/common-measure scenarios without changing
study eligibility merely to force a target number.

## Optional Luna Max subagent

If Codex supports reusable custom subagents and `gpt-5.6-luna` is available, create
`~/.codex/agents/luna-worker.toml`:

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

Delegate only bounded modules. The parent agent must independently verify material numbers,
source dates, estimands, and disagreements. See
[the subagent protocol](references/subagent-protocol.md).

## Important limits

- Aggregate reconstruction cannot recover unavailable participant-level data, covariance,
  missing-data mechanisms, or undocumented models.
- A random-effects model does not make hazard ratios, risk ratios, and odds ratios the same
  estimand.
- A reconstructed unadjusted calculation is not automatically equivalent to a published
  adjusted model.
- Multiplicity or a late analysis plan can raise concern but does not prove intentional
  p-hacking or misconduct.
- This tool supports critical appraisal; it does not replace clinical, statistical,
  regulatory, or domain judgment.

## License

[MIT License](LICENSE) — Copyright 2026 - Thiago Guimarães Gruber.
