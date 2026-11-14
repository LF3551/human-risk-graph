# Who can ship it alone? Two-person control and dormant authority over publishing in the most downloaded PyPI packages

Status: **protocol**, to be registered on OSF before any data in the sample is collected.
The protocol and the code that implements it, [benchmark/two_person.py](../benchmark/two_person.py)
with its tests in [tests/test_two_person.py](../tests/test_two_person.py), are fixed at the
git tag `two-person-protocol`; the OSF registration records that commit. Results are added
below the protocol without changing it, and any deviation is listed under "Deviations".

Author: Aleksei Aleinikov (ORCID 0009-0003-8866-3131).

## Background

Attacks on open-source supply chains often go through the person who can publish, not
through the code: a maintainer who handed a package to a stranger (event-stream, 2018), a
dormant maintainer account taken over and used to publish a malicious release (ctx on PyPI,
2022), a lone, overloaded maintainer whose trust was won over years to ship a backdoor
(xz-utils, 2024). Two controls address this: a second person who must approve a release
before it is published, and the removal of authority that nobody uses any more.

GitHub offers both for releases built in GitHub Actions. A *deployment environment* (for
example `pypi`) can require approval by named reviewers before a job that publishes runs,
can forbid reviewers from approving a run they started themselves (*prevent self-review*),
and can refuse administrators a bypass. These settings, the people who deployed and the
people who review code are public for public repositories. This study measures how often
the most downloaded Python packages use them, using the same definitions as
[Human Risk Graph](../README.md) 0.16.0 (model hrg-3).

## Research questions

- **RQ1 (two-person gate).** What share of projects published their latest release, as far
  as PyPI provenance shows, through a GitHub environment that enforces a two-person rule:
  required reviewers, no self-approval, no administrator bypass? And how does the path
  releases actually take compare with the environments projects have configured?
- **RQ2 (single publisher).** What share of projects had a single person publishing
  releases in the year before T0, among the publishing events visible on GitHub?
- **RQ3 (dormant authority).** Among projects whose publishing environment names
  reviewers, what share name a reviewer with no activity in the repository in the 90 days
  before T0? What share of all projects have such a dormant reviewer who could approve
  their own release (dormant solo authority)?
- **RQ4 (review concentration).** Among projects where code review is used, what share
  rely on one reviewer in practice, with fewer than two effective approvers?

The study is descriptive: it estimates proportions with confidence intervals and does not
test hypotheses. Expectations are stated below so that the results can be compared with
them, but they are not confirmatory tests.

## Design

Cross-sectional study of public GitHub data at a reference date **T0**: the UTC date on
which collection starts, at most 14 days after the registration. Inactivity, publishing
windows and the activity lookups are all measured relative to T0.

### Sampling frame

