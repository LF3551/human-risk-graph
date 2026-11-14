# Human Risk Graph (HRG) — Formal Model

## 1. Introduction

Human Risk Graph (HRG) is a graph-theoretic model for quantifying organizational security risk arising from human dependencies, decision concentration, and emergency bypass mechanisms. Unlike traditional security models focused solely on technical vulnerabilities, HRG treats people as components of the attack surface.

## 2. Formal Definitions

### Definition 1: Human Risk Graph

A Human Risk Graph is a 4-tuple **G = (V, E, W, C)** where:

- **V** is a finite set of vertices representing people in an organization
- **E ⊆ V × V** is a set of directed edges representing dependency relationships
- **W: E → [0,1]** is an edge weight function representing dependency strength
- **C: V → [0,1]** is a vertex criticality function representing individual importance

### Definition 2: Edge Types

Each edge e ∈ E has an associated type τ(e) ∈ T where T = {approval, escalation, bypass}:

- **approval**: person u must approve decisions by person v
- **escalation**: person u can escalate to person v
- **bypass**: person u can override controls normally enforced by v

### Definition 3: Critical Nodes

A node v ∈ V is **critical** if C(v) ≥ θ where θ is a criticality threshold (typically θ = 0.7).

Let **V_critical ⊆ V** denote the set of all critical nodes.

### Model versions

| Model | Default | Use |
|-------|---------|-----|
| `hrg-2` | since 0.5.0 | Section 3. Size-independent, explainable metrics and a fix plan. |
| `hrg-3` | experimental, since 0.12.0 | [model-hrg3.md](model-hrg3.md). Critical functions: who can perform them and whether one person can complete them alone. |
| `hrg-1` | up to 0.4.x | Section 4. The model of the original paper; `--model hrg-1` reproduces its results. |

Every report records the model it was computed with.

## 3. Model hrg-2

Model hrg-1 has three known weaknesses: a single approver for everyone gives a decision
concentration of 0 (the Gini coefficient of one value), the bus factor is divided by |V| so
the same single point of failure looks harmless in a large organization, and the linear
composite lets one severe weakness be averaged away by two good metrics. hrg-2 fixes all three.

Let U be the undirected graph of the approval, escalation and other non-bypass dependencies
(the **support graph**). Bypasses are left out on purpose: being able to override someone
does not make the organization less dependent on them, and counting an override as a path
would let a new bypass lower key-person risk. Bypasses are measured by B instead.
(Before 0.8.1, U included bypasses.)

### 3.1 Key-person risk (K)

For a person v, let P₋ᵥ be the number of connected pairs of people other than v in U, and
L(v) the number of those pairs that are disconnected in U − v. The **impact** of v is

$$I(v) = \frac{L(v)}{P_{-v}}$$

I(v) > 0 exactly when v is an articulation point, so impact generalises the single point of
failure to "how much depends on this person". The key-person risk is

$$K = \max_{v \in V} C(v) \cdot I(v)$$

K does not depend on the size of the organization: in a star with centre c, K = C(c) for any
number of leaves. The reports also show how many people v **cuts off** (people outside the
largest remaining group) and the **bus factor**: the node connectivity of the largest
connected component of U, i.e. the smallest number of people whose loss splits it.

### 3.2 Approval concentration (D)

Let A be the approval edges. The approval weight held by person u is
$w_u = \sum_{(u,v) \in A} W(u,v)$ (u is the approver), and $s_u = w_u / \sum_x w_x$ is u's share.
D is the Herfindahl-Hirschman index:

$$D = \sum_u s_u^2, \qquad N_{\text{eff}} = 1/D$$

N_eff is the **effective number of approvers**: D = 1 for a single approver, 1/n for n
equal approvers. Findings: fewer than 4 effective approvers (D ≥ 0.25) is a warning,
fewer than 2 (D ≥ 0.5) an error.

