# Model hrg-3: critical functions and the two-person rule (experimental)

hrg-2 measures how people are **connected**: a key person is one whose absence disconnects
the others. Connection is not replaceability: two people can be connected by an escalation
while only one of them can restore the database. hrg-3 asks the question directly, for each
thing the organization must be able to do:

1. **Who can do it, and what stops if one of them is unavailable?** (availability)
2. **Can one person complete it alone?** (integrity, the two-person rule)

The second question is the one [SLSA Source Level 4](https://slsa.dev/spec/v1.2/source-requirements)
asks of source changes ("two-party review"), and the one ISO/IEC 27001 A.5.3 (segregation of
duties) and DORA Art. 9(4) ask of privileged operations. hrg-3 is experimental: its
definitions may change in minor releases; hrg-2 remains the default model.

Use it with `hrg analyze FILE --model hrg-3`, or `model = "hrg-3"` in `hrg.toml`.

## 1. Functions

A function f has

- a **criticality** $c_f \in [0, 1]$ (default 0.5),
- the number of people it **requires**, $r_f \geq 1$ (default 1; 2 for a two-person rule),
- its **performers** $P_f$: people trained and authorized to do it,
- the people who can complete it **alone** $A_f \subseteq P_f$ despite $r_f$, for example an
  admin who can bypass branch protection,
- its **separation** policy: `required` (default) when one person completing it alone is a
  risk, `not-required` when that is the intended way to work, for example a database
  restore by the on-call engineer.

```yaml
functions:
  - id: release
    name: Publish a release
    criticality: 0.9
    requires: 1
    performers: [alice, bob]
  - id: merge
    name: Merge to main
    criticality: 0.8
    requires: 2
    performers: [alice, bob, carol]
    alone: [alice]
```

`hrg scan github` drafts these functions from a repository: **merge** (who approves or
merges; requires 2 when the branch requires reviews, with anyone who can merge without a
second person in `alone`), **release** (who published the last 30 GitHub releases),
**admin** (repository admins, when visible) and one **deploy** function per deployment
environment (below). Like dependencies, they are written with
`source`, `evidence` and `confirmed: false`. With `hrg scan github --org ORG` they are drafted
for every scanned repository and named after it (`payments-api/release`), so a person who is
the only releaser of several services is a single point of every one of them. Other
functions (restore the database, rotate signing keys, grant production access) are added by
hand.

### Deploy functions from GitHub Environments

A deployment environment with required reviewers is a two-person rule for deploying: one
person starts the deployment and one of the reviewers approves it. `deploy-<environment>`
is drafted with `requires: 2`; its performers are the reviewers (team members when the team
is visible, otherwise the team as one node) and the people who created the last 30
deployments. In `alone`:

- the reviewers, unless the environment has *Prevent self-review*: they can approve their
  own deployments;
- the repository admins, when *Allow administrators to bypass configured protection rules*
  is on (the default) and the admins are visible.

Environments without required reviewers are drafted only when their name looks like a
production or publishing target (`prod`, `live`, `release`, `publish`, `pypi`, `npm`,
`crates`, `rubygems`, `maven`, `nuget`, `docker`, `registry`): `requires: 1`, performed by
the people who deployed recently, since whoever can run the workflow deploys alone.
Production-like environments get criticality 0.9, other protected ones 0.7. Deployments
created by bots are not counted as people.

### Last activity

People who hold authority over a function can carry `last_active`, the date they were last
seen active, or `never`. The scan sets it for performers from the latest merged pull
request, approval, release or deployment it read, and looks up the person's last commit on
the branch when that is missing or more than 30 days old (at most 30 lookups per
repository). `hrg scan github --no-activity` records nothing. People without `last_active`
are of unknown activity and are never reported as inactive.

## 2. Definitions

The people who can complete f without anyone else are

$$\text{Solo}(f) = \begin{cases} P_f & r_f \le 1 \\ A_f & r_f \ge 2 \end{cases}$$

f **can be performed** without the people in a set X when at least $r_f$ performers remain
or someone in $A_f$ remains:

$$|P_f \setminus X| \ge r_f \quad\lor\quad A_f \setminus X \neq \emptyset$$

The **margin** of f is the smallest number of people whose absence stops it:

$$m_f = \max\left(0,\ |P_f| - r_f + 1,\ |A_f|\right)$$

$m_f = 0$: f cannot be performed at all. $m_f = 1$: some single person stops it; those
people are its **single points**.

## 3. Metrics

Let $C = \sum_f c_f$, $U$ the functions with $m_f = 0$, and F the **critical** functions,
$c_f \geq \theta$ (the critical threshold, 0.7 by default).

**Function loss L.** For a person p, the weight lost when p is unavailable is

$$\ell(p) = \frac{1}{C}\left(\sum_{f \in U} c_f + \sum_{f:\ m_f = 1,\ \text{f stops without p}} c_f\right)$$

and $L = \max_p \ell(p)$, or $\sum_{f \in U} c_f / C$ when nobody is a single point.

**Authority concentration D.** Each function's criticality is split equally among its
performers, $w_p = \sum_{f \ni p} c_f / |P_f|$, and D is the Herfindahl-Hirschman index of
the shares $s_p = w_p / \sum_q w_q$:

$$D = \sum_p s_p^2, \qquad N_{\text{eff}} = 1/D \text{ effective people}$$

**Solo control S.** The weighted share of critical functions that require separation and
someone can complete alone. With $F_s \subseteq F$ the critical functions whose separation
is `required`:

$$S = \frac{\sum_{f \in F_s,\ \text{Solo}(f) \neq \emptyset} c_f}{\sum_{f \in F_s} c_f}, \qquad S = 0 \text{ when } F_s = \emptyset$$

Functions with separation `not-required` are left out of S altogether, numerator and
denominator: a routine single-person operation is not a control failure, and declaring one
cannot dilute the solo control of the others. They still count for L and D, so a restore
only one person can do is still a single point of failure.

**Score.** The metrics are combined exactly as in hrg-2, with the same weights
(`[weights]` key-person → L, concentration → D, override → S):

$$R = \frac{1 - (1 - \alpha L)(1 - \beta D)(1 - \gamma S)}{1 - (1 - \alpha)(1 - \beta)(1 - \gamma)}, \qquad \text{score} = \text{round}(100(1 - R))$$

Reports also give two sub-scores: **availability**, the same formula with L and D only, and
**integrity**, $\text{round}(100(1 - S))$. A team can be resilient and still let one person
ship alone, or the other way round; the sub-scores keep the two apart.

## 4. Findings

| Rule | When | Level |
|---|---|---|
| HRG005 Function depends on too few people | $m_f \le 1$ | error if f is critical, else warning |
| HRG006 Critical function one person can complete alone | $f \in F_s$ and $\text{Solo}(f) \neq \emptyset$ | warning |
| HRG007 Function relies on inactive people | a performer's `last_active` is older than `inactive-days` (default 90) or `never` | error if f is critical and its margin among active people is 0, or an inactive person is in $\text{Solo}(f)$ for $f \in F_s$; else warning |
| HRG002 Concentrated authority | $D \geq 0.25$ (error from 0.5) | |
| HRG004 Risk above threshold | `--min-score` / `--fail-above` | error |

Findings on functions can be accepted in `hrg.toml` with `target = "<function id>"`.

HRG007 does not change the score: the metrics use the performers as declared, so the score
of a file does not change from one day to the next. The finding gives the margin among
active people, $m_f$ computed without the inactive performers, next to the declared one.
An inactive account that can complete a critical function alone is an error even when the
function has margin to spare, because a dormant account with that authority is an easy
target for takeover.

## 5. Fix plan

Greedy, like hrg-2: simulate each remediation, apply the one that lowers R the most, repeat.

- **Backup** for a function with $m_f \le 1$: one more trained and authorized performer.
- **Two-person rule** for a critical function someone can complete alone:
  $r_f \leftarrow \max(2, r_f)$ and $A_f \leftarrow \emptyset$. With fewer than two performers
  this makes the function impossible, so the plan only proposes it when it lowers R.

As in hrg-2, the plan shows which structural changes improve the model, not that they are
feasible: a backup only helps if the person has the skills, the access and the time.

## 6. Properties checked by the test suite

- L, D, S, R ∈ [0, 1]; the score is in [0, 100].
- Adding a performer to every function never increases L.
- Removing every `alone` entry never increases S.
- Adding a function with separation `not-required` never changes S.
- Raising `requires` never decreases L.
- Fix plan steps only lower R.
- Relabelling people does not change the score.
- Reference scenarios: one person doing a function alone (L = D = S = 1, score 0); two
  performers without a two-person rule (L = 0, S = 1); a two-person rule with exactly two
  people (L = 1, S = 0); a two-person rule with a bypass (S = 1); a sole maintainer who
  can bypass review (margin 1, not impossible); a routine single-person operation with
  separation `not-required` (S = 0, still a single point of failure).

## 7. What it does not do

- **Attack paths.** S asks whether one person can complete a function, not which accounts
  an attacker can reach from a compromised one; for that, use
  [BloodHound](https://github.com/SpecterOps/BloodHound) and its GitHub and GCP collectors.
- **Skills.** Performers are whoever you list; the scan sees authority and activity, not
  competence.
- **Dependencies.** hrg-3 scores functions only; the dependency graph is still drawn in the
  HTML report and still analyzed by hrg-2.

On 8 public CNCF repositories, 6 of the 7 people the scan found publishing releases are
declared maintainers ([benchmark](benchmark.md)).
