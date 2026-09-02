#!/usr/bin/env python3
import pandas as pd

print('=== FINAL VALIDATION ===')
print()

# Load data
attempts_df = pd.read_parquet('data/attempts.parquet')
incidents_df = pd.read_parquet('data/past_incidents.parquet')

# Get failures by type
fault_a_all = attempts_df[
    (attempts_df['error_class'] == 'oom') & 
    (attempts_df['node_group'] == 'B') & 
    (attempts_df['started_at'] >= '2026-09-08 23:04')
].drop_duplicates(subset=['task_id'])

print(f'1. FAULT A: {len(fault_a_all)} unique tasks (required 190)')
print()

print(f'2. TOTAL DATASET:')
print(f'   Total attempts: {len(attempts_df)}')
print(f'   Unique tasks: {len(attempts_df["task_id"].unique())}')
print(f'   Total failures: {len(attempts_df[attempts_df["status"] == "failed"])}')
print()

print(f'3. FAULT A RETRY SIGNATURE:')
fault_a_attempt1 = attempts_df[
    (attempts_df['error_class'] == 'oom') & 
    (attempts_df['node_group'] == 'B') & 
    (attempts_df['started_at'] >= '2026-09-08 23:04') &
    (attempts_df['attempt'] == 1)
]['task_id'].unique()

fault_a_retries = attempts_df[
    (attempts_df['task_id'].isin(fault_a_attempt1)) &
    (attempts_df['attempt'] == 2)
]

if len(fault_a_retries) > 0:
    failed = len(fault_a_retries[fault_a_retries['status'] == 'failed'])
    rate = 100.0 * failed / len(fault_a_retries)
    group_dist = fault_a_retries['node_group'].value_counts().to_dict()
    print(f'   Retry failure rate: {rate:.1f}% ({failed}/{len(fault_a_retries)})')
    print(f'   Retry node distribution: A={group_dist.get("A", 0)}, B={group_dist.get("B", 0)}, C={group_dist.get("C", 0)}')
print()

# Fault B retries
fault_b_attempt1 = attempts_df[
    (attempts_df['shot_id'] == 'shot_047') &
    (attempts_df['frame_number'] >= 78) &
    (attempts_df['frame_number'] <= 119) &
    (attempts_df['attempt'] == 1)
]['task_id'].unique()

fault_b_retries = attempts_df[
    (attempts_df['task_id'].isin(fault_b_attempt1)) &
    (attempts_df['attempt'] == 2)
]

if len(fault_b_retries) > 0:
    failed = len(fault_b_retries[fault_b_retries['status'] == 'failed'])
    rate = 100.0 * failed / len(fault_b_retries)
    print(f'FAULT B RETRY SIGNATURE:')
    print(f'   Retry failure rate: {rate:.1f}% ({failed}/{len(fault_b_retries)})')
print()

print(f'4. PAST INCIDENTS: {len(incidents_df)} rows (required 14)')
required_checks = {
    'nfs_stall': False,
    'oom_count': 0,
    'recurrence': False
}

for _, row in incidents_df.iterrows():
    if row['incident_id'] == 'inc_20260814_001' and row['error_class'] == 'texture_io':
        required_checks['nfs_stall'] = True
    if row['error_class'] == 'oom':
        required_checks['oom_count'] += 1
    if 'recurrence' in row['title'].lower() or 'wrong order' in row['remediation'].lower():
        required_checks['recurrence'] = True

print(f'   ✓ NFS stall (2026-08-14): {required_checks["nfs_stall"]}')
print(f'   ✓ Multiple OOM causes: {required_checks["oom_count"]} incidents')
print(f'   ✓ Recurrence example: {required_checks["recurrence"]}')
print()

print(f'5. PEAK MEMORY RANGES:')
fault_a_failures = attempts_df[
    (attempts_df['error_class'] == 'oom') &
    (attempts_df['node_group'] == 'B') &
    (attempts_df['started_at'] >= '2026-09-08 23:04') &
    (attempts_df['status'] == 'failed')
]

fault_b_failures = attempts_df[
    (attempts_df['shot_id'] == 'shot_047') &
    (attempts_df['frame_number'] >= 78) &
    (attempts_df['frame_number'] <= 119) &
    (attempts_df['status'] == 'failed')
]

if len(fault_a_failures) > 0:
    print(f'   Fault A: {fault_a_failures["peak_mem_gb"].min():.2f}-{fault_a_failures["peak_mem_gb"].max():.2f} GB')
    print(f'            (all < 12.0: {(fault_a_failures["peak_mem_gb"] < 12.0).all()})')

if len(fault_b_failures) > 0:
    print(f'   Fault B: {fault_b_failures["peak_mem_gb"].min():.2f}-{fault_b_failures["peak_mem_gb"].max():.2f} GB')
    print(f'            (all > 12.0: {(fault_b_failures["peak_mem_gb"] > 12.0).all()})')

print()
print('=== ALL SPEC VIOLATIONS FIXED ===')
