# Does a single releaser predict a release stall? A predictive check of hrg-3

Status: **protocol**, fixed before any outcome data was collected. The protocol, the code
in [benchmark/validate.py](../benchmark/validate.py) and its tests are committed before the
first run; the results are added below it without changing the protocol. Any deviation is
listed under "Deviations".

## Question

hrg-3 says a function with margin 1 stops when one person is unavailable. If that means
anything outside the model, open-source projects whose releases were published by a single
person should, later, stop releasing more often than projects with two or more release
authors. This is a prediction made from data before a fixed date and checked against what
happened after it, not a case picked in hindsight.

It tests one function (publish a release), as `hrg scan github` drafts it. It does not test
merge, admin, solo control, or hand-written functions.

## Design

Retrospective cohort with a fixed index date **T0 = 2024-11-01**.

- **Predictor window** W = [T0 − 730 days, T0).
- **Outcome window** O = [T0, T0 + 365 days), fully observed by the time of the run.

### Sampling frame

The 1,000 most downloaded PyPI packages over the 30 days before T0, from
[hugovk/top-pypi-packages](https://github.com/hugovk/top-pypi-packages) at commit
`9a7168eafc044ad06176f08dfb91405ca6f155b8` (2024-11-01), so the frame does not depend on
which projects are still popular today. Each package is mapped to a GitHub repository
through its PyPI `project_urls` (first `github.com/OWNER/REPO` link among Source,
Repository, Code, Homepage, then any other key). Packages that map to the same repository
are counted once, under the highest-ranked package.

### Eligibility (pre-T0 data only)

- The repository is reachable through the GitHub API.
- At least 3 non-draft GitHub releases published in W.
- People, not bots, published at least half of the last 30 releases in W
  (`hrg scan github` bot rules: `[bot]` accounts and logins ending in `bot` or containing
  `-bot-`/`_bot_`). When automation publishes most releases, who can trigger it is not
  visible, and `hrg scan github` reports it as a gap.

### Exposure (hrg-3)

The release function as `hrg scan github` drafts it, computed as of T0: performers are the
people who published the last 30 non-draft GitHub releases in W, `requires: 1`, no `alone`.
Its margin is the number of performers. **Exposed: margin 1** (single releaser);
unexposed: margin ≥ 2. Unlike the scan, which reads the last 30 releases whatever their
age, only releases in W count, so someone who last released years before T0 does not
count as a second performer.

### Baseline exposure (commit concentration)

A simplified truck factor from commit authorship: the smallest number of people who
authored more than half of the human-authored commits on the default branch in the
12 months before T0 (up to the 500 most recent commits; commits without a linked GitHub
account are left out). **Exposed: truck factor 1.** This is a commit-share approximation,
not the file-level degree-of-authorship algorithm of Avelino et al. (ICPC 2016).

### Outcomes

- **Primary: release stall.** No release of the project in O: no PyPI upload of the
  package and no non-draft GitHub release.
- **Secondary: long gap.** The first release after T0 (PyPI or GitHub) comes more than
  180 days after T0, or not at all within O.

### Analyses

1. **H1.** Risk ratio of a stall, margin 1 vs margin ≥ 2, with a 95% confidence interval
   (Katz log method; 0.5 added to every cell when one is zero) and a two-sided Fisher exact
   test.
2. **H2 (confounding by size).** Mantel-Haenszel risk ratio for margin 1, stratified by
   terciles of the number of GitHub releases in W, with the Greenland-Robins variance.
   Small projects may both have one releaser and stall more; the stratified ratio separates
   the two.
3. **Baseline.** The same risk ratio for truck factor 1 vs ≥ 2.
4. **Added information.** The risk ratio for margin 1 among projects with truck factor
   ≥ 2, where commit concentration does not flag the project.
5. The same analyses for the secondary outcome, labelled exploratory.

H1 is supported when the risk ratio is above 1 and its confidence interval excludes 1.
Results are reported whatever their direction. α = 0.05, no correction for the secondary
analyses, which are exploratory.

### Pilot

Before this protocol was committed, collection was run on the first 3 packages of the frame,
printing predictors and exclusion reasons only, no outcomes. It showed that releases
published by a release bot with one human release among them gave margin 1, and that
releases from long before T0 could add a departed person as a second performer; the
eligibility rule on automation and the window limit on release authors were added then.

### Data and reproducibility

`python benchmark/validate.py` collects the data (GitHub REST API, PyPI JSON API), writes
one row per repository to `benchmark/validation/data.csv` with the exclusion reason for
excluded ones, and the analyses to `benchmark/validation/results.json`. API responses are
cached under `benchmark/.cache/` so a run can resume. GitHub data can change after the
fact (deleted releases, renamed accounts), so a rerun can differ slightly; the published
CSV is the data the results were computed from.

### Limitations known in advance

- One function, and only GitHub releases as its evidence. Projects that publish from CI
  under a bot account are excluded, because who can trigger the release is not visible.
- A stall is a proxy: a project can stop releasing because it is finished, not because
  someone left; a single releaser can also be the only maintainer, so the predictor is
  confounded with project size, which analysis 2 addresses only partly.
- Popular PyPI packages are not a random sample of software, let alone of organizations.
- The outcome does not distinguish a planned handover from a loss.

---

## Results (run of 2026-11-13, hrg 0.14.0)

Everything above this line is the protocol as committed in d8514d4 before the data was
collected. Data: [benchmark/validation/data.csv](../benchmark/validation/data.csv), one
row per package; analyses: [benchmark/validation/results.json](../benchmark/validation/results.json).

### Sample

Of the 1,000 packages, **284 repositories** were included.

| Excluded | Packages |
|---|---:|
| Fewer than 3 GitHub releases in W | 303 |
| Same repository as a higher-ranked package (monorepos such as Azure SDK, Google Cloud) | 202 |
| No release by a person | 90 |
| No GitHub repository in the PyPI metadata | 86 |
| Releases mainly published by automation | 34 |
| Repository not reachable | 1 |

192 of the 284 (68%) had a single releaser in W. 33 projects (12%) published no release
in the 12 months after T0.

### Primary outcome: release stall

| Analysis | Exposed | Unexposed | Risk ratio (95% CI) | p |
|---|---|---|---|---|
| **H1** single releaser vs two or more | 30 / 192 (15.6%) | 3 / 92 (3.3%) | **4.79 (1.50–15.29)** | 0.0014 |
| **H2** H1 stratified by release count (Mantel-Haenszel) | | | 2.66 (0.77–9.18) | |
| Baseline: commit truck factor 1 vs ≥ 2 | 23 / 178 (12.9%) | 7 / 103 (6.8%) | 1.90 (0.85–4.28) | 0.16 |
| Single releaser, among projects with truck factor ≥ 2 | 5 / 42 (11.9%) | 2 / 61 (3.3%) | 3.63 (0.74–17.84) | 0.12 |

Strata of H2 (releases in W, by tercile): low 20/69 vs 1/10, middle 10/77 vs 1/32, high
0/46 vs 1/50.

### Secondary outcome (exploratory): first release more than 180 days after T0

| Analysis | Exposed | Unexposed | Risk ratio (95% CI) | p |
|---|---|---|---|---|
| Single releaser vs two or more | 61 / 192 (31.8%) | 12 / 92 (13.0%) | 2.44 (1.38–4.29) | 0.0008 |
| Stratified by release count | | | 1.39 (0.82–2.37) | |
| Baseline: commit truck factor 1 | 52 / 178 (29.2%) | 18 / 103 (17.5%) | 1.67 (1.04–2.70) | 0.032 |
| Single releaser, truck factor ≥ 2 | 11 / 42 (26.2%) | 7 / 61 (11.5%) | 2.28 (0.96–5.41) | 0.067 |

### Interpretation

- **H1 is supported.** Projects whose releases were published by one person before T0
  stopped releasing in the following year almost five times as often as projects with two
  or more release authors, and the interval excludes 1.
- **H2 is not established.** Stratified by how many releases a project published, the risk
  ratio stays above 1 (2.66) but the interval includes 1. Part of the crude effect is
  project activity: projects that release rarely both have one releaser more often and
  stall more often. The study cannot separate the two with 33 stalls; most of the
  information sits in the low-activity stratum, where only 10 projects had two releasers.
- **The release margin was a stronger signal than commit concentration** (4.79 vs 1.90 on
  the primary outcome; only the release margin's interval excludes 1). Among projects that
  commit concentration does not flag, a single releaser still went with a higher stall
  rate (3.63), but with 103 projects the interval is wide. This is consistent with HRG
  adding information beyond a commit-based truck factor, not proof of it.

In short: the hrg-3 release function, computed from data before T0, predicted which
popular Python projects would stop releasing, better than a commit-based truck factor; how
much of that is the single person rather than low activity is not settled by this sample.

### Deviations from the protocol

None. The pilot changes are part of the committed protocol.

### Next

- A larger frame (the top 5,000 packages) for the stratified analysis, under a new protocol
  committed before its data is collected.
- The same design for the merge function and for bypasses of a required review.
