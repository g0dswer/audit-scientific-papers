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
tests, and validate the skill. Install it as a managed copy without `.git` metadata if
you want consent-based updates; keep `.git` only for a developer checkout. Then use Audit
Scientific Papers to audit this study:

[PASTE DOI OR URL, OR ATTACH THE PAPER]
```

If your interface supports skill mentions, select `@Audit Scientific Papers`. In Codex,
the installed skill may be invoked as `$audit-scientific-papers`.

## Stable updates

The skill checks the repository's latest published, non-prerelease GitHub release once at
the beginning of an audit. If a newer semantic version is available, it shows the installed
and available versions, exact release commit, release summary, material changes, and
release link, then asks whether to update before proceeding. It never interprets an audit
request as permission to update and never silently replaces local files.

After consent, the bundled updater verifies that the approved version and commit have not
changed, downloads that exact commit into temporary storage, rejects unsafe archive
entries, validates and revalidates the staged candidate, and installs it with an automatic
restore on ordinary activation failures. A successful update retains the previous version
for an explicit rollback, records its content digest, and verifies that digest before
restoring it.

The installer does not execute the downloaded test suite: downloaded Python would run with
the user's privileges and is not a security sandbox. Tests are a publishing gate for the
maintainer, while installation uses non-executing package validation. The updater trusts
the named GitHub repository; commit pinning prevents a release tag from changing after
consent, but it does not protect against compromise of the repository or maintainer account.
HTTPS certificate verification is never disabled. If a Python installation has no usable
default CA path, the updater may retry with an installed `certifi` bundle or a known
operating-system CA bundle while keeping hostname and certificate validation enabled.

Check manually with:

```bash
python3 scripts/check_for_update.py --json
```

Users who installed a version from before `v1.0.0` must reinstall once to bootstrap this
mechanism. After that, future stable releases are detected when the skill is invoked. A
network failure never blocks an audit, and a Git checkout is never replaced automatically.

### Publishing a stable version

Development commits on `main` are never offered directly. To publish an update:

1. choose the next semantic version and update both `VERSION` and
   `skill-manifest.json` in the same reviewed change;
2. update the manifest's summary, changes, publication date, tag, and minimum updater
   protocol when needed;
3. run `python3 -m unittest discover -s scripts -p 'test_*.py' -v` and validate the skill;
4. require the repository's test workflow to pass on the reviewed change;
5. merge the reviewed change, tag that exact merge commit as `v<version>`, and publish a
   non-draft, non-prerelease GitHub release whose publication date matches the manifest.

The checker resolves the release tag to a commit and the user's consent is bound to that
commit. If the release, tag, manifest, approval, or candidate identity is inconsistent, the
installed version remains active.

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

# Draw a forest plot of the reconstruction (dependency-free SVG)
python3 scripts/plot_forest.py meta_data.csv forest.svg \
  --analysis-id primary_pool \
  --common-measure HR

# Absolute effects for a two-arm binary outcome; state the event direction
python3 scripts/calculate_binary_effects.py 16 41 12 39 --harm --json

# Consistency checks on a published estimate and interval
python3 scripts/verify_continuous_result.py ci -4.04 -6.89 -1.18 --measure MD --json
python3 scripts/verify_continuous_result.py ci 0.75 0.60 0.94 --measure HR --json

# Check one extracted row without retyping its numbers or its measure
python3 scripts/verify_continuous_result.py row meta_data.csv STUDY_ID \
  --analysis-id primary_pool --json
```

Use `--allow-mixed-estimands` only when the published forest plot itself mixed native
ratio measures and the first step must reproduce that choice. It does not make the pooled
estimand scientifically valid. The source intervals are assumed to be 95% intervals by
default; use `--input-confidence`, or a per-row `input_confidence` column when a forest
plot mixes levels. `--confidence` controls the requested output interval without changing
the reconstructed study variances.

### Statistical conventions

- **Prediction intervals** use Student's t on **k − 2** degrees of freedom, the Cochrane
  Handbook and Higgins–Thompson–Spiegelhalter convention. Pass `--prediction-df k-1` for
  the model-degrees-of-freedom alternative that some software reports. Every output states
  which convention it used.
- **Prediction intervals always use the conventional inverse-variance standard error**,
  even under `--inference HKSJ`, so choosing HKSJ for the confidence interval does not
  silently widen the prediction interval.
- **`--model fixed` is honoured across the whole sensitivity ladder.** Rungs that are
  meaningful only for random effects report `NOT_ASSESSABLE` rather than publishing
  random-effects numbers under a fixed-effect heading.
- **Ratio measures must be analyzed on the log scale.** The continuous checker requires
  exactly one of `--measure {HR,RR,OR,IRR,RATIO,MD,SMD}` or `--scale {linear,ratio}`, with
  no default, because a hazard, odds, or risk ratio sent down the linear path gets a badly
  wrong p-value and a spurious interval asymmetry. Prefer `--measure`: it is the vocabulary
  the source and the extraction schema already use, so the scale follows from an audited
  field instead of a judgement call. Better still, `row` reads an extracted dataset and
  takes the effect, interval, measure, and interval level from the row itself, so nothing
  is retyped. A heuristic also warns when an input looks like an unlogged ratio, but it is
  a second net: it cannot detect a ratio close to the null with a narrow interval, which is
  exactly the shape of the largest cohort studies.
- **Event direction is explicit.** `calculate_binary_effects.py` takes `--harm` or
  `--benefit`; if neither is given it assumes a beneficial event and says so prominently,
  because the assumption inverts NNT and NNH labels.
- **Dependence guards fail closed.** An unrecognized `overlap_status` is a blocking error,
  not a value that quietly bypasses the overlap check.

The repository includes a versioned Naghshi 2020 fixture as a regression test. It checks
published reconstruction and cleaner provenance/common-measure scenarios without changing
study eligibility merely to force a target number.

## Optional Luna Max subagent

If you're in Codex, it is a good strategy to deploy Luna Max Subagents to do the data scrapping because it is so cheap and accurate.

Just prompt codex this:

```text
Create a Luna Max subagent following this:
create a file `~/.codex/agents/luna-worker.toml`:
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
