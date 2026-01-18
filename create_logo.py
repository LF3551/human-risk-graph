"""
Script to generate the Human Risk Graph logo without version number.
"""
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import networkx as nx

# Create figure
fig, ax = plt.subplots(1, 1, figsize=(16, 8), facecolor='#1e2130')
ax.set_facecolor('#1e2130')
ax.set_xlim(0, 16)
ax.set_ylim(0, 8)
ax.axis('off')

# Graph nodes positions (left side)
positions = {
    'A': (2.5, 6),
    'B': (4, 6),
    'C': (3, 4),
    'D': (4.5, 4),
    'E': (3.5, 2)
}

# Node colors and sizes
node_colors = {
    'A': '#00d4ff',
    'B': '#00b894',
    'C': '#ff8c42',
    'D': '#ffd93d',
    'E': '#f0e5d8'
}

node_sizes = {
    'A': 0.5,
    'B': 0.5,
    'C': 0.6,
    'D': 0.45,
    'E': 0.5
}

# Draw edges
edges = [('A', 'C'), ('B', 'C'), ('C', 'D'), ('C', 'E')]
for edge in edges:
    start = positions[edge[0]]
    end = positions[edge[1]]
    ax.annotate('', xy=end, xytext=start,
                arrowprops=dict(arrowstyle='->', lw=2.5, color='#4a5568', 
                              connectionstyle="arc3,rad=0.1", alpha=0.7))

# Draw nodes
for node, pos in positions.items():
    # Highlight for critical node C
    if node == 'C':
        highlight = patches.Circle(pos, node_sizes[node] + 0.08, 
                                  color='#ff6b35', alpha=0.3, zorder=1)
        ax.add_patch(highlight)
    
    circle = patches.Circle(pos, node_sizes[node], color=node_colors[node], 
                           ec='white', linewidth=4, zorder=2)
    ax.add_patch(circle)
    
    ax.text(pos[0], pos[1], node, fontsize=44, fontweight='bold',
           ha='center', va='center', color='#1e2130', zorder=3)

# Title text (right side)
ax.text(11, 5.8, 'HUMAN', fontsize=100, fontweight='bold',
       ha='center', va='center', color='#00d4ff', family='sans-serif')

ax.text(11, 4.5, 'RISK', fontsize=100, fontweight='bold',
       ha='center', va='center', color='#ff8c42', family='sans-serif')

ax.text(11, 3.2, 'GRAPH', fontsize=100, fontweight='bold',
       ha='center', va='center', color='white', family='sans-serif')

# Subtitle
ax.text(11, 1.8, 'Quantitative Security Risk Model', fontsize=28,
       ha='center', va='center', color='#a0aec0', style='italic', family='sans-serif')

ax.text(11, 1.2, 'People as Attack Surface', fontsize=24,
       ha='center', va='center', color='#718096', family='sans-serif')

plt.tight_layout()
plt.savefig('logo.png', dpi=150, facecolor='#1e2130', bbox_inches='tight', pad_inches=0.3)
plt.savefig('logo_social.png', dpi=150, facecolor='#1e2130', bbox_inches='tight', pad_inches=0.3)
print("✅ Logo created: logo.png and logo_social.png (without version)")
