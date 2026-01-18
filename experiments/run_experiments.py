"""
Run HRG experiments and collect results.

Compares HRG metrics across different organizational topologies
and validates against baseline methods.
"""
import json
import pandas as pd
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.hrg import HumanRiskGraph
from src.graph_analysis import compute_betweenness_centrality


def load_data(filename: str):
    """Load organization data from JSON."""
    with open(filename, 'r') as f:
        data = json.load(f)
    return data["people"], data["dependencies"]


def run_experiment(data_file: str) -> dict:
    """
    Run HRG analysis on a dataset.
    
    Args:
        data_file: Path to JSON data file
        
    Returns:
        Dict with results
    """
    people, dependencies = load_data(data_file)
    
    # Create HRG
    hrg = HumanRiskGraph(people, dependencies)
    
    # Calculate metrics
    results = hrg.calculate()
    
    # Add graph statistics
    graph = hrg.export_graph()
    results["num_nodes"] = len(graph.nodes())
    results["num_edges"] = len(graph.edges())
    results["graph_density"] = len(graph.edges()) / (len(graph.nodes()) * (len(graph.nodes()) - 1)) if len(graph.nodes()) > 1 else 0
    
    # Analyze critical nodes
    results["num_critical_nodes"] = len(results["critical_nodes"])
    results["num_articulation_points"] = len(results["articulation_points"])
    
    return results


def run_all_experiments():
    """Run experiments on all synthetic datasets."""
    data_dir = Path(__file__).parent / "data"
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    
    # Find all synthetic data files
    data_files = list(data_dir.glob("synthetic_*.json"))
    
    if not data_files:
        print("No synthetic data found. Run generate_data.py first.")
        return
    
    all_results = []
    
    for data_file in data_files:
        print(f"Running experiment on {data_file.name}...")
        
        topology = data_file.stem.replace("synthetic_", "")
        results = run_experiment(str(data_file))
        results["topology"] = topology
        results["dataset"] = data_file.name
        
        all_results.append(results)
        
        print(f"  HRG Score: {results['composite_score']:.3f} ({results['risk_level']})")
        print(f"  Bus Factor: {results['bus_factor']:.3f}")
        print(f"  Decision Concentration: {results['decision_concentration']:.3f}")
        print(f"  Bypass Risk: {results['bypass_risk']:.3f}")
        print()
    
    # Save results to CSV
    df = pd.DataFrame(all_results)
    output_file = results_dir / "experiment_results.csv"
    df.to_csv(output_file, index=False)
    print(f"Results saved to {output_file}")
    
    # Print summary
    print("\n=== Summary ===")
    print(df[["topology", "composite_score", "risk_level", "bus_factor", "decision_concentration", "bypass_risk"]])


if __name__ == "__main__":
    run_all_experiments()
