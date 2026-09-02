#!/usr/bin/env python3
"""
Synthetic render farm failure dataset generator.

Generates a realistic render farm batch failure dataset with injected faults.
Phases:
  1. Fleet: 100 nodes across 3 groups
  2. Content: 50 shots, 12 jobs, frame ranges, artists, assets
  3. Schedule: Clean run ~9,700 tasks with node assignment and timing
  4. Faults: Assign failures to specific tasks
  5. Attempts: Emit all task attempts (success + failures + retries)
  6. Past incidents: Hand-authored incident history
  7. Output: Write Parquet files
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import json

# Global RNG seed
SEED = 20260909
rng = np.random.default_rng(SEED)

# ============================================================================
# Configuration
# ============================================================================

BATCH_START = datetime(2026, 9, 8, 22, 0, 0)
BATCH_END = datetime(2026, 9, 9, 6, 0, 0)
MAINTENANCE_START = datetime(2026, 9, 8, 23, 0, 0)
FAULT_A_ONSET = datetime(2026, 9, 8, 23, 4, 0)
FAULT_C_START = datetime(2026, 9, 9, 2, 8, 0)
FAULT_C_END = datetime(2026, 9, 9, 2, 19, 0)

NODES_PER_GROUP = {"A": 40, "B": 30, "C": 30}
NODE_MEMORY_GB = {"A": 64, "B": 64, "C": 128}
NODE_CORES = {"A": 32, "B": 32, "C": 64}

HAIR_SHADER_SHOTS = {"shot_012", "shot_023", "shot_031", "shot_044"}
HEAVY_SHOT = "shot_047"
HEAVY_FRAMES_START = 78
HEAVY_FRAMES_END = 119

FAULT_A_COUNT = 190
FAULT_B_COUNT = 42
FAULT_C_COUNT = 14
RESIDUAL_COUNT = 48

# Asset environments and artists
ENVIRONMENTS = [
    "env_forest", "env_canyon", "env_city", "env_beach", "env_cave",
    "env_desert", "env_mansion", "env_space", "env_underwater", "env_volcano",
    "env_glacier", "env_tropical", "env_industrial", "env_suburban", "env_village",
    "env_mountain", "env_temple", "env_lab", "env_market", "env_warehouse"
]
ARTISTS = [f"artist_{i:02d}" for i in range(1, 9)]

# ============================================================================
# Phase 1: Fleet
# ============================================================================

def create_farm_nodes():
    """Create farm_nodes table: 100 nodes across 3 groups."""
    nodes = []
    
    for group in ["A", "B", "C"]:
        for i in range(1, NODES_PER_GROUP[group] + 1):
            node_id = f"node_{group.lower()}_{i:02d}"
            # Fleet state AFTER incident and AFTER rollback: B on 7.3.1, A and C on 7.3.0
            version = "7.3.1" if group == "B" else "7.3.0"
            nodes.append({
                "node_id": node_id,
                "node_group": group,
                "mem_gb": NODE_MEMORY_GB[group],
                "cpu_cores": NODE_CORES[group],
                "renderer_version": version,
                "online": True
            })
    
    return pd.DataFrame(nodes)


# ============================================================================
# Phase 2: Content Universe
# ============================================================================

def create_content_universe():
    """
    Create shots with frame ranges, jobs, artists, assets.
    Returns: dict with shots, tasks metadata.
    """
    # 50 shots distributed across 12 jobs (2-7 shots each)
    shots = {}
    job_shot_counts = rng.integers(2, 8, size=12)
    # Ensure sum is 50
    while job_shot_counts.sum() != 50:
        job_shot_counts = rng.integers(2, 8, size=12)
    
    shot_idx = 1
    for job_num, shot_count in enumerate(job_shot_counts, start=1):
        job_id = f"job_{(job_num):04d}"
        for _ in range(shot_count):
            shot_id = f"shot_{shot_idx:03d}"
            
            # Hair shader shots get 380-420 frames, others get 140-210 (balanced to ~9700 total)
            if shot_id in HAIR_SHADER_SHOTS:
                frame_count = rng.integers(380, 421)  # 380-420 frames
            else:
                frame_count = rng.integers(140, 211)  # 140-210 frames
            
            # Assign artist
            artist = rng.choice(ARTISTS)
            
            # Assign asset refs (2-5 paths)
            num_assets = rng.integers(2, 6)
            asset_refs = []
            for _ in range(num_assets):
                env = rng.choice(ENVIRONMENTS)
                texture_idx = rng.integers(1, 6)
                asset_refs.append(f"/assets/{env}/texture_{texture_idx:02d}.tx")
            
            # Hair shader coverage for hair shots
            if shot_id in HAIR_SHADER_SHOTS:
                # ALL frames use hair shader on hair shots
                hair_rate = 1.0
            else:
                hair_rate = 0.0
            
            shots[shot_id] = {
                "job_id": job_id,
                "frame_count": frame_count,
                "submitted_by": artist,
                "asset_refs": asset_refs,
                "hair_rate": hair_rate
            }
            shot_idx += 1
    
    return shots


# ============================================================================
# Phase 3: Schedule Clean Run
# ============================================================================

def schedule_tasks(shots):
    """
    Simulate queue dispatch: nodes pull tasks as they free.
    Returns: list of task records with node_id, started_at, ended_at, frame_weight.
    """
    # Create task list
    tasks = []
    for shot_id, shot_info in shots.items():
        for frame_num in range(1, shot_info["frame_count"] + 1):
            task_id = f"{shot_id}_f{frame_num:04d}"
            tasks.append({
                "task_id": task_id,
                "shot_id": shot_id,
                "frame_number": frame_num,
                "job_id": shot_info["job_id"],
                "submitted_by": shot_info["submitted_by"],
                "asset_refs": shot_info["asset_refs"],
                "hair_rate": shot_info["hair_rate"]
            })
    
    unique_tasks = len(tasks)
    print(f"Generated {unique_tasks} unique tasks")
    
    # Frame weight: smooth function per shot
    frame_weights = {}
    for shot_id in shots:
        frame_count = shots[shot_id]["frame_count"]
        # Create smooth weight curve using sine components
        frames = np.arange(frame_count)
        # Use sum of sines for smooth variation, normalized to [0.4, 1.0]
        weight_curve = (
            0.3 * np.sin(2 * np.pi * frames / frame_count) +
            0.2 * np.sin(4 * np.pi * frames / frame_count) +
            rng.normal(0, 0.05, frame_count)
        )
        weight_curve = (weight_curve - weight_curve.min()) / (weight_curve.max() - weight_curve.min())
        weight_curve = 0.4 + 0.6 * weight_curve
        frame_weights[shot_id] = weight_curve
    
    # For shot_047, make frames 78-119 the heaviest
    if HEAVY_SHOT in frame_weights:
        curve = frame_weights[HEAVY_SHOT]
        curve[HEAVY_FRAMES_START:HEAVY_FRAMES_END+1] = np.linspace(0.95, 1.0, HEAVY_FRAMES_END - HEAVY_FRAMES_START + 1)
    
    # Schedule tasks using queue simulation
    node_free_times = {
        f"node_{g.lower()}_{i:02d}": BATCH_START
        for g in ["A", "B", "C"]
        for i in range(1, NODES_PER_GROUP[g] + 1)
    }
    
    all_nodes = list(node_free_times.keys())
    
    # Sort tasks randomly but deterministically to spread out shot coverage
    # This helps ensure hair shots run in all groups across time periods
    tasks_indexed = [(i, t) for i, t in enumerate(tasks)]
    rng.shuffle(tasks_indexed)
    
    scheduled = []
    for idx, task in tasks_indexed:
        # Pick earliest free node
        earliest_node = min(node_free_times, key=node_free_times.get)
        start_time = node_free_times[earliest_node]
        
        # Duration: lognormal centered ~4.8 min, clipped to [90s, 14min]
        # Using lognormal with appropriate parameters
        duration = rng.lognormal(mean=np.log(4.8 * 60), sigma=0.6)
        duration = np.clip(duration, 90, 840)
        
        end_time = start_time + timedelta(seconds=int(duration))
        node_free_times[earliest_node] = end_time
        
        # Extract group from node_id
        node_group = earliest_node.split("_")[1].upper()
        
        # Renderer version: 7.3.1 if B and after maintenance, else 7.3.0
        if node_group == "B" and start_time >= MAINTENANCE_START:
            renderer_version = "7.3.1"
        else:
            renderer_version = "7.3.0"
        
        # Determine if uses_hair_shader for this frame
        uses_hair_shader = False
        if task["shot_id"] in HAIR_SHADER_SHOTS:
            uses_hair_shader = rng.random() < task["hair_rate"]
        
        frame_idx = task["frame_number"] - 1
        frame_weight = frame_weights[task["shot_id"]][frame_idx]
        
        scheduled.append({
            "task_id": task["task_id"],
            "shot_id": task["shot_id"],
            "frame_number": task["frame_number"],
            "job_id": task["job_id"],
            "node_id": earliest_node,
            "node_group": node_group,
            "started_at": start_time,
            "ended_at": end_time,
            "duration_sec": int(duration),
            "submitted_by": task["submitted_by"],
            "asset_refs": task["asset_refs"],
            "uses_hair_shader": uses_hair_shader,
            "frame_weight": frame_weight,
            "renderer_version": renderer_version
        })
    
    # Verify distribution across groups for hair shots and shot_047
    print(f"\nVerifying task distribution...")
    before_maintenance = [t for t in scheduled if t["started_at"] < MAINTENANCE_START]
    after_maintenance = [t for t in scheduled if t["started_at"] >= MAINTENANCE_START]
    
    # Check hair shader task counts
    total_hair_tasks = sum(1 for t in scheduled if t["uses_hair_shader"])
    hair_after_maintenance = sum(1 for t in after_maintenance if t["uses_hair_shader"])
    hair_b_after_fault_onset = sum(1 for t in after_maintenance if t["uses_hair_shader"] and t["node_group"] == "B" and t["started_at"] >= FAULT_A_ONSET)
    
    print(f"  Total hair shader tasks: {total_hair_tasks}")
    print(f"  Hair tasks after maintenance: {hair_after_maintenance}")
    print(f"  Hair tasks on group B after {FAULT_A_ONSET.strftime('%H:%M')}: {hair_b_after_fault_onset}")
    
    for shot_id in HAIR_SHADER_SHOTS | {HEAVY_SHOT}:
        shot_tasks = [t for t in scheduled if t["shot_id"] == shot_id]
        groups_before = set(t["node_group"] for t in before_maintenance if t["shot_id"] == shot_id)
        groups_after = set(t["node_group"] for t in after_maintenance if t["shot_id"] == shot_id)
        print(f"  {shot_id}: Before 23:00 in {groups_before}, After 23:00 in {groups_after}")
        
        # For hair shots, ensure coverage both before and after 23:00
        if shot_id in HAIR_SHADER_SHOTS:
            # If missing before, manually assign some frames to before 23:00
            if len(groups_before) < 3:
                # Find frames to move earlier
                frames_to_move = [t for t in scheduled if t["shot_id"] == shot_id and t["started_at"] >= MAINTENANCE_START]
                if frames_to_move:
                    # Move first few frames to run before maintenance
                    for i in range(min(3, len(frames_to_move))):
                        frames_to_move[i]["started_at"] = BATCH_START + timedelta(hours=rng.integers(0, 1))
                        frames_to_move[i]["ended_at"] = frames_to_move[i]["started_at"] + timedelta(seconds=frames_to_move[i]["duration_sec"])
            
            if len(groups_after) < 3:
                # Find frames to move later
                frames_to_move = [t for t in scheduled if t["shot_id"] == shot_id and t["started_at"] < MAINTENANCE_START]
                if frames_to_move:
                    # Move last few frames to run after maintenance
                    for i in range(min(3, len(frames_to_move))):
                        frames_to_move[i]["started_at"] = MAINTENANCE_START + timedelta(hours=rng.integers(0, 3))
                        frames_to_move[i]["ended_at"] = frames_to_move[i]["started_at"] + timedelta(seconds=frames_to_move[i]["duration_sec"])
    
    return scheduled


# ============================================================================
# Phase 4: Fault Assignment
# ============================================================================

def assign_faults(scheduled_tasks):
    """
    Assign exactly 294 tasks to faults.
    Returns: dict mapping task_id to fault name or None.
    """
    fault_assignment = {}
    assigned_tasks = set()
    
    # Fault A: exactly 190 tasks
    # Eligible: node_group B AND started_at >= 23:04 AND uses_hair_shader
    fault_a_eligible = [
        t for t in scheduled_tasks
        if t["node_group"] == "B" and t["started_at"] >= FAULT_A_ONSET and t["uses_hair_shader"]
    ]
    
    if len(fault_a_eligible) < 260:
        raise RuntimeError(
            f"Fault A eligibility pool too small: {len(fault_a_eligible)} < 260. "
            "Hair shots not distributed widely enough."
        )
    
    # Sort by frame_weight descending, take top 190
    fault_a_eligible.sort(key=lambda t: t["frame_weight"], reverse=True)
    fault_a_tasks = fault_a_eligible[:FAULT_A_COUNT]
    
    for task in fault_a_tasks:
        fault_assignment[task["task_id"]] = "A"
        assigned_tasks.add(task["task_id"])
    
    print(f"Fault A: {len(fault_a_tasks)} tasks assigned (eligible pool: {len(fault_a_eligible)})")
    
    # Fault B: exactly 42 tasks
    # shot_047, frames 78-119
    fault_b_tasks = [
        t for t in scheduled_tasks
        if t["shot_id"] == HEAVY_SHOT and HEAVY_FRAMES_START <= t["frame_number"] <= HEAVY_FRAMES_END
    ]
    
    assert len(fault_b_tasks) == FAULT_B_COUNT, \
        f"Fault B should have {FAULT_B_COUNT} tasks, got {len(fault_b_tasks)}"
    
    for task in fault_b_tasks:
        fault_assignment[task["task_id"]] = "B"
        assigned_tasks.add(task["task_id"])
    
    print(f"Fault B: {len(fault_b_tasks)} tasks assigned")
    
    # Fault C: exactly 14 tasks
    # Sample uniformly from tasks in 02:08:00-02:19:00 window, excluding assigned
    fault_c_pool = [
        t for t in scheduled_tasks
        if FAULT_C_START <= t["started_at"] <= FAULT_C_END and t["task_id"] not in assigned_tasks
    ]
    
    # Resample if too many from one group or one shot
    max_iterations = 100
    for iteration in range(max_iterations):
        fault_c_candidates = rng.choice(len(fault_c_pool), size=FAULT_C_COUNT, replace=False)
        fault_c_tasks = [fault_c_pool[i] for i in sorted(fault_c_candidates)]
        
        # Check constraints
        group_counts = {}
        shot_counts = {}
        for task in fault_c_tasks:
            group_counts[task["node_group"]] = group_counts.get(task["node_group"], 0) + 1
            shot_counts[task["shot_id"]] = shot_counts.get(task["shot_id"], 0) + 1
        
        if max(group_counts.values()) <= 6 and max(shot_counts.values()) <= 3:
            break
    
    for task in fault_c_tasks:
        fault_assignment[task["task_id"]] = "C"
        assigned_tasks.add(task["task_id"])
    
    print(f"Fault C: {len(fault_c_tasks)} tasks assigned")
    
    # Residual: exactly 48 tasks
    # Uniform random draw from remaining unassigned
    residual_pool = [t for t in scheduled_tasks if t["task_id"] not in assigned_tasks]
    residual_indices = rng.choice(len(residual_pool), size=RESIDUAL_COUNT, replace=False)
    residual_tasks = [residual_pool[i] for i in residual_indices]
    
    for task in residual_tasks:
        fault_assignment[task["task_id"]] = "residual"
        assigned_tasks.add(task["task_id"])
    
    print(f"Residual: {len(residual_tasks)} tasks assigned")
    print(f"Total assigned: {len(assigned_tasks)}")
    
    return fault_assignment


# ============================================================================
# Phase 5: Emit Attempts
# ============================================================================

def emit_attempts(scheduled_tasks, fault_assignment, shots):
    """
    Emit all task attempts: attempt 1 (with failures), and attempt 2 (retries).
    Returns: DataFrame of all attempts.
    """
    attempts = []
    all_nodes = []
    for group in ["A", "B", "C"]:
        for i in range(1, NODES_PER_GROUP[group] + 1):
            all_nodes.append(f"node_{group.lower()}_{i:02d}")
    
    # Convert to numpy array for consistent behavior
    all_nodes = np.array(all_nodes)
    
    # DEBUG: Verify all_nodes structure
    group_counts = {"A": 0, "B": 0, "C": 0}
    for node in all_nodes:
        group = str(node).split("_")[1].upper()
        group_counts[group] += 1
    print(f"  DEBUG: all_nodes has {len(all_nodes)} nodes: A={group_counts['A']}, B={group_counts['B']}, C={group_counts['C']}")
    
    # DEBUG: Track retry nodes and indices for Fault A
    fault_a_retry_nodes = []
    fault_a_retry_indices = []
    
    for task in scheduled_tasks:
        task_id = task["task_id"]
        fault = fault_assignment.get(task_id)
        is_failed = fault is not None
        task_id = task["task_id"]
        fault = fault_assignment.get(task_id)
        is_failed = fault is not None
        
        # Attempt 1
        if is_failed:
            status = "failed"
            error_class, error_text = generate_error(
                fault, task, is_retry=False, shots=shots
            )
            peak_mem_gb = generate_peak_memory(fault, task, is_retry=False)
        else:
            status = "success"
            error_class = None
            error_text = None
            peak_mem_gb = generate_peak_memory(None, task, is_retry=False)
        
        attempts.append({
            "task_id": task_id,
            "job_id": task["job_id"],
            "shot_id": task["shot_id"],
            "frame_number": task["frame_number"],
            "node_id": task["node_id"],
            "node_group": task["node_group"],
            "attempt": 1,
            "status": status,
            "started_at": task["started_at"],
            "ended_at": task["ended_at"],
            "error_class": error_class,
            "error_text": error_text,
            "peak_mem_gb": peak_mem_gb,
            "mem_allocated_gb": 12.0,
            "renderer_version": task["renderer_version"],
            "uses_hair_shader": task["uses_hair_shader"],
            "asset_refs": task["asset_refs"],
            "submitted_by": task["submitted_by"]
        })
        
        # Attempt 2 (retry)
        if is_failed:
            # Retry after 2-8 minutes
            retry_delay = int(rng.integers(120, 480))
            retry_start = task["ended_at"] + timedelta(seconds=retry_delay)
            
            # Retry duration (slightly different from first attempt)
            retry_duration = int(rng.lognormal(mean=np.log(4.8 * 60), sigma=0.6))
            retry_duration = int(np.clip(retry_duration, 90, 840))
            retry_end = retry_start + timedelta(seconds=retry_duration)
            
            # Retry node: uniform random from all 100 nodes (by index)
            retry_node_idx = rng.integers(0, len(all_nodes))
            retry_node = str(all_nodes[retry_node_idx])
            retry_group = retry_node.split("_")[1].upper()
            
            # DEBUG: Track retry indices and nodes for Fault A
            if fault == "A":
                fault_a_retry_indices.append(retry_node_idx)
                fault_a_retry_nodes.append(retry_node)
            
            # Retry version based on node and time
            if retry_group == "B" and retry_start >= MAINTENANCE_START:
                retry_version = "7.3.1"
            else:
                retry_version = "7.3.0"
            
            # Retry outcome
            if fault == "A":
                # Fail only if retries back to group B
                retry_status = "failed" if retry_group == "B" else "success"
                retry_error_class, retry_error_text = (
                    generate_error(fault, task, is_retry=True, retry_group=retry_group, shots=shots)
                    if retry_status == "failed" else (None, None)
                )
                retry_peak_mem = generate_peak_memory(
                    fault if retry_status == "failed" else None, task, is_retry=True
                )
            elif fault == "B":
                # Always fail
                retry_status = "failed"
                retry_error_class, retry_error_text = generate_error(
                    fault, task, is_retry=True, shots=shots
                )
                retry_peak_mem = generate_peak_memory(fault, task, is_retry=True)
            elif fault in ["C", "residual"]:
                # Always succeed
                retry_status = "success"
                retry_error_class = None
                retry_error_text = None
                retry_peak_mem = generate_peak_memory(None, task, is_retry=True)
            
            attempts.append({
                "task_id": task_id,
                "job_id": task["job_id"],
                "shot_id": task["shot_id"],
                "frame_number": task["frame_number"],
                "node_id": retry_node,
                "node_group": retry_group,
                "attempt": 2,
                "status": retry_status,
                "started_at": retry_start,
                "ended_at": retry_end,
                "error_class": retry_error_class,
                "error_text": retry_error_text,
                "peak_mem_gb": retry_peak_mem,
                "mem_allocated_gb": 12.0,
                "renderer_version": retry_version,
                "uses_hair_shader": task["uses_hair_shader"],
                "asset_refs": task["asset_refs"],
                "submitted_by": task["submitted_by"]
            })
    
    # DEBUG: Print sample of retry nodes for verification
    if fault_a_retry_nodes:
        sample_nodes = fault_a_retry_nodes[:5]
        print(f"  DEBUG: Sample Fault A retry nodes: {sample_nodes}")
        node_types = [n.split('_')[1].upper() for n in fault_a_retry_nodes]
        print(f"  DEBUG: Fault A retry node groups: A={node_types.count('A')}, B={node_types.count('B')}, C={node_types.count('C')}")
        
        # Analyze index distribution
        if fault_a_retry_indices:
            group_from_indices = {"A": 0, "B": 0, "C": 0}
            for idx in fault_a_retry_indices:
                if idx < 40:
                    group_from_indices["A"] += 1
                elif idx < 70:
                    group_from_indices["B"] += 1
                else:
                    group_from_indices["C"] += 1
            print(f"  DEBUG: Groups from indices: A={group_from_indices['A']}, B={group_from_indices['B']}, C={group_from_indices['C']}")
            print(f"  DEBUG: Sample Fault A retry indices (first 20): {fault_a_retry_indices[:20]}")
    
    return pd.DataFrame(attempts)


def generate_error(fault, task, is_retry=False, retry_group=None, shots=None):
    """Generate error_class and error_text for a failed task."""
    if fault == "A" or fault == "B":
        error_class = "oom"
        # Generate OOM message with self-consistent byte figure
        elapsed_min = rng.integers(1, 5)
        elapsed_sec = rng.integers(0, 60)
        elapsed_str = f"00:{elapsed_min:02d}:{elapsed_sec:02d}"
        
        # Pick MB figure
        mb_figure = rng.choice([61204, 62144, 63024, 64512, 61024])
        
        # Pick byte allocation (power of 2 ish)
        byte_alloc = rng.choice([2147483648, 1073741824, 536870912, 1610612736])
        
        error_text = (
            f"{elapsed_str} {mb_figure}MB ERROR | can't allocate {byte_alloc} bytes "
            f"with alignment 64 in ?:?():0 (virtual memory : 65536 Mb)\n"
            f"{elapsed_str} {mb_figure}MB WARNING | render terminating early: out of memory"
        )
    elif fault == "C":
        error_class = "texture_io"
        # Pick an asset from the task's refs
        asset_path = rng.choice(task["asset_refs"]) if task["asset_refs"] else "/assets/env_forest/texture_01.tx"
        elapsed_min = rng.integers(0, 1)
        elapsed_sec = rng.integers(0, 60)
        elapsed_str = f"00:{elapsed_min:02d}:{elapsed_sec:02d}"
        
        error_text = (
            f"{elapsed_str} 8842MB ERROR | [texturesys] {asset_path}: "
            f"Invalid image file \"{asset_path}\": read error: Input/output error\n"
            f"{elapsed_str} 8842MB WARNING | [kick] render aborted due to earlier errors"
        )
    else:  # residual
        error_classes = ["license_timeout", "disk_full", "frame_write_corrupt", "segfault", "stale_mount"]
        error_class = rng.choice(error_classes)
        
        if error_class == "license_timeout":
            error_text = "00:02:15 8842MB ERROR | License checkout timeout (waited 120s)"
        elif error_class == "disk_full":
            error_text = "00:03:45 8842MB ERROR | Disk full: /scratch/frame_001234.exr"
        elif error_class == "frame_write_corrupt":
            error_text = "00:04:22 8842MB ERROR | Frame write failed: corruption detected in exr header"
        elif error_class == "segfault":
            error_text = "00:01:08 8842MB ERROR | Segmentation fault (core dumped) in arnold kick"
        else:  # stale_mount
            error_text = "00:00:45 8842MB ERROR | Stale NFS mount: /mnt/assets"
    
    return error_class, error_text


def generate_peak_memory(fault, task, is_retry=False):
    """Generate peak_mem_gb for a task."""
    base_peak = 6.0 + 5.0 * task["frame_weight"]
    
    if fault is None:
        # Success path
        peak = base_peak + rng.normal(0, 0.1)
        peak = np.clip(peak, 5.5, 11.6)
        
        # Special case: group B hair-shader success after 23:00 get 30% inflation
        if (task["node_group"] == "B" and task["started_at"] >= MAINTENANCE_START and
            task["uses_hair_shader"]):
            peak = peak * 1.30
            peak = np.clip(peak, 6.0, 11.9)
        
        return float(np.round(peak, 2))
    
    elif fault == "A":
        # Failure: under 12.0 (contrast with B)
        peak = np.clip(rng.normal(11.8, 0.15), 0, 11.95)
        return float(np.round(peak, 2))
    
    elif fault == "B":
        # Failure: over 12.0
        peak = np.clip(rng.normal(14.2, 0.20), 13.6, 20.0)
        return float(np.round(peak, 2))
    
    elif fault in ["C", "residual"]:
        # Unrelated to memory, use normal success value
        peak = base_peak + rng.normal(0, 0.1)
        peak = np.clip(peak, 5.5, 11.6)
        return float(np.round(peak, 2))


# ============================================================================
# Phase 6: Past Incidents
# ============================================================================

PAST_INCIDENTS = [
    {
        "incident_id": "inc_20260814_001",
        "occurred_on": "2026-08-14",
        "title": "NFS texture filer stall",
        "error_class": "texture_io",
        "symptom_summary": "14 tasks failed with texture read timeouts in a 12-minute window",
        "dimension_signature": "timestamp cluster 02:15-02:27, no node or shot pattern",
        "root_cause": "Brief NFS stall on texture filer. Self-resolved after 12 minutes.",
        "remediation": "Re-queue 14 tasks as-is, no code or infrastructure change needed.",
        "outcome": "resolved",
        "time_to_resolve_min": 45
    },
    {
        "incident_id": "inc_20260721_001",
        "occurred_on": "2026-07-21",
        "title": "Hair shader memory regression (old Arnold)",
        "error_class": "oom",
        "symptom_summary": "108 failures on group C (old cluster), all hair-shader scenes",
        "dimension_signature": "shot_id + node_group concentration, ~90 failed tasks",
        "root_cause": "Arnold 7.1.0 on group C had a hair shader memory leak. Unrelated to current 7.3.1 regression.",
        "remediation": "Upgrade group C to Arnold 7.2.1. Did not recur.",
        "outcome": "resolved",
        "time_to_resolve_min": 240
    },
    {
        "incident_id": "inc_20260805_001",
        "occurred_on": "2026-08-05",
        "title": "Subdivision surface subdivision overflow",
        "error_class": "oom",
        "symptom_summary": "67 failures on shot_003 only, frames 40-110 (contiguous heavy frame range)",
        "dimension_signature": "shot_id + frame_number clustering, all groups equally",
        "root_cause": "Artist pushed subdivision level to 4 on a cage with 50k polygons. Peak geometry ~8M polys at render time, blew out 12GB allocation.",
        "remediation": "Bump shot_003 allocation to 18GB, target group C. Artist reduced subdivision to level 2 for future shots.",
        "outcome": "resolved",
        "time_to_resolve_min": 90
    },
    {
        "incident_id": "inc_20260820_001",
        "occurred_on": "2026-08-20",
        "title": "Group A node DIMM failure (recurrence)",
        "error_class": "oom",
        "symptom_summary": "12 failures on tasks dispatched to node_a_18 only",
        "dimension_signature": "node_id concentration, all tasks on one bad node",
        "root_cause": "DIMM failure on node_a_18 made available memory ~48GB instead of 64GB. First fixed by draining node, then DIMM was replaced.",
        "remediation": "Drain node_a_18. This is the SAME root cause as 2026-08-19, but remediation was forgotten yesterday. Node re-brought online after hardware replacement on 08-21.",
        "outcome": "resolved",
        "time_to_resolve_min": 1440
    },
    {
        "incident_id": "inc_20260819_001",
        "occurred_on": "2026-08-19",
        "title": "Group A node DIMM failure (original)",
        "error_class": "oom",
        "symptom_summary": "11 failures on node_a_18 only",
        "dimension_signature": "node_id: node_a_18",
        "root_cause": "DIMM failure left node_a_18 with ~48GB usable memory. Tasks fit on other nodes.",
        "remediation": "Drain node_a_18. Schedule maintenance window for hardware replacement.",
        "outcome": "resolved",
        "time_to_resolve_min": 240
    },
    {
        "incident_id": "inc_20260610_001",
        "occurred_on": "2026-06-10",
        "title": "License server timeout cascade",
        "error_class": "license_timeout",
        "symptom_summary": "Scattered ~30 failures across all groups in a 8-minute window (23:12-23:20)",
        "dimension_signature": "timestamp cluster only, no other pattern",
        "root_cause": "License server briefly unresponsive. Checkout requests queued, some timed out.",
        "remediation": "Increase license checkout timeout from 60s to 90s. Re-queue as-is.",
        "outcome": "resolved",
        "time_to_resolve_min": 30
    },
    {
        "incident_id": "inc_20260525_001",
        "occurred_on": "2026-05-25",
        "title": "Corrupt scratch disk frame write",
        "error_class": "frame_write_corrupt",
        "symptom_summary": "Single task shot_022_f0088 failed with frame file corruption",
        "dimension_signature": "Isolated single task, no cluster",
        "root_cause": "Transient disk sector error on /scratch during frame write.",
        "remediation": "Re-queue the one task. No systemic issue.",
        "outcome": "resolved",
        "time_to_resolve_min": 5
    },
    {
        "incident_id": "inc_20260410_001",
        "occurred_on": "2026-04-10",
        "title": "Scheduler crash during batch",
        "error_class": "segfault",
        "symptom_summary": "12 in-flight tasks killed abruptly by scheduler restart",
        "dimension_signature": "All occurred within 2-minute window, scattered across shots/nodes",
        "root_cause": "Scheduler daemon segfaulted on an edge case in job dependency parsing. Restarted by watchdog.",
        "remediation": "Restart scheduler. Upgrade to fixed version. Re-queue the 12 tasks.",
        "outcome": "resolved",
        "time_to_resolve_min": 15
    },
    {
        "incident_id": "inc_20260315_001",
        "occurred_on": "2026-03-15",
        "title": "NFS filer maintenance window forgotten",
        "error_class": "stale_mount",
        "symptom_summary": "~8 random tasks across all groups failed with stale mount, 00:15-00:22",
        "dimension_signature": "timestamp cluster, no node or shot pattern",
        "root_cause": "Filer maintenance took asset mount offline for 10 minutes without a maintenance window broadcast.",
        "remediation": "Re-queue. Add mount monitoring to alert page.",
        "outcome": "resolved",
        "time_to_resolve_min": 20
    },
    {
        "incident_id": "inc_20260228_001",
        "occurred_on": "2026-02-28",
        "title": "Disk full on render node group",
        "error_class": "disk_full",
        "symptom_summary": "9 failures on nodes in group B only, /scratch full",
        "dimension_signature": "node_group = B cluster",
        "root_cause": "Scratch cleanup script failed (cron misconfiguration). /scratch filled overnight.",
        "remediation": "Purge /scratch on group B nodes. Fix cron job. Re-queue 9 tasks to other groups if possible.",
        "outcome": "resolved",
        "time_to_resolve_min": 60
    },
    {
        "incident_id": "inc_20260110_001",
        "occurred_on": "2026-01-10",
        "title": "Database connectivity spike",
        "error_class": "license_timeout",
        "symptom_summary": "~5 license checkout timeouts scattered over 15 minutes",
        "dimension_signature": "Isolated timeouts, no pattern",
        "root_cause": "Database backing license server experienced a 30-second spike in query latency.",
        "remediation": "No action on farm side. Database team added connection pooling. Re-queue.",
        "outcome": "resolved",
        "time_to_resolve_min": 25
    },
    {
        "incident_id": "inc_20250925_001",
        "occurred_on": "2025-09-25",
        "title": "Typo in render command",
        "error_class": "segfault",
        "symptom_summary": "Single shot (shot_005) all frames failed with segfault across all groups",
        "dimension_signature": "shot_id: shot_005 only, all 180 frames",
        "root_cause": "Artist uploaded scene with typo in mel expression that dereferenced null at render kickoff.",
        "remediation": "Artist fixed scene, re-uploaded, re-queue 180 tasks.",
        "outcome": "resolved",
        "time_to_resolve_min": 45
    },
    {
        "incident_id": "inc_20260812_001",
        "occurred_on": "2026-08-12",
        "title": "Texture cache memory leak on group A",
        "error_class": "oom",
        "symptom_summary": "37 failures on group A only, unrelated shots, over 45-minute span",
        "dimension_signature": "node_group = A, scattered across shots and time",
        "root_cause": "Texture cache on group A nodes leaked 2-3GB per render pass. Symptoms grew over the first 2 hours as cache filled. Unrelated to scene content or shader type.",
        "remediation": "Restart kick daemon on all group A nodes. Drain nodes during maintenance. Upgrade Arnold to version without the leak.",
        "outcome": "resolved",
        "time_to_resolve_min": 420
    },
    {
        "incident_id": "inc_20260701_001",
        "occurred_on": "2026-07-01",
        "title": "Memory regression missed wrong order of rollback",
        "error_class": "oom",
        "symptom_summary": "45 task failures on group B between 14:30-15:20, did not recur after remediation",
        "dimension_signature": "node_group = B, time cluster, hair-shader scenes only",
        "root_cause": "Arnold 7.2.5 pushed to group B at 14:00 with hair shader regression. Re-queue was attempted at 14:45 but without the rollback first: ~30% of re-queued tasks landed back on 7.2.5 and failed again. Final fix: rollback to 7.2.4 first, then re-queue.",
        "remediation": "Rollback group B to Arnold 7.2.4. Wait 10 minutes. Re-queue 45 tasks. Order matters: rollback precedes re-queue.",
        "outcome": "resolved",
        "time_to_resolve_min": 180
    }
]


def create_past_incidents_df():
    """Convert PAST_INCIDENTS to DataFrame."""
    return pd.DataFrame(PAST_INCIDENTS)


# ============================================================================
# Phase 7: Output
# ============================================================================

def save_parquet_files(attempts_df, farm_nodes_df, incidents_df):
    """Write Parquet files."""
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)
    
    # Write attempts
    attempts_df.to_parquet(output_dir / "attempts.parquet", index=False, engine="pyarrow")
    print(f"Wrote {len(attempts_df)} rows to data/attempts.parquet")
    
    # Write farm_nodes
    farm_nodes_df.to_parquet(output_dir / "farm_nodes.parquet", index=False, engine="pyarrow")
    print(f"Wrote {len(farm_nodes_df)} rows to data/farm_nodes.parquet")
    
    # Write past_incidents
    incidents_df.to_parquet(output_dir / "past_incidents.parquet", index=False, engine="pyarrow")
    print(f"Wrote {len(incidents_df)} rows to data/past_incidents.parquet")


# ============================================================================
# Main
# ============================================================================

def main():
    print("Render Farm Failure Dataset Generator")
    print("=" * 70)
    print(f"Seed: {SEED}")
    print(f"Batch window: {BATCH_START} to {BATCH_END}")
    print()
    
    # Phase 1: Fleet
    print("Phase 1: Creating farm nodes...")
    farm_nodes_df = create_farm_nodes()
    print(f"  {len(farm_nodes_df)} nodes created")
    
    # Phase 2: Content universe
    print("Phase 2: Creating content universe...")
    shots = create_content_universe()
    print(f"  {len(shots)} shots created")
    print(f"  Hair shader shots: {HAIR_SHADER_SHOTS}")
    print(f"  Heavy shot: {HEAVY_SHOT}")
    
    # Phase 3: Schedule clean run
    print("Phase 3: Scheduling clean run...")
    scheduled_tasks = schedule_tasks(shots)
    print(f"  {len(scheduled_tasks)} task attempts scheduled")
    
    # Phase 4: Fault assignment
    print("Phase 4: Assigning faults...")
    fault_assignment = assign_faults(scheduled_tasks)
    
    # Phase 5: Emit attempts
    print("Phase 5: Emitting attempts...")
    attempts_df = emit_attempts(scheduled_tasks, fault_assignment, shots)
    print(f"  {len(attempts_df)} total attempt records")
    
    # Phase 6: Past incidents
    print("Phase 6: Creating past incidents...")
    incidents_df = create_past_incidents_df()
    print(f"  {len(incidents_df)} incident records")
    
    # Phase 7: Output
    print("Phase 7: Writing output files...")
    save_parquet_files(attempts_df, farm_nodes_df, incidents_df)
    
    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    # Failure analysis
    failures = attempts_df[attempts_df["status"] == "failed"]
    success = attempts_df[attempts_df["status"] == "success"]
    
    # Count by fault
    fault_a_rows = len(attempts_df[(attempts_df["task_id"].isin(
        [t["task_id"] for t in scheduled_tasks if fault_assignment.get(t["task_id"]) == "A"]
    )) & (attempts_df["attempt"] == 1)])
    fault_b_rows = len(attempts_df[(attempts_df["task_id"].isin(
        [t["task_id"] for t in scheduled_tasks if fault_assignment.get(t["task_id"]) == "B"]
    )) & (attempts_df["attempt"] == 1)])
    fault_c_rows = len(attempts_df[(attempts_df["task_id"].isin(
        [t["task_id"] for t in scheduled_tasks if fault_assignment.get(t["task_id"]) == "C"]
    )) & (attempts_df["attempt"] == 1)])
    residual_rows = len(attempts_df[(attempts_df["task_id"].isin(
        [t["task_id"] for t in scheduled_tasks if fault_assignment.get(t["task_id"]) == "residual"]
    )) & (attempts_df["attempt"] == 1)])
    
    print(f"Total attempts: {len(attempts_df)}")
    print(f"Total failure rows: {len(failures)}")
    print(f"Total success rows: {len(success)}")
    print()
    print(f"Failure breakdown (attempt 1 only):")
    print(f"  Fault A: {fault_a_rows}")
    print(f"  Fault B: {fault_b_rows}")
    print(f"  Fault C: {fault_c_rows}")
    print(f"  Residual: {residual_rows}")
    print()
    
    # Unique task counts
    unique_tasks = len(attempts_df["task_id"].unique())
    print(f"Unique tasks: {unique_tasks}")
    
    # Retry outcomes and node distribution
    print()
    print("Retry signatures (second-attempt failure rate):")
    for fault_name in ["A", "B", "C", "residual"]:
        if fault_name == "residual":
            fault_tasks = set(t["task_id"] for t in scheduled_tasks if fault_assignment.get(t["task_id"]) == "residual")
        else:
            fault_tasks = set(t["task_id"] for t in scheduled_tasks if fault_assignment.get(t["task_id"]) == fault_name)
        
        fault_retries = attempts_df[(attempts_df["task_id"].isin(fault_tasks)) & (attempts_df["attempt"] == 2)]
        if len(fault_retries) > 0:
            failure_rate = len(fault_retries[fault_retries["status"] == "failed"]) / len(fault_retries)
            print(f"  Fault {fault_name}: {failure_rate:.1%} ({len(fault_retries[fault_retries['status'] == 'failed'])}/{len(fault_retries)})")
            
            # For Fault A, show retry node distribution
            if fault_name == "A":
                retry_group_counts = fault_retries["node_group"].value_counts().to_dict()
                print(f"    Fault A retry node distribution: A={retry_group_counts.get('A', 0)}, B={retry_group_counts.get('B', 0)}, C={retry_group_counts.get('C', 0)}")
    
    # Memory ranges for failures
    print()
    print("Peak memory for failures:")
    fault_a_failures = attempts_df[(attempts_df["task_id"].isin(
        [t["task_id"] for t in scheduled_tasks if fault_assignment.get(t["task_id"]) == "A"]
    )) & (attempts_df["status"] == "failed")]
    fault_b_failures = attempts_df[(attempts_df["task_id"].isin(
        [t["task_id"] for t in scheduled_tasks if fault_assignment.get(t["task_id"]) == "B"]
    )) & (attempts_df["status"] == "failed")]
    
    if len(fault_a_failures) > 0:
        print(f"  Fault A: min={fault_a_failures['peak_mem_gb'].min():.2f} GB, max={fault_a_failures['peak_mem_gb'].max():.2f} GB")
    if len(fault_b_failures) > 0:
        print(f"  Fault B: min={fault_b_failures['peak_mem_gb'].min():.2f} GB, max={fault_b_failures['peak_mem_gb'].max():.2f} GB")
    
    # Assertions
    print()
    print("Assertions:")
    assert len(attempts_df) >= 9900 and len(attempts_df) <= 10100, \
        f"Total attempts {len(attempts_df)} not in [9900, 10100]"
    print(f"  ✓ Total attempts in [9900, 10100]: {len(attempts_df)}")
    
    assert unique_tasks >= 9600 and unique_tasks <= 9800, \
        f"Unique tasks {unique_tasks} not in [9600, 9800]"
    print(f"  ✓ Unique tasks in [9600, 9800]: {unique_tasks}")
    
    assert fault_a_rows == 190, f"Fault A row count {fault_a_rows} != 190"
    print(f"  ✓ Fault A exactly 190 tasks: {fault_a_rows}")
    
    assert len(incidents_df) == 14, f"Past incidents {len(incidents_df)} != 14"
    print(f"  ✓ Past incidents exactly 14: {len(incidents_df)}")
    
    print()
    print("=" * 70)
    print("Dataset generation complete!")
    print(f"Seed: {SEED}")


if __name__ == "__main__":
    main()
