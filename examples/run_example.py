#!/usr/bin/env python3
"""
Example usage of Human Risk Graph.

This demonstrates how to:
1. Load organizational data
2. Create a Human Risk Graph
3. Calculate risk metrics
4. Analyze results
"""
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.hrg import HumanRiskGraph


def main():
    """Run example HRG analysis."""
    
    # Load example organization data
    data_file = Path(__file__).parent.parent / "data" / "example_organization.json"
    
    with open(data_file, 'r') as f:
        data = json.load(f)
    
    people = data["people"]
    dependencies = data["dependencies"]
    
    print("=" * 60)
    print("Human Risk Graph - Example Analysis")
    print("=" * 60)
    print()
    
    # Display organization structure
    print(f"Organization: {len(people)} people, {len(dependencies)} dependencies")
    print()
    print("People:")
    for person in people:
        print(f"  {person['id']}: {person['role']} (criticality: {person['criticality']})")
    print()
    
    print("Dependencies:")
    for dep in dependencies:
        print(f"  {dep['from']} → {dep['to']} ({dep['type']}, weight: {dep['weight']})")
    print()
    
    # Create HRG and calculate metrics
    print("-" * 60)
    print("Analyzing Human Risk Graph...")
    print("-" * 60)
    print()
    
    hrg = HumanRiskGraph(people, dependencies)
    results = hrg.calculate()
    
    # Display results
    print("RISK METRICS:")
    print(f"  Bus Factor Score:           {results['bus_factor']:.3f}")
    print(f"  Decision Concentration:     {results['decision_concentration']:.3f}")
    print(f"  Bypass Risk Score:          {results['bypass_risk']:.3f}")
    print()
    print(f"  Composite HRG Score:        {results['composite_score']:.3f}")
    print(f"  Risk Level:                 {results['risk_level']}")
    print()
    
    # Critical nodes
    print("CRITICAL NODES:")
    if results['critical_nodes']:
        for node_id in results['critical_nodes']:
            person = next(p for p in people if p['id'] == node_id)
            print(f"  {node_id}: {person['role']} (criticality: {person['criticality']})")
    else:
        print("  None")
    print()
    
    # Articulation points
    print("ARTICULATION POINTS (Single Points of Failure):")
    if results['articulation_points']:
        for node_id in results['articulation_points']:
            person = next(p for p in people if p['id'] == node_id)
            print(f"  {node_id}: {person['role']}")
            
            # Analyze this node
            analysis = hrg.analyze_node(node_id)
            print(f"    - Betweenness Centrality: {analysis['betweenness_centrality']:.3f}")
            print(f"    - In-degree: {analysis['in_degree']}, Out-degree: {analysis['out_degree']}")
    else:
        print("  None")
    print()
    
    # Critical dependencies
    print("CRITICAL DEPENDENCIES:")
    critical_deps = hrg.get_critical_dependencies()
    for from_node, to_node, edge_type in critical_deps:
        print(f"  {from_node} → {to_node} ({edge_type})")
    print()
    
    # Simulate node removal
    print("-" * 60)
    print("Impact Analysis: What if we lose key people?")
    print("-" * 60)
    print()
    
    for node_id in results['articulation_points'][:2]:  # Analyze top 2
        person = next(p for p in people if p['id'] == node_id)
        impact = hrg.simulate_node_removal(node_id)
        
        print(f"Removing {node_id} ({person['role']}):")
        print(f"  Original HRG Score: {impact['original_score']:.3f}")
        print(f"  New HRG Score:      {impact['new_score']:.3f}")
        print(f"  Score Change:       {impact['score_change']:+.3f}")
        
        if impact['disconnected_nodes']:
            print(f"  Disconnected nodes: {', '.join(impact['disconnected_nodes'])}")
        print()
    
    # Interpretation
    print("=" * 60)
    print("INTERPRETATION")
    print("=" * 60)
    print()
    
    if results['risk_level'] in ['High', 'Critical']:
        print("⚠️  WARNING: This organization has significant human risk factors!")
        print()
        
        if results['bus_factor'] > 0.6:
            print("  • Bus Factor is high - losing key people would severely impact operations")
        
        if results['decision_concentration'] > 0.5:
            print("  • Decision-making is too centralized - consider distributing authority")
        
        if results['bypass_risk'] > 0.4:
            print("  • Too many bypass mechanisms - emergency controls may be overused")
    else:
        print("✓ This organization has reasonable risk distribution.")
    
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
