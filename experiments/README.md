# HRG Experiments

This directory contains tools for generating synthetic organizational data and running HRG experiments.

## Structure

```
experiments/
├── data/                    # Generated synthetic datasets
├── results/                 # Experiment results (CSV files)
├── plots/                   # Visualization output (for future use)
├── generate_data.py         # Synthetic organization generator
└── run_experiments.py       # Experiment runner
```

## Quick Start

### 1. Generate Synthetic Data

```bash
python experiments/generate_data.py
```

This generates 4 organizational topologies (20 people each):
- **hierarchical**: Tree structure with approval chains
- **flat**: Peer network with distributed authority
- **star**: Centralized authority model
- **random**: Arbitrary connections

Output: `data/synthetic_*.json`

### 2. Run Experiments

```bash
python experiments/run_experiments.py
```

This analyzes all datasets and computes HRG metrics.

Output: `results/experiment_results.csv`

### 3. Generate Visualizations

```bash
python experiments/visualize.py
```

Creates publication-quality plots:
- `metric_comparison.png` — Bar charts comparing all metrics
- `composite_breakdown.png` — Stacked bars showing score components
- `risk_profile_radar.png` — Radar chart for risk profiles
- `graph_statistics.png` — Structural statistics

Output: `plots/*.png`

## Results

See `results/experiment_results.csv` for tabular data with columns:
- topology
- composite_score
- risk_level
- bus_factor
- decision_concentration
- bypass_risk
- num_nodes, num_edges, graph_density
- num_critical_nodes, num_articulation_points

## Extending

To add custom experiments:

1. Create JSON files in `data/` following this format:
```json
{
  "people": [
    {"id": "A", "role": "SRE", "criticality": 0.9}
  ],
  "dependencies": [
    {"from": "A", "to": "B", "type": "approval", "weight": 0.8}
  ]
}
```

2. Run experiments: they automatically process all `data/*.json` files

## For Research Paper

Results from these experiments should be:
1. Summarized in tables for `paper/sections/results.tex`
2. Visualized in plots (to be added)
3. Compared with baseline metrics
