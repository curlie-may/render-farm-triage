#!/usr/bin/env python3
import pandas as pd

# Load the attempts data
df = pd.read_parquet('data/attempts.parquet')

# Get Fault A first attempts (exclude shot_047 which is Fault B)
fault_a_attempt1_tasks = df[
    (df['error_class'] == 'oom') &
    (df['node_group'] == 'B') &
    (df['started_at'] >= '2026-09-08 23:04') &
    (df['attempt'] == 1) &
    (df['shot_id'] != 'shot_047')
]['task_id'].unique()

print(f"Fault A: {len(fault_a_attempt1_tasks)} tasks failed on attempt 1")

# Get Fault A retries (attempt 2)
fault_a_retries = df[
    (df['task_id'].isin(fault_a_attempt1_tasks)) &
    (df['attempt'] == 2)
]

print(f"Fault A retries: {len(fault_a_retries)} tasks attempted on attempt 2")

# Count by retry group
retry_groups = fault_a_retries['node_group'].value_counts().to_dict()
print(f"Fault A retry distribution by group:")
print(f"  A: {retry_groups.get('A', 0)}")
print(f"  B: {retry_groups.get('B', 0)}")
print(f"  C: {retry_groups.get('C', 0)}")

# Show sample nodes
print(f"\nSample retry nodes:")
sample = fault_a_retries[['task_id', 'node_id', 'node_group', 'attempt']].head(20)
for idx, row in sample.iterrows():
    print(f"  {row['task_id']}: {row['node_id']} (group {row['node_group']})")