Concentration is not always a weakness: approving every production change through one
security team can be a deliberate control. D measures how few people the decisions depend
on (availability and the room for one person's error), not whether the process is right.
When the concentration is intended, record it as a risk acceptance with a reason and an
expiry date, so that it stays visible without failing CI.

### 3.3 Override exposure (B)

A bypass edge (x, a) means x can override the controls a enforces, so every approval
(a, t) can be overridden. Let A_c be the **critical approvals**: approval edges with a
critical approver or a critical approvee, and f(a) how fully a can be overridden: 1 if any
bypass of a is unreviewed, ½ if every bypass of a is a **break-glass** bypass whose use is
reviewed afterwards (`review: after`), 0 if a cannot be bypassed. Then

$$B = \frac{\sum_{(a,t) \in A_c} W(a,t)\, f(a)}{\sum_{e \in A_c} W(e)}$$

with B = 0 when A_c is empty. A break-glass bypass still lets one person override the
control, but misuse is caught; the factor ½ is a model parameter like the weights below.

### 3.4 Composite risk, score and grade

The three weaknesses are combined with a noisy-OR, normalised so that the worst case is 1:

$$R = \frac{1 - (1 - \alpha K)(1 - \beta D)(1 - \gamma B)}{1 - (1 - \alpha)(1 - \beta)(1 - \gamma)}$$

with α = 0.4, β = 0.3, γ = 0.3 by default. R = 0 without weaknesses, R = 1 when all three
metrics are 1, R is increasing in each metric, and a single metric at 1 contributes more than
its linear share (for example 0.57 instead of 0.4 for K). The **score** is
$\text{round}(100 \cdot (1 - R))$.

The noisy-OR is a modelling choice, not a claim that the three risks are independent: in a
real organization a key person often also holds the approvals and the bypass. It is used
because a severe weakness then dominates the score instead of being averaged away by two
good metrics.

The weights are model parameters, not empirically calibrated values: they express that a
key person weighs a little more than concentration or overrides. Set them in `hrg.toml`
(`[weights]`) if your organization weighs these risks differently, and compare scores
only under the same weights.

| Score | Grade | Risk level |
|-------|-------|------------|
| 90-100 | A | Low |
| 80-89 | B | Low |
| 70-79 | C | Low |
| 50-69 | D | Moderate |
| 30-49 | F | High |
| 0-29 | F | Critical |

**What the score means.** The score is a structural index of how the organization is wired:
who depends on whom, how approval authority is spread, and which controls can be
overridden. It is not a calibrated probability of an incident, and two organizations with
the same score can fail in different ways; read the three metrics and the findings, not
only the number. It is as good as the graph: a dependency that exists only in practice
(an approval in chat, an admin who never merges) is invisible until someone adds it, which
is why `hrg scan` marks inferred dependencies as unconfirmed. When some dependencies are
unconfirmed, the reports also give the score on confirmed dependencies only; a large gap
between the two means the result rests on data nobody has checked yet.

### 3.5 Fix plan

`hrg analyze` simulates remediations, applies the one that lowers R the most, and repeats
(three steps by default):

- **Deputy** for a key person or one of the top three approvers: a new person with the same
  criticality who shares each of their approvals (the weight is split in two), has the same
  escalations and can be overridden by the same bypasses, but does not get their bypass powers.
- **Second-person check on a bypass** involving a critical person: the bypass is no longer a
  single-person override and is removed.

A deputy removes a person's own impact, but adds one more person behind any other
bottleneck, so a deputy is not always an improvement; the plan only lists steps that lower R
by at least half a point.

The plan shows which structural changes improve the model, not that they are feasible: a
deputy only helps if they have the skills, the access and the time, and a second-person
check only helps if the second person is independent.

### 3.6 Properties checked by the test suite

- K, D, B, R ∈ [0, 1]; R is increasing in each metric.
- K does not decrease when any criticality increases.
- Adding a bypass never decreases B and never improves the score; it does not change K or
  the bus factor. Putting a check on a bypass never increases R; marking a bypass as
  reviewed after use (break-glass) never increases R.
- A deputy never increases the person's own impact.
- Relabelling people does not change any result.
- Reference structures: star (K = C(c), independent of size), single approver (D = 1),
  n equal approvers (D = 1/n), complete team (K = 0, bus factor n − 1).

### 3.7 Complexity

| Metric | Time |
|--------|------|
| K | O(\|V\| + \|E\|): one depth-first search with Tarjan's low-link gives the parts every articulation point splits its component into (`separations`) |
| Bus factor | O(\|V\| + \|E\|) with a single point of failure, otherwise node connectivity (max-flow) |
| D, B | O(\|E\|) |

The fix plan evaluates the model once per candidate remediation (at most 16 per step), so
it is linear in the size of the graph too: about 0.6 s for 3,000 people and 2.4 s for
10,000 on a laptop. The hrg-1 bypass risk enumerates paths of length up to 5 and grows
exponentially on dense graphs.

## 4. Model hrg-1 (original paper)

### 4.1 Bus Factor Score (BF)

The Bus Factor Score measures organizational fragility to loss of key individuals.

**Definition 4 (Bus Factor Score):**

$$BF(G) = \frac{1}{|V|} \sum_{v \in AP(G)} C(v)$$

where AP(G) is the set of **articulation points** (cut vertices) in G — nodes whose removal disconnects the graph or isolates critical nodes.

**Properties:**
- BF(G) ∈ [0,1]
- Higher BF indicates greater fragility
- BF = 0 when no articulation points exist

**Algorithm Complexity:** O(|V| + |E|) using Tarjan's algorithm for finding articulation points.

### 4.2 Decision Concentration Score (DC)

Measures inequality in the distribution of decision authority.

**Definition 5 (Decision Concentration Score):**

Let A = {e ∈ E : τ(e) = approval} be the set of approval edges.

For each person u ∈ V, define their approval weight (u is the approver):

$$w_u = \sum_{(u,v) \in A} W((u,v))$$

Let **w = (w_1, w_2, ..., w_n)** be the sorted sequence of approval weights.

The Decision Concentration Score is the **Gini coefficient**:

$$DC(G) = \frac{\sum_{i=1}^{n} (2i - n - 1) \cdot w_i}{n \sum_{i=1}^{n} w_i}$$

**Properties:**
- DC(G) ∈ [0,1]
- DC = 0: perfectly equal distribution
- DC = 1: maximum concentration (one person has all authority)

**Alternative formulation using Shannon entropy:**

$$DC_{entropy}(G) = 1 - \frac{H(w)}{H_{max}}$$

where $H(w) = -\sum_{i=1}^{n} p_i \log_2(p_i)$ and $p_i = \frac{w_i}{\sum w_j}$

### 4.3 Bypass Risk Score (BR)

Quantifies the fraction of critical paths that can be circumvented.

**Definition 6 (Critical Path):**

A path P = (v_1, v_2, ..., v_k) is **critical** if:
1. v_1 ∈ V_critical or v_k ∈ V_critical
2. ∃e ∈ P such that τ(e) = approval

**Definition 7 (Bypass Risk Score):**

Let CP(G) be the set of all critical paths in G.

A critical path P is **bypassable** if ∃e ∈ E such that:
- τ(e) = bypass
- e creates a shortcut around P

$$BR(G) = \frac{|\{P \in CP(G) : P \text{ is bypassable}\}|}{|CP(G)|}$$

**Properties:**
- BR(G) ∈ [0,1]
- BR = 0: no critical paths can be bypassed
- BR = 1: all critical paths have bypass mechanisms

**Algorithm Complexity:** O(|V| · |E|) using modified BFS to enumerate critical paths.

### 4.4 Composite HRG Risk Score

**Definition 8 (HRG Risk Score):**

The overall risk score is a weighted combination:

$$HRG(G) = \alpha \cdot BF(G) + \beta \cdot DC(G) + \gamma \cdot BR(G)$$

where α + β + γ = 1 and α, β, γ ≥ 0 are weight parameters.

**Standard weighting:** α = 0.4, β = 0.3, γ = 0.3

## 5. Theoretical Properties (hrg-1)

### Theorem 1 (Monotonicity)

If C(v) increases for some v ∈ AP(G), then BF(G) increases.

**Proof:** Direct from Definition 4, as the sum increases monotonically with C(v). □

### Theorem 2 (Worst-Case Bus Factor)

For a star graph with center c, BF(G) = C(c).

**Proof:** In a star graph, the center is the only articulation point. Removing c disconnects all other nodes. □

### Theorem 3 (Bypass Risk Bound)

If no bypass edges exist (∀e ∈ E, τ(e) ≠ bypass), then BR(G) = 0.

**Proof:** Trivial from Definition 7. □

## 6. Computational Complexity (hrg-1)

| Metric | Time Complexity | Space Complexity |
|--------|-----------------|------------------|
| BF(G) | O(\|V\| + \|E\|) | O(\|V\|) |
| DC(G) | O(\|E\| + \|V\| log \|V\|) | O(\|V\|) |
| BR(G) | O(\|V\| · \|E\|) | O(\|V\| + \|E\|) |

All metrics are efficiently computable for graphs with thousands of nodes.

## 7. Interpretation Guidelines

### Risk Level Classification

| HRG Score | Risk Level | Interpretation |
|-----------|------------|----------------|
| 0.0 - 0.3 | Low | Distributed authority, resilient |
| 0.3 - 0.5 | Moderate | Some concentration, manageable |
| 0.5 - 0.7 | High | Significant dependencies, review needed |
| 0.7 - 1.0 | Critical | Severe single points of failure |

### Per-Metric Thresholds

- **BF > 0.6**: Organization vulnerable to loss of key individuals
- **DC > 0.5**: Authority excessively centralized
- **BR > 0.4**: Too many bypass mechanisms, control effectiveness reduced

## 8. Limitations

1. **Static Analysis**: Model captures structure at a point in time, not dynamics
2. **Binary Relationships**: Edge weights are simplified; real dependencies are complex
3. **Assumes Rational Actors**: Does not model malicious insiders explicitly
4. **No Temporal Dimension**: Does not account for time-dependent availability

## 9. Future Extensions

- Dynamic HRG: time-varying graphs G(t)
- Probabilistic HRG: uncertainty in C(v) and W(e)
- Multi-layer HRG: separate graphs for different security domains
- Attack simulation: adversarial path analysis