The 1,000 most downloaded PyPI packages in the 30 days before 2026-11-01, from
[hugovk/top-pypi-packages](https://github.com/hugovk/top-pypi-packages) at commit
`29c0d4c38c28c0e6b99e73fa09cb91a2323ca51b` (file `top-pypi-packages.min.json`, positions
1-1000). Each package is mapped to a GitHub repository through its PyPI metadata (first
`github.com/OWNER/REPO` link among Source, Source Code, Repository, Code, GitHub,
Homepage, then any other link, then the home page), with the function used in the first
study ([validation-hrg3.md](validation-hrg3.md)). Packages that map to the same repository
are counted once, under the highest-ranked package.

### Eligibility

A package is included when:

1. its PyPI metadata link to a GitHub repository;
2. it had at least one PyPI upload in the 365 days before T0;
3. the repository is reachable through the GitHub API and not archived;
4. it is the highest-ranked package of its repository.

Every package in the frame is listed with its exclusion reason in the private data
(see Publication).

### Measures

All measures are defined in `benchmark/two_person.py`; the function names are given.

**Publishing environment** (`is_publishing`): a GitHub deployment environment whose name
contains `prod`, `live`, `release`, `publish`, `pypi`, `npm`, `crates`, `rubygems`,
`maven`, `nuget`, `docker` or `registry` (case-insensitive), the rule of
`hrg scan github` 0.16.0.

**Gate of an environment** (`environment_gate`): *gated* when it has a required-reviewers
rule naming at least one user or team (bots are not counted); a *two-person gate* when it
is gated, prevents self-review, and does not allow administrators to bypass its rules.

**RQ1, path of the latest release** (`latest_release`, `release_path`). The latest
release is the PyPI version whose last non-yanked upload before T0 is the most recent.
For every one of its files the study reads the PyPI provenance
([PEP 740](https://peps.python.org/pep-0740/), `https://pypi.org/integrity/...`), which
exists for files uploaded through Trusted Publishing with attestations and names the
publisher: kind, repository, workflow and environment. The repository is read from
`repository`, the field PyPI's integrity API returns, or from `repository_owner` and
`repository_name`, the form of PEP 740's example (`publisher_repository`); environment
names are compared case-insensitively. The release gets the class of its weakest file:

| Class | Meaning |
|---|---|
| V2 | every file attested by this repository through an environment with a two-person gate |
| V1 | every file attested through gated environments, at least one allowing self-approval or administrator bypass |
| V0 | every file attested, at least one through an ungated environment or without one |
| O | attested by another publisher (another repository, or not GitHub) |
| P | only some files attested |
| U | no file attested: the path is not observable |

**Primary outcome: the share of projects whose latest release was not observed passing
through a two-person gate (not V2).** It is a statement about what can be observed, not
that publishing is unprotected: P and U releases can be uploaded under controls this
study cannot see, and a V2 release shows that the latest release took a gated path, not
that no other path (an API token, another workflow) exists.

**RQ1, configured gate** (`publish_gate`), from the environments alone, one of four
classes:

| Class | Meaning |
|---|---|
| G2 | at least one publishing environment with a two-person gate |
| G1 | a gated publishing environment, but self-approval or administrator bypass is allowed |
| G0 | publishing environments, none gated |
| NE | no publishing environment visible |

Secondary outcomes: the share of projects not in G2, and the cross-tabulation of the
configured gate by the path of the latest release, which shows projects that configure a
gate their releases do not take.

**RQ2, human publishers seen on GitHub** (`human_publishers`): the people, not bots, who published a
non-draft GitHub release (among the 100 most recent) or created a deployment to a
publishing environment (among its 100 most recent) in the 365 days before T0. Primary
outcome: share of projects with exactly one human publisher, among projects with at least
one. PyPI does not publish who uploaded a file, and the person who creates a GitHub
release or deployment is not necessarily the one whose credentials upload it; the outcome
is about publishing events visible on GitHub only.

**RQ3, dormant reviewers.** For each user (not team) named as a required reviewer of a
gated publishing environment, the last activity seen in the repository before T0: the
latest of their merged pull requests and reviews (among the pull requests read for RQ4),
GitHub releases, deployments to publishing environments, and their most recent commit on
the default branch in the 180 days before T0 (`commits?author=`). *Dormant*
(`is_dormant`): no such activity in the 90 days before T0. Primary outcomes:

- among projects in G1 or G2 with at least one user reviewer, the share with at least one
  dormant reviewer;
- among all included projects, the share with **dormant solo authority**: a dormant
  reviewer of a gated publishing environment that allows self-approval.

Projects whose publishing environments name only teams are counted and reported
separately: team members are not public.

**RQ4, review concentration.** The 50 most recent pull requests merged into the default
branch whose author is not a bot (found among the 300 most recently updated closed pull
requests), and for each the people other than the author, not bots, who approved it.
Effective approvers (`effective_approvers`): 1 / Σ sᵢ², where sᵢ is reviewer i's share of
approvals. An approval counts when it stood (`standing_approvals`): the reviewer's latest
review that changes the state is an approval; a later request for changes or a dismissed
approval withdraws it, a comment does not. *Single reviewer in practice*: fewer than 2 effective approvers, the HRG002
error threshold. Primary outcome: share of projects with a single reviewer in practice,
among projects with at least 10 approved pull requests in the 50. Secondary: the same
share among those whose default branch visibly requires an approving review (a ruleset
`pull_request` rule with `required_approving_review_count` ≥ 1).

### Analyses

1. Each primary outcome as a proportion with a Wilson score 95% interval (`wilson`).
2. RQ1: the distribution over the path classes, the distribution over G2, G1, G0 and NE,
   the configured gate by path, and the median age of the latest release at T0.
3. Sensitivity, labelled as such: RQ1 with every gated environment counted as publishing
   whatever its name (`publish_gate(any_name=True)`); RQ3 with a 180-day threshold.
4. Exploratory, labelled as such: RQ1 and RQ2 by owner type (organization or user account)
   and by rank (1-100, 101-1000); for RQ4, the median share of the 50 merged pull requests
   without an approval by someone else, among the projects of the secondary RQ4 outcome
   (at least 10 approved pull requests and a visible review requirement).

There is no hypothesis test and no correction for multiplicity. With about 750 included
projects, an interval is at most about ±3.6 percentage points wide.

**Interpreting the intervals.** The frame is the fixed, non-random set of the most
downloaded packages, not a sample from a defined population. The intervals describe the
sampling variability the proportions would have if these projects were a sample from a
population of similar packages; they do not account for measurement or classification
error, nor for how far the results generalize beyond the frame.

**Measurement check.** To estimate classification error, 40 included projects drawn at
random with a fixed seed (`measurement_sample`, seed 20261114) are checked by hand after
collection: their release workflows, environment settings and the PyPI provenance of the
latest release are read and compared with the recorded publish path, configured gate and
reviewer status. The report gives the share of projects whose classes agree, and describes
every disagreement. The data are not corrected after the check.

### Expectations

Stated before the data, from experience rather than evidence, to be compared with the
results and not tested: V2 for under 5% of projects; U the largest path class; G2 under
10% of projects and NE the largest configured class; a single human publisher in more
than a third of the projects with any; dormant solo authority in fewer than 5% of
projects. Results are reported in full whether or not they match.

### What the author saw before registration

While developing `hrg scan github` 0.16.0 the author read the environments, reviewers and
deployments of a few repositories (pypa/pip, astral-sh/uv, vercel/next.js, cli/cli and
others), some of which are in the frame. A pilot of the code ran on frame positions
1001-1010, outside the sample, to check that it works and to measure the API cost
(about 55 calls per repository). It showed that one page of 100 closed pull requests can
hold only a few merged pull requests by people, and the code was changed to read up to
300. After a review of a draft of this protocol, the path of the latest release
from PyPI provenance, the measurement check and the wording rules were added, and the
pilot was run again on the same positions. While checking a second review, which
pointed to the field names of PEP 740's example, the author looked at the provenance of
the latest release of a few packages in the frame to see which fields PyPI returns: the
publisher of pip (environment `pypi`) and requests (environment `publish`), and only the
field names for urllib3, attrs, idna, certifi and pydantic-core (which has no provenance).
The review also led to reading every file of a release, to the rule for withdrawn
approvals and to the limitation on settings over time. No other data from positions
1-1000 was collected.

### Data collection

`python benchmark/two_person.py --t0 YYYY-MM-DD` with a GitHub token of an account that
has no push access to the sampled repositories, so that every project is seen the same way
(as by the public). API responses are cached under `benchmark/.cache/` so that a run can
resume; a rate limit makes it wait, never record missing data. GitHub data can change
during collection; the cached responses are the data the results are computed from.

### Limitations known in advance

- **Visibility.** Classic branch protection, administrators and team members are not
  public. Projects can publish under controls this study cannot see (NE), and reviewers
  named through teams cannot be assessed.
- **Name rule.** Environments are classified by name; the sensitivity analysis counts
  every gated environment.
- **Activity is a proxy.** A reviewer can be active elsewhere (other repositories, the
  issue tracker, chat) and still reachable; "dormant" means no activity seen in this
  repository, not that the account is abandoned.
- **Publishers.** PyPI does not publish uploader identities; RQ2 sees GitHub releases and
  deployments only.
- **Settings over time.** Environment settings are read at T0, but the latest release can
  be months older. Current settings are used as a proxy for the settings in effect when it
  was published; historical changes are not observable. The median age of the latest
  release is reported to show how large the gap is.
- **Provenance.** Attestations exist only for files uploaded through Trusted Publishing
  with attestations; older uploads and uploads with API tokens have none (class U), and
  provenance says nothing about other paths a project could use.
- **Mapping.** Packages whose PyPI metadata do not link to GitHub are excluded, and a
  link can point to a different repository than the one that publishes.
- **Sample.** The most downloaded PyPI packages are not a random sample of open-source
  software, and T0 is one point in time.

## Reporting rules

The report uses the operational definitions, not stronger words:

- "not observed passing through a two-person gate", not "unprotected";
- "publishers seen on GitHub", not "the people who upload to PyPI";
- a reviewer "with no activity seen in this repository for 90 days", not an "abandoned"
  or "compromised" account; "dormant" is always given with that definition;
- intervals with the caveats under Analyses.

## Publication and disclosure

The findings concern specific accounts that could be targeted, so the study publishes
aggregates only.

- **Published:** this protocol, the code and its tests, `benchmark/two-person/results.json`
  (aggregate counts and intervals only) and a report of the results.
- **Not published:** per-repository rows (written to `benchmark/.private/`, not committed)
  and the API cache. Logins are used only to compute the measures and never appear in
  published output. Both are deleted 90 days after the report is published. A project's
  maintainers can ask for their own row.
- **Disclosure.** Every project with dormant solo authority (RQ3) is told privately at
  least 30 days before the report is published: through GitHub private vulnerability
  reporting when it is enabled, otherwise through the contact in its security policy;
  projects without either are not contacted, and no public issue is opened. The message
  names the environment and the reviewer concerned and nothing else, explains the risk,
  and suggests confirming whether the reviewer still needs the role and enabling prevent
  self-review. Disclosure does not change the data: projects are measured at T0.

## Deviations

Any change after registration is listed here with its reason and its effect on the
results.

---

## Results

Registered on OSF on 2026-11-14 at 11:09 UTC, before data collection:
[doi:10.17605/OSF.IO/J8ZFG](https://doi.org/10.17605/OSF.IO/J8ZFG), with this protocol
(SHA-256 `b432b2cb…3ccfb`) and the code at tag `two-person-protocol`. Data collection
started on 2026-11-14 (T0 = 2026-11-14).

Results are added here after the run.
