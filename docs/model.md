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

## 3. Risk Metrics

### 3.1 Bus Factor Score (BF)

The Bus Factor Score measures organizational fragility to loss of key individuals.

**Definition 4 (Bus Factor Score):**

$$BF(G) = \frac{1}{|V|} \sum_{v \in AP(G)} C(v)$$

where AP(G) is the set of **articulation points** (cut vertices) in G — nodes whose removal disconnects the graph or isolates critical nodes.

**Properties:**
- BF(G) ∈ [0,1]
- Higher BF indicates greater fragility
- BF = 0 when no articulation points exist

**Algorithm Complexity:** O(|V| + |E|) using Tarjan's algorithm for finding articulation points.

### 3.2 Decision Concentration Score (DC)

Measures inequality in the distribution of decision authority.

**Definition 5 (Decision Concentration Score):**

Let A = {e ∈ E : τ(e) = approval} be the set of approval edges.

For each person v ∈ V, define their approval weight:

$$w_v = \sum_{(u,v) \in A} W((u,v))$$

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

### 3.3 Bypass Risk Score (BR)

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

### 3.4 Composite HRG Risk Score

**Definition 8 (HRG Risk Score):**

The overall risk score is a weighted combination:

$$HRG(G) = \alpha \cdot BF(G) + \beta \cdot DC(G) + \gamma \cdot BR(G)$$

where α + β + γ = 1 and α, β, γ ≥ 0 are weight parameters.

**Standard weighting:** α = 0.4, β = 0.3, γ = 0.3

## 4. Theoretical Properties

### Theorem 1 (Monotonicity)

If C(v) increases for some v ∈ AP(G), then BF(G) increases.

**Proof:** Direct from Definition 4, as the sum increases monotonically with C(v). □

### Theorem 2 (Worst-Case Bus Factor)

For a star graph with center c, BF(G) = C(c).

**Proof:** In a star graph, the center is the only articulation point. Removing c disconnects all other nodes. □

### Theorem 3 (Bypass Risk Bound)

If no bypass edges exist (∀e ∈ E, τ(e) ≠ bypass), then BR(G) = 0.

**Proof:** Trivial from Definition 7. □

## 5. Computational Complexity

| Metric | Time Complexity | Space Complexity |
|--------|-----------------|------------------|
| BF(G) | O(\|V\| + \|E\|) | O(\|V\|) |
| DC(G) | O(\|E\| + \|V\| log \|V\|) | O(\|V\|) |
| BR(G) | O(\|V\| · \|E\|) | O(\|V\| + \|E\|) |

All metrics are efficiently computable for graphs with thousands of nodes.

## 6. Interpretation Guidelines

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

## 7. Limitations

1. **Static Analysis**: Model captures structure at a point in time, not dynamics
2. **Binary Relationships**: Edge weights are simplified; real dependencies are complex
3. **Assumes Rational Actors**: Does not model malicious insiders explicitly
4. **No Temporal Dimension**: Does not account for time-dependent availability

## 8. Future Extensions

- Dynamic HRG: time-varying graphs G(t)
- Probabilistic HRG: uncertainty in C(v) and W(e)
- Multi-layer HRG: separate graphs for different security domains
- Attack simulation: adversarial path analysis
