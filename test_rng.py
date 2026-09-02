#!/usr/bin/env python3
import numpy as np

# Test rng.choice with node list
SEED = 20260909
rng = np.random.default_rng(SEED)

NODES_PER_GROUP = {"A": 40, "B": 30, "C": 30}

# Create all_nodes the same way as in generate.py
all_nodes = []
for group in ["A", "B", "C"]:
    for i in range(1, NODES_PER_GROUP[group] + 1):
        all_nodes.append(f"node_{group.lower()}_{i:02d}")

print(f"All nodes list: {len(all_nodes)} nodes")
print(f"First 5: {all_nodes[:5]}")
print(f"Last 5: {all_nodes[-5:]}")

# Simulate 190 draws (Fault A retries)
draws = []
for _ in range(190):
    node = rng.choice(all_nodes)
    draws.append(node)

# Count by group
groups = {"A": 0, "B": 0, "C": 0}
for node in draws:
    group = node.split("_")[1].upper()
    groups[group] += 1

print(f"\nFault A retry distribution from uniform draw of 190:")
print(f"  A: {groups['A']} (expected ~76, ratio {groups['A']}/190 = {100*groups['A']/190:.1f}%)")
print(f"  B: {groups['B']} (expected ~57, ratio {groups['B']}/190 = {100*groups['B']/190:.1f}%)")
print(f"  C: {groups['C']} (expected ~57, ratio {groups['C']}/190 = {100*groups['C']/190:.1f}%)")

print(f"\nSample draws:")
for i in range(10):
    print(f"  {i}: {draws[i]}")
