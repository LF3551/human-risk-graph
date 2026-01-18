# HRG Example

## Organization

We model a small organization of four people:

- A — SRE (critical infrastructure access)
- B — Security Engineer (approval authority)
- C — Manager (emergency bypass authority)
- D — Developer

## Dependencies

- A depends on B for security approvals
- C can bypass A during emergencies

## Observations

- A is a single point of failure for operations
- C introduces bypass risk
- Removing A or C significantly increases systemic risk

## Interpretation

Although no technical vulnerability exists, organizational structure
creates a latent security risk that HRG exposes.
