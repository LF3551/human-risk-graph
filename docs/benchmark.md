# Benchmark: does `hrg scan github` find the real approvers?

`hrg scan github` infers who approves whose work from pull request reviews. This benchmark
checks that inference against an independent source: the people each project **declares**
as approvers in its governance files (MAINTAINERS, OWNERS). The scanner does not read those
files, so the comparison is not circular.

Reproduce it with a GitHub token:

```bash
python benchmark/run.py --max-prs 100      # writes benchmark/results.json
```

The repositories and where their declared approvers come from are in
[benchmark/repos.yaml](../benchmark/repos.yaml); raw results, including per-person approval
counts, are in [benchmark/results.json](../benchmark/results.json).

## Metrics

For each repository, over its most recent merged pull requests (up to 100):

- **Precision**: share of people seen approving who are declared approvers.
- **Recall**: share of declared approvers seen approving at least once.
- **Approvals by declared**: share of all approving reviews given by declared approvers.
  This is the closest to what the model uses, since approval weight is proportional to the
  number of approvals.
- **Top approver declared**: whether the person with the most approvals is declared.
- **Release authors declared**: share of the people who published the last 30 GitHub
  releases (the `release` function of model hrg-3) who are declared approvers.

## Results

Run on 2026-11-13 with human-risk-graph 0.12.0, up to 100 merged pull requests per repository.

| Repository | PRs | Declared | Approvers | Precision | Recall | Approvals by declared | Top approver declared | Release authors declared | Reviews required |
|---|---:|---:|---:|---:|---:|---:|:---:|---:|:---:|
| prometheus/prometheus | 100 | 25 | 31 | 42% | 52% | 70% | yes | n/a | unknown |
| open-policy-agent/opa | 100 | 10 | 6 | 50% | 30% | 68% | yes | n/a | unknown |
| kyverno/kyverno | 100 | 10 | 10 | 50% | 50% | 54% | yes | 100% of 2 | yes |
| fluxcd/flux2 | 100 | 10 | 7 | 86% | 60% | 99% | yes | n/a | unknown |
| helm/helm | 42 | 10 | 12 | 67% | 80% | 93% | yes | 100% of 3 | yes |
| etcd-io/etcd | 83 | 7 | 9 | 56% | 71% | 96% | yes | 50% of 2 | unknown |
| cert-manager/cert-manager | 57 | 10 | 4 | 75% | 30% | 92% | yes | n/a | unknown |
| kubernetes-sigs/kustomize | 50 | 3 | 4 | 50% | 67% | 86% | yes | n/a | unknown |
| **All** | 632 | 85 | 83 | **54%** | **53%** | **82%** | | **86%** of 7 | |

Fewer than 100 pull requests means fewer were merged into the default branch among the
most recently updated closed ones (Prow-merged repositories close many without a merge).
"n/a" for release authors: the repository publishes no GitHub releases or publishes them
only through automation, which the draft reports as a coverage gap.

## What this shows

**The scanner finds who carries approval authority, weighted by activity.** 82% of all
approving reviews come from declared approvers, and in all 8 repositories the most active
approver is a declared one. In five of them, declared approvers give over 85% of approvals.

**Release authority is found too.** 6 of the 7 people who published releases are declared
approvers; the seventh published one etcd release.

**The benchmark caught a scanner error, now fixed.** The first 0.12.0 run matched only 60%
of release authors: `prombot`, `cert-manager-bot` and `jetstack-release-bot` are machine
users (ordinary accounts without the `[bot]` suffix of GitHub Apps) and were counted as
people. The scanner now treats accounts named like bots as automation, which also raised
flux2's recall from 30% to 60% because bot pull requests no longer fill the window.

**Person-level precision is moderate (54%) because anyone can approve on GitHub.** An
approving review from someone without merge rights is recorded like any other. In
prometheus, opa and kyverno, 30-46% of approving reviews come from people not on the
declared list. Some are likely area maintainers or members of teams named in CODEOWNERS
rather than in MAINTAINERS; others are contributors whose approval is not binding.

Filtering by the review's `author_association` does not fix this: GitHub reports hidden
organization members as `CONTRIBUTOR`, so a declared kyverno maintainer is indistinguishable
from an outside contributor. The draft therefore keeps these approvals, marked
`confirmed: false`, for a person to review, which is what the confirmation workflow is for.

**Recall is moderate (53%) because declared lists include inactive people.** In opa and
cert-manager, 7 of 10 declared approvers gave no approval in the window. This is not only
a scanner limit: authority on paper that is not exercised is itself a finding (who
actually approves is a smaller group than the governance file suggests).

**Review requirements are mostly not visible.** In six of eight repositories the default
branch is protected but its settings need admin access, so unreviewed merges are reported
as a coverage gap instead of a bypass. Every draft lists its gaps (2-5 per repository here,
including admins, who are visible only with push access).

## Limitations

- Declared lists are a proxy for ground truth: they can be outdated, and some repositories
  grant approval through teams or CODEOWNERS that the lists do not mention.
- Only GitHub approving reviews are counted. Prow-based repositories (etcd, cert-manager,
  kustomize) approve with `/approve` comments; their approvers appear here only when they
  also leave a GitHub review.
- One window of up to 100 pull requests per repository; results change over time, so the
  date and tool version are part of every run.
- The benchmark measures approval and release discovery. Bypass discovery and repository
  admins need admin-only data and are not measured on public repositories.
- Accounts are treated as bots by name (`[bot]` suffix, or a name ending in `bot` or
  containing `-bot-`); a person whose login ends in "bot" is skipped unless the scan runs
  with `--include-bots`.
