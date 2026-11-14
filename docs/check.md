# Check a PyPI package: who could release it alone?

`hrg check PACKAGE` looks at how a package on PyPI is published and answers three
questions, each with what to change:

1. Did the latest release go through a **second person** before it was published?
2. Does **one person** publish every release?
3. Can a reviewer who has **not been active** for months still approve a release alone?

```bash
pip install human-risk-graph
hrg check requests
hrg check my-package --show-people          # your own project: name the people
hrg check my-package --fail-on error        # in CI: exit code 3 on an error
hrg check my-package --format json
```

```
hrg check my-package 2.1.0 · acme/my-package

  Release path  V1  published through a reviewer gate one person can pass alone
  Configured    G1  a reviewer gate one person can pass alone
  Publishers    1 seen on GitHub in the last year
  Reviewers     2 on publishing environments, 1 inactive for over 90 days

  ▲ 1 reviewer(s) of a publishing environment, with no activity seen in the repository
    for over 90 days, can approve a release they start themselves.
    → Confirm each reviewer still needs the role, remove those who do not, and enable
      Prevent self-review.
  △ The latest release went through a reviewer gate (environment pypi) that one person
    can pass alone: reviewers can approve their own run, or administrators can bypass it.
    → On the publishing environment, require reviewers, enable Prevent self-review and
      turn off the administrator bypass.
  △ One person published every release seen on GitHub in the last year.
    → Give a second maintainer the ability to release, and document how.
```

The definitions are the ones of the
[two-person study](study-two-person.md), which measured them on the 1,000 most downloaded
PyPI packages.

## What it reads

Public data only, with your GitHub token if you have one (`GITHUB_TOKEN`, `GH_TOKEN`,
`gh auth token` or `--token`):

- **PyPI:** the package metadata (to find the GitHub repository) and the
  [provenance](https://peps.python.org/pep-0740/) of every file of the latest release,
  which says which repository, workflow and GitHub environment published it. Packages
  published with Trusted Publishing and attestations have it;
  `pypa/gh-action-pypi-publish` creates attestations by default.
- **GitHub:** the repository's deployment environments (required reviewers, Prevent
  self-review, administrator bypass), its releases and the deployments to publishing
  environments in the last year, and for each reviewer the latest activity seen: commits
  in the last 180 days, and pull requests and reviews among the 30 most recent merged pull
  requests (read only with a token, to stay within GitHub's limits).

When PyPI does not link to the repository, the one named by the provenance is used, or
pass `--repo OWNER/NAME`. On GitHub Enterprise Server, pass `--api-url`.

## Release path

From the provenance of every file of the latest release; the weakest file decides.

| Class | Meaning |
|---|---|
| V2 | every file published through an environment with a **two-person gate**: required reviewers, Prevent self-review on, no administrator bypass |
| V1 | through a reviewer gate one person can pass alone (self-approval or administrator bypass) |
| V0 | without a reviewer gate (an ungated environment, or none) |
| O | published by another repository or service: its gate is not checked |
| P | only some files have provenance: the others were uploaded another way, such as an API token |
| U | no provenance: how the release was published cannot be seen |

The **configured gate** is the strongest gate on any publishing environment (G2, G1, G0,
or NE for none). A G2 project whose latest release is V0, V1 or P has a gate its releases
do not take, which `hrg check` reports.

A publishing environment is one whose name contains `prod`, `live`, `release`, `publish`,
`pypi`, `npm`, `crates`, `rubygems`, `maven`, `nuget`, `docker` or `registry`.

## Findings

| Level | When |
|---|---|
| error | a reviewer of a publishing environment with no activity seen for over `--inactive-days` (default 90) can approve a release they start themselves |
| warning | the latest release is V1, V0 or P; a configured two-person gate was not used; an inactive reviewer; one person published every release seen on GitHub in the last year |
| note | the path is not observable (U) or belongs to another publisher (O) |
| ok | the latest release went through a two-person gate |

`--fail-on error` or `--fail-on warning` exits with code 3 when a finding has that level
or worse, for use in CI.

## People are not named by default

`hrg check` works on any public package, so its output could point an attacker at an
account: a reviewer who has not been seen for months and can approve their own release is
an easy target for takeover. By default it reports **what** is wrong and how to fix it,
with counts, and names nobody. `--show-people` adds the logins and when each was last
seen; it is meant for maintainers checking their own project. Nothing is stored or sent
anywhere.

## Limits

- **Activity is what the repository shows.** A reviewer can be active elsewhere; "no
  activity seen" is not "abandoned".
- **Settings are read now.** The environment settings in effect when the latest release
  was published are not visible; current settings stand in for them.
- **One release, one path.** A V2 release shows that the latest release went through a
  two-person gate, not that no other path (an API token, another workflow) exists.
- **GitHub only.** Publishers are seen through GitHub releases and deployments; PyPI does
  not publish who uploaded a file. Releases from GitLab or other CI show as O or U.
- **Team reviewers** are counted but not checked for activity: team members are not public.
