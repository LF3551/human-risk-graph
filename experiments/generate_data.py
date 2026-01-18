"""
Synthetic data generator for HRG experiments.

Generates realistic organizational graphs with various topologies
for testing and benchmarking.
"""
import json
import random
import networkx as nx
from typing import List, Dict, Tuple


def generate_synthetic_organization(
    num_people: int = 20,
    topology: str = "hierarchical",
    seed: int = 42
) -> Tuple[List[Dict], List[Dict]]:
    """
    Generate synthetic organizational data.
    
    Args:
        num_people: Number of people in organization
        topology: 'hierarchical', 'flat', 'star', or 'random'
        seed: Random seed for reproducibility
        
    Returns:
        Tuple of (people, dependencies)
    """
    random.seed(seed)
    
    # Generate people with roles and criticality
    roles = ["SRE", "Security Engineer", "Developer", "Manager", "Director", "Analyst"]
    people = []
    
    for i in range(num_people):
        person_id = f"P{i+1}"
        role = random.choice(roles)
        
        # Managers and directors tend to have higher criticality
        if role in ["Manager", "Director"]:
            criticality = random.uniform(0.6, 0.95)
        elif role in ["SRE", "Security Engineer"]:
            criticality = random.uniform(0.5, 0.9)
        else:
            criticality = random.uniform(0.3, 0.7)
        
        people.append({
            "id": person_id,
            "role": role,
            "criticality": round(criticality, 2)
        })
    
    # Generate dependencies based on topology
    dependencies = []
    
    if topology == "hierarchical":
        dependencies = _generate_hierarchical(people)
    elif topology == "flat":
        dependencies = _generate_flat(people)
    elif topology == "star":
        dependencies = _generate_star(people)
    else:  # random
        dependencies = _generate_random(people)
    
    return people, dependencies


def _generate_hierarchical(people: List[Dict]) -> List[Dict]:
    """Generate hierarchical approval structure."""
    dependencies = []
    n = len(people)
    
    # Create tree structure with approvals going up
    for i in range(1, n):
        parent_idx = random.randint(0, i-1)
        
        dependencies.append({
            "from": people[i]["id"],
            "to": people[parent_idx]["id"],
            "type": "approval",
            "weight": round(random.uniform(0.6, 0.9), 2)
        })
    
    # Add some bypass edges from managers
    managers = [p for p in people if p["role"] in ["Manager", "Director"]]
    for manager in random.sample(managers, min(2, len(managers))):
        target = random.choice([p for p in people if p["id"] != manager["id"]])
        dependencies.append({
            "from": manager["id"],
            "to": target["id"],
            "type": "bypass",
            "weight": round(random.uniform(0.7, 0.95), 2)
        })
    
    return dependencies


def _generate_flat(people: List[Dict]) -> List[Dict]:
    """Generate flat structure with peer approvals."""
    dependencies = []
    n = len(people)
    
    # Create peer approval network
    for _ in range(n // 2):
        i, j = random.sample(range(n), 2)
        dependencies.append({
            "from": people[i]["id"],
            "to": people[j]["id"],
            "type": "approval",
            "weight": round(random.uniform(0.5, 0.8), 2)
        })
    
    return dependencies


def _generate_star(people: List[Dict]) -> List[Dict]:
    """Generate star topology with central authority."""
    dependencies = []
    
    # Pick central node (highest criticality)
    center = max(people, key=lambda p: p["criticality"])
    
    # Everyone reports to center
    for person in people:
        if person["id"] != center["id"]:
            dependencies.append({
                "from": person["id"],
                "to": center["id"],
                "type": "approval",
                "weight": round(random.uniform(0.7, 0.9), 2)
            })
    
    return dependencies


def _generate_random(people: List[Dict]) -> List[Dict]:
    """Generate random dependency structure."""
    dependencies = []
    n = len(people)
    num_edges = random.randint(n, 2 * n)
    
    edge_types = ["approval", "escalation", "bypass"]
    weights_ranges = {
        "approval": (0.6, 0.9),
        "escalation": (0.5, 0.8),
        "bypass": (0.7, 0.95)
    }
    
    edges_added = set()
    
    for _ in range(num_edges):
        i, j = random.sample(range(n), 2)
        edge = (people[i]["id"], people[j]["id"])
        
        if edge not in edges_added:
            edge_type = random.choice(edge_types)
            weight_range = weights_ranges[edge_type]
            
            dependencies.append({
                "from": people[i]["id"],
                "to": people[j]["id"],
                "type": edge_type,
                "weight": round(random.uniform(*weight_range), 2)
            })
            edges_added.add(edge)
    
    return dependencies


def save_synthetic_data(people: List[Dict], dependencies: List[Dict], filename: str):
    """Save synthetic data to JSON file."""
    data = {
        "people": people,
        "dependencies": dependencies
    }
    
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    # Generate different topologies
    topologies = ["hierarchical", "flat", "star", "random"]
    
    for topology in topologies:
        people, deps = generate_synthetic_organization(
            num_people=20,
            topology=topology,
            seed=42
        )
        
        filename = f"experiments/data/synthetic_{topology}.json"
        save_synthetic_data(people, deps, filename)
        print(f"Generated {filename}")
