"""
Visualization of HRG experiment results.

Generates publication-quality plots for research paper.
"""
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Set publication style
plt.style.use('seaborn-v0_8-paper')
plt.rcParams['figure.dpi'] = 300
plt.rcParams['font.size'] = 10
plt.rcParams['axes.labelsize'] = 11
plt.rcParams['axes.titlesize'] = 12
plt.rcParams['legend.fontsize'] = 9


def load_results(results_file: str = "experiments/results/experiment_results.csv") -> pd.DataFrame:
    """Load experiment results from CSV."""
    return pd.read_csv(results_file)


def plot_metric_comparison(df: pd.DataFrame, output_dir: Path):
    """
    Create bar chart comparing metrics across topologies.
    """
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    fig.suptitle('HRG Metrics Comparison Across Organizational Topologies', fontsize=14, fontweight='bold')
    
    metrics = [
        ('bus_factor', 'Bus Factor Score', axes[0, 0]),
        ('decision_concentration', 'Decision Concentration', axes[0, 1]),
        ('bypass_risk', 'Bypass Risk Score', axes[1, 0]),
        ('composite_score', 'Composite HRG Score', axes[1, 1])
    ]
    
    colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
    
    for metric, title, ax in metrics:
        x = np.arange(len(df))
        bars = ax.bar(x, df[metric], color=colors, alpha=0.8, edgecolor='black', linewidth=0.5)
        
        ax.set_xlabel('Topology', fontweight='bold')
        ax.set_ylabel('Score', fontweight='bold')
        ax.set_title(title, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(df['topology'], rotation=45, ha='right')
        ax.set_ylim(0, max(df[metric]) * 1.2)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        
        # Add value labels on bars
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.3f}',
                   ha='center', va='bottom', fontsize=8)
    
    plt.tight_layout()
    output_file = output_dir / 'metric_comparison.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_file}")
    plt.close()


def plot_composite_score_breakdown(df: pd.DataFrame, output_dir: Path):
    """
    Create stacked bar chart showing contribution of each metric to composite score.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Weights from composite formula: α=0.4, β=0.3, γ=0.3
    bf_contribution = df['bus_factor'] * 0.4
    dc_contribution = df['decision_concentration'] * 0.3
    br_contribution = df['bypass_risk'] * 0.3
    
    x = np.arange(len(df))
    width = 0.6
    
    p1 = ax.bar(x, bf_contribution, width, label='Bus Factor (40%)', color='#2E86AB', edgecolor='black', linewidth=0.5)
    p2 = ax.bar(x, dc_contribution, width, bottom=bf_contribution, label='Decision Concentration (30%)', color='#A23B72', edgecolor='black', linewidth=0.5)
    p3 = ax.bar(x, br_contribution, width, bottom=bf_contribution + dc_contribution, label='Bypass Risk (30%)', color='#F18F01', edgecolor='black', linewidth=0.5)
    
    ax.set_xlabel('Topology', fontweight='bold', fontsize=12)
    ax.set_ylabel('Composite Score Contribution', fontweight='bold', fontsize=12)
    ax.set_title('Composite HRG Score Breakdown by Component', fontweight='bold', fontsize=13)
    ax.set_xticks(x)
    ax.set_xticklabels(df['topology'], rotation=45, ha='right')
    ax.legend(loc='upper right', framealpha=0.9)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    plt.tight_layout()
    output_file = output_dir / 'composite_breakdown.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_file}")
    plt.close()


def plot_radar_chart(df: pd.DataFrame, output_dir: Path):
    """
    Create radar chart comparing risk profiles across topologies.
    """
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))
    
    # Metrics to display on radar
    categories = ['Bus Factor', 'Decision\nConcentration', 'Bypass Risk']
    N = len(categories)
    
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]  # Complete the circle
    
    colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
    
    for idx, (_, row) in enumerate(df.iterrows()):
        values = [
            row['bus_factor'],
            row['decision_concentration'],
            row['bypass_risk']
        ]
        values += values[:1]  # Complete the circle
        
        ax.plot(angles, values, 'o-', linewidth=2, label=row['topology'].capitalize(), color=colors[idx])
        ax.fill(angles, values, alpha=0.15, color=colors[idx])
    
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_ylim(0, max(df[['bus_factor', 'decision_concentration', 'bypass_risk']].max()) * 1.2)
    ax.set_title('Risk Profile Comparison\n(Radar Chart)', fontweight='bold', fontsize=13, pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), framealpha=0.9)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    output_file = output_dir / 'risk_profile_radar.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_file}")
    plt.close()


def plot_graph_statistics(df: pd.DataFrame, output_dir: Path):
    """
    Plot graph structural statistics.
    """
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    fig.suptitle('Organizational Graph Structure Statistics', fontsize=14, fontweight='bold')
    
    x = np.arange(len(df))
    width = 0.6
    colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
    
    # Number of articulation points
    axes[0].bar(x, df['num_articulation_points'], width, color=colors, alpha=0.8, edgecolor='black', linewidth=0.5)
    axes[0].set_xlabel('Topology', fontweight='bold')
    axes[0].set_ylabel('Count', fontweight='bold')
    axes[0].set_title('Articulation Points\n(Single Points of Failure)', fontweight='bold')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(df['topology'], rotation=45, ha='right')
    axes[0].grid(axis='y', alpha=0.3, linestyle='--')
    
    # Graph density
    axes[1].bar(x, df['graph_density'], width, color=colors, alpha=0.8, edgecolor='black', linewidth=0.5)
    axes[1].set_xlabel('Topology', fontweight='bold')
    axes[1].set_ylabel('Density', fontweight='bold')
    axes[1].set_title('Graph Density\n(Edge Connectivity)', fontweight='bold')
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(df['topology'], rotation=45, ha='right')
    axes[1].grid(axis='y', alpha=0.3, linestyle='--')
    
    # Critical nodes
    axes[2].bar(x, df['num_critical_nodes'], width, color=colors, alpha=0.8, edgecolor='black', linewidth=0.5)
    axes[2].set_xlabel('Topology', fontweight='bold')
    axes[2].set_ylabel('Count', fontweight='bold')
    axes[2].set_title('Critical Nodes\n(High Importance)', fontweight='bold')
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(df['topology'], rotation=45, ha='right')
    axes[2].grid(axis='y', alpha=0.3, linestyle='--')
    
    plt.tight_layout()
    output_file = output_dir / 'graph_statistics.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_file}")
    plt.close()


def generate_all_plots():
    """Generate all visualizations."""
    print("=" * 60)
    print("HRG Experiment Visualization")
    print("=" * 60)
    print()
    
    # Load data
    results_file = Path("experiments/results/experiment_results.csv")
    if not results_file.exists():
        print(f"ERROR: {results_file} not found!")
        print("Run 'python experiments/run_experiments.py' first.")
        return
    
    df = load_results(str(results_file))
    print(f"Loaded {len(df)} experiment results")
    print()
    
    # Create output directory
    output_dir = Path("experiments/plots")
    output_dir.mkdir(exist_ok=True)
    
    # Generate plots
    print("Generating plots...")
    plot_metric_comparison(df, output_dir)
    plot_composite_score_breakdown(df, output_dir)
    plot_radar_chart(df, output_dir)
    plot_graph_statistics(df, output_dir)
    
    print()
    print("=" * 60)
    print("✓ All plots generated successfully!")
    print(f"  Output directory: {output_dir.absolute()}")
    print("=" * 60)


if __name__ == "__main__":
    generate_all_plots()
