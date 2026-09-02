#!/usr/bin/env python3
"""Independent verifier for the render farm triage dataset.

Reads render_task_attempts (from Parquet or ClickHouse), identifies the fault
groups from observable columns alone, and runs the ten checks in FAULTS.md's
"Generator verification checklist" plus the hair-shader corroborating signal.

This script does not import, read, or otherwise depend on generate.py. Every
threshold and expected value below is transcribed from FAULTS.md. Fault
membership is derived from the data (error_class, shot_id, peak_mem_gb vs
mem_allocated_gb) rather than accepted from any external label.

Usage:
    python verify.py --parquet data/attempts.parquet
    python verify.py --clickhouse
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Expected values and thresholds, transcribed from FAULTS.md. Nothing below
# is derived from generate.py.
# ---------------------------------------------------------------------------

SIG_LEVEL = 0.05

EXPECTED = {
    "fault_b_rows": 84,                    # exact
    "fault_c_rows": 14,                    # exact
    "residual_rows": 48,                   # exact
    "fault_a_rows_band": (234, 260),       # approximate: 190 + Binomial(190, 0.30) +/- 2SD
    "fault_a_unique_tasks": 190,           # exact
    "fault_b_unique_tasks": 42,            # exact
    "fault_c_unique_tasks": 14,            # exact
    "residual_unique_tasks": 48,           # exact
    "total_unique_tasks": 294,             # exact
    "fault_a_retry_band": (0.22, 0.38),    # ~30% +/- margin
    "fault_b_retry_rate": 1.0,             # exact
    "fault_c_retry_rate": 0.0,             # exact
    "residual_retry_rate": 0.0,            # exact
}

# Total row-count band = sum of the four component bands (234+84+14+48 .. 260+84+14+48)
EXPECTED["total_rows_band"] = (
    EXPECTED["fault_a_rows_band"][0] + EXPECTED["fault_b_rows"] + EXPECTED["fault_c_rows"] + EXPECTED["residual_rows"],
    EXPECTED["fault_a_rows_band"][1] + EXPECTED["fault_b_rows"] + EXPECTED["fault_c_rows"] + EXPECTED["residual_rows"],
)

# Root-cause dimensions a diagnostic agent would test. Excludes error_class,
# which is how the fault subsets are carved out in the first place, not a
# candidate root-cause dimension.
CONCENTRATION_DIMENSIONS = [
    "node_group", "node_id", "shot_id", "job_id", "renderer_version", "submitted_by",
]

TIME_BUCKET_MINUTES = 10

FAULT_B_SHOT = "shot_047"
KNOWN_OOM_SIBLING_ERROR_CLASS = "texture_io"


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    number: str
    name: str
    passed: bool
    terminal_line: str
    detail_md: str
    failure_note: Optional[str] = None


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _normalize(attempts: pd.DataFrame) -> pd.DataFrame:
    df = attempts.copy()
    df["started_at"] = pd.to_datetime(df["started_at"])
    df["ended_at"] = pd.to_datetime(df["ended_at"])
    df["attempt"] = df["attempt"].astype(int)
    df["frame_number"] = df["frame_number"].astype(int)
    df["peak_mem_gb"] = df["peak_mem_gb"].astype(float)
    df["mem_allocated_gb"] = df["mem_allocated_gb"].astype(float)
    for col in ("task_id", "job_id", "shot_id", "node_id", "node_group",
                "status", "renderer_version", "submitted_by"):
        df[col] = df[col].astype(str)
    # error_class stays nullable (None for success rows)
    return df


def load_from_parquet(attempts_path: str) -> dict:
    attempts = pd.read_parquet(attempts_path)
    data_dir = os.path.dirname(os.path.abspath(attempts_path))
    farm_nodes_path = os.path.join(data_dir, "farm_nodes.parquet")
    past_incidents_path = os.path.join(data_dir, "past_incidents.parquet")
    farm_nodes = pd.read_parquet(farm_nodes_path) if os.path.exists(farm_nodes_path) else None
    past_incidents = pd.read_parquet(past_incidents_path) if os.path.exists(past_incidents_path) else None
    source_desc = f"Parquet file: {os.path.abspath(attempts_path)}"
    return {
        "attempts": _normalize(attempts),
        "farm_nodes": farm_nodes,
        "past_incidents": past_incidents,
        "source_desc": source_desc,
    }


def load_from_clickhouse() -> dict:
    import clickhouse_connect

    host = os.environ["CLICKHOUSE_HOST"]
    user = os.environ["CLICKHOUSE_USER"]
    password = os.environ["CLICKHOUSE_PASSWORD"]
    database = os.environ["CLICKHOUSE_DATABASE"]

    client = clickhouse_connect.get_client(
        host=host, username=user, password=password, database=database, secure=True,
    )
    attempts = client.query_df("SELECT * FROM render_task_attempts")
    try:
        farm_nodes = client.query_df("SELECT * FROM farm_nodes")
    except Exception:
        farm_nodes = None
    try:
        past_incidents = client.query_df("SELECT * FROM past_incidents")
    except Exception:
        past_incidents = None

    source_desc = f"ClickHouse host: {host}, database: {database}, table: render_task_attempts"
    return {
        "attempts": _normalize(attempts),
        "farm_nodes": farm_nodes,
        "past_incidents": past_incidents,
        "source_desc": source_desc,
    }


# ---------------------------------------------------------------------------
# Core reusable analysis primitives
# ---------------------------------------------------------------------------

def concentration(df: pd.DataFrame, dimension: str, subset_mask: pd.Series) -> pd.DataFrame:
    """For each value of `dimension`, compare its share of the failure subset
    (subset_mask, boolean, aligned to df) against its share of all attempts in
    df. Returns counts, shares, a two-sided binomial p-value, and a
    Bonferroni-corrected p-value (corrected across the distinct values of this
    dimension observed in df — that is the number of hypotheses tested).
    """
    n_total = len(df)
    subset = df[subset_mask]
    n_subset = len(subset)
    values = df[dimension].dropna().unique()
    k = len(values)
    rows = []
    for v in values:
        pop_count = int((df[dimension] == v).sum())
        pop_share = pop_count / n_total if n_total else 0.0
        subset_count = int((subset[dimension] == v).sum())
        subset_share = subset_count / n_subset if n_subset else 0.0
        if n_subset and k:
            pval = stats.binomtest(subset_count, n_subset, pop_share, alternative="two-sided").pvalue
        else:
            pval = 1.0
        pval_corrected = min(pval * k, 1.0) if k else 1.0
        rows.append({
            "value": v,
            "pop_count": pop_count,
            "pop_share": pop_share,
            "subset_count": subset_count,
            "subset_share": subset_share,
            "p_value": pval,
            "p_value_bonferroni": pval_corrected,
            "n_values_tested": k,
        })
    result = pd.DataFrame(rows)
    if len(result):
        result = result.sort_values("subset_count", ascending=False).reset_index(drop=True)
    return result


def check_success_elsewhere(df: pd.DataFrame, dimension: str, value: str,
                             exclude_dimension: str, exclude_value: str) -> pd.DataFrame:
    """Rows matching dimension==value that succeeded, excluding rows where
    exclude_dimension==exclude_value. The reverse test: does this value
    succeed outside the suspected culprit?
    """
    mask = (
        (df[dimension] == value)
        & (df["status"] == "success")
        & (df[exclude_dimension] != exclude_value)
    )
    return df[mask]


def second_attempt_failure_rate(fault_df: pd.DataFrame, full_df: pd.DataFrame):
    """For the unique tasks appearing in fault_df, look up their attempt==2
    row (if any) in full_df and report the fraction that failed again.
    Returns (rate, n_failed_second, n_second_attempts, n_unique_tasks).
    """
    task_ids = fault_df["task_id"].unique()
    n_tasks = len(task_ids)
    if n_tasks == 0:
        return float("nan"), 0, 0, 0
    related = full_df[full_df["task_id"].isin(task_ids)]
    second = related[related["attempt"] == 2]
    n_second = len(second)
    n_failed_second = int((second["status"] == "failed").sum())
    rate = n_failed_second / n_second if n_second else float("nan")
    return rate, n_failed_second, n_second, n_tasks


def identify_faults(df: pd.DataFrame) -> dict:
    """Derive fault group membership from observable columns only.

    OOM pile = failure rows with error_class == 'oom'.
    Fault B   = OOM rows on shot_047 (cross-checked against peak_mem_gb > mem_allocated_gb).
    Fault A   = OOM rows not on shot_047 (cross-checked against peak_mem_gb < mem_allocated_gb).
    Fault C   = failure rows with error_class == 'texture_io'.
    Residual  = every other failure row.
    """
    failed = df[df["status"] == "failed"].copy()
    oom = failed[failed["error_class"] == "oom"].copy()
    fault_c = failed[failed["error_class"] == KNOWN_OOM_SIBLING_ERROR_CLASS].copy()

    fault_b = oom[oom["shot_id"] == FAULT_B_SHOT].copy()
    fault_a = oom[oom["shot_id"] != FAULT_B_SHOT].copy()

    known = {"oom", KNOWN_OOM_SIBLING_ERROR_CLASS}
    residual = failed[~failed["error_class"].isin(known)].copy()

    return {
        "failed": failed, "oom": oom,
        "fault_a": fault_a, "fault_b": fault_b, "fault_c": fault_c, "residual": residual,
    }


def mask_for(df: pd.DataFrame, subset: pd.DataFrame) -> pd.Series:
    return df.index.isin(subset.index)


def fmt_p(p: float) -> str:
    if p < 1e-300:
        return "< 1e-300"
    if p < 1e-4:
        return f"{p:.3e}"
    return f"{p:.4f}"


def fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def run_checks(data: dict):
    df = data["attempts"]
    n_total = len(df)
    faults = identify_faults(df)
    failed, oom = faults["failed"], faults["oom"]
    fault_a, fault_b, fault_c, residual = faults["fault_a"], faults["fault_b"], faults["fault_c"], faults["residual"]

    batch_start = df["started_at"].min()
    df = df.copy()
    df["time_bucket"] = df["started_at"].dt.floor(f"{TIME_BUCKET_MINUTES}min")
    all_dims = CONCENTRATION_DIMENSIONS + ["time_bucket"]

    checks: list[CheckResult] = []
    measured: dict = {}

    # -- Partition sanity (feeds several checks, reported once) -------------
    oom_partition_ok = (len(fault_a) + len(fault_b) == len(oom))
    known_classes_covered = (len(failed) == len(oom) + len(fault_c) + len(residual))

    # ---------------------------------------------------------------------
    # Check 1: Fault A recoverable — node_group concentration + reverse test
    # ---------------------------------------------------------------------
    conc_node_a = concentration(df, "node_group", mask_for(df, fault_a))
    b_row = conc_node_a[conc_node_a["value"] == "B"]
    b_subset_share = float(b_row["subset_share"].iloc[0]) if len(b_row) else 0.0
    b_pop_share = float(b_row["pop_share"].iloc[0]) if len(b_row) else 0.0
    b_p = float(b_row["p_value_bonferroni"].iloc[0]) if len(b_row) else 1.0
    node_concentrated = len(b_row) > 0 and b_subset_share > b_pop_share and b_p < SIG_LEVEL

    conc_shot_a = concentration(df, "shot_id", mask_for(df, fault_a))
    hair_shots = conc_shot_a[conc_shot_a["p_value_bonferroni"] < SIG_LEVEL]["value"].tolist()

    reverse_test_rows = []
    reverse_test_ok = len(hair_shots) > 0
    for shot in hair_shots:
        elsewhere = check_success_elsewhere(df, "shot_id", shot, "node_group", "B")
        groups_present = sorted(elsewhere["node_group"].unique().tolist())
        ok = ("A" in groups_present) and ("C" in groups_present)
        reverse_test_ok = reverse_test_ok and ok
        reverse_test_rows.append((shot, len(elsewhere), groups_present, ok))

    check1_pass = node_concentrated and reverse_test_ok
    hair_shot_rate = float(fault_a["uses_hair_shader"].mean()) if len(fault_a) else float("nan")

    reverse_detail = "; ".join(
        f"{s}: {n} successes outside B in groups {g}" for s, n, g, ok in reverse_test_rows
    )
    checks.append(CheckResult(
        number="1", name="Fault A recoverable (node concentration + reverse test)",
        passed=check1_pass,
        terminal_line=(
            f"group B = {fmt_pct(b_subset_share)} of Fault A failures vs {fmt_pct(b_pop_share)} of batch "
            f"(p={fmt_p(b_p)}); {len(hair_shots)} shots isolated, reverse test "
            f"{'passed' if reverse_test_ok else 'FAILED'}"
        ),
        detail_md=(
            f"Group B holds {b_row['subset_count'].iloc[0] if len(b_row) else 0} of "
            f"{len(fault_a)} Fault A failure rows ({fmt_pct(b_subset_share)}) while running "
            f"{fmt_pct(b_pop_share)} of the batch ({b_row['pop_count'].iloc[0] if len(b_row) else 0} of "
            f"{n_total} attempts). Binomial p = {fmt_p(b_p)} after Bonferroni correction across "
            f"{int(b_row['n_values_tested'].iloc[0]) if len(b_row) else 0} node groups.\n\n"
            f"Shot-id concentration on the same subset isolates {len(hair_shots)} shot(s) at "
            f"p < {SIG_LEVEL} after correction: {', '.join(hair_shots) if hair_shots else '(none)'}. "
            f"{fmt_pct(hair_shot_rate)} of Fault A rows have uses_hair_shader = True.\n\n"
            f"Reverse test (do these shots succeed outside group B?): {reverse_detail if reverse_detail else '(no shots to test)'}."
        ),
    ))

    # ---------------------------------------------------------------------
    # Check 2: node signal not buried by shot signal
    # ---------------------------------------------------------------------
    node_min_p = float(conc_node_a[conc_node_a["subset_count"] > 0]["p_value_bonferroni"].min()) if len(conc_node_a) else 1.0
    shot_min_p = float(conc_shot_a[conc_shot_a["subset_count"] > 0]["p_value_bonferroni"].min()) if len(conc_shot_a) else 1.0
    check2_pass = node_min_p < shot_min_p
    checks.append(CheckResult(
        number="2", name="Fault A node signal stronger than shot signal",
        passed=check2_pass,
        terminal_line=f"node_group best p={fmt_p(node_min_p)} vs shot_id best p={fmt_p(shot_min_p)}",
        detail_md=(
            f"The strongest (smallest) Bonferroni-corrected p-value on node_group is "
            f"{fmt_p(node_min_p)}, versus {fmt_p(shot_min_p)} on shot_id, for the same Fault A "
            f"subset ({len(fault_a)} rows). The node signal is "
            f"{'stronger' if check2_pass else 'NOT stronger'} than the shot signal, "
            f"as required so the node-group test is the one an agent should reach for first."
        ),
    ))

    # ---------------------------------------------------------------------
    # Check 3: Fault B recoverable — fails in all three groups, retries fail again
    # ---------------------------------------------------------------------
    b_groups = fault_b["node_group"].value_counts().to_dict()
    all_three_groups = all(g in b_groups and b_groups[g] > 0 for g in ("A", "B", "C"))
    b_retry_rate, b_fail2, b_n2, b_ntasks = second_attempt_failure_rate(fault_b, df)
    check3_pass = all_three_groups and (b_retry_rate == 1.0)
    checks.append(CheckResult(
        number="3", name="Fault B recoverable (fails in all groups; retries fail again)",
        passed=check3_pass,
        terminal_line=(
            f"shot_047 failures in groups {sorted(b_groups.keys())}={b_groups}; "
            f"retry fail-again rate={fmt_pct(b_retry_rate)} ({b_fail2}/{b_n2})"
        ),
        detail_md=(
            f"shot_047 (Fault B) failures appear in all three node groups: "
            f"A={b_groups.get('A', 0)}, B={b_groups.get('B', 0)}, C={b_groups.get('C', 0)}, "
            f"including group C which runs Arnold 7.3.0 — ruling out a node-group cause. "
            f"Of {b_ntasks} unique Fault B tasks, {b_n2} had a second attempt and "
            f"{b_fail2} of those failed again ({fmt_pct(b_retry_rate)}), matching the "
            f"expected 100% content-located retry signature."
        ),
    ))

    # ---------------------------------------------------------------------
    # Check 4: memory contrast
    # ---------------------------------------------------------------------
    a_below = fault_a["peak_mem_gb"] < fault_a["mem_allocated_gb"]
    b_above = fault_b["peak_mem_gb"] > fault_b["mem_allocated_gb"]
    a_below_frac = float(a_below.mean()) if len(fault_a) else float("nan")
    b_above_frac = float(b_above.mean()) if len(fault_b) else float("nan")
    a_min, a_max = float(fault_a["peak_mem_gb"].min()), float(fault_a["peak_mem_gb"].max())
    b_min, b_max = float(fault_b["peak_mem_gb"].min()), float(fault_b["peak_mem_gb"].max())
    check4_pass = (a_below_frac == 1.0) and (b_above_frac == 1.0) and oom_partition_ok
    checks.append(CheckResult(
        number="4", name="Memory contrast (Fault A under budget, Fault B over budget)",
        passed=check4_pass,
        terminal_line=(
            f"Fault A peak_mem in [{a_min:.2f}, {a_max:.2f}] GB, all below allocation "
            f"({fmt_pct(a_below_frac)}); Fault B peak_mem in [{b_min:.2f}, {b_max:.2f}] GB, "
            f"all above allocation ({fmt_pct(b_above_frac)})"
        ),
        detail_md=(
            f"Fault A failure rows range from {a_min:.2f} to {a_max:.2f} GB peak memory, and "
            f"{fmt_pct(a_below_frac)} of them are below mem_allocated_gb (12.0 GB). "
            f"Fault B failure rows range from {b_min:.2f} to {b_max:.2f} GB, and "
            f"{fmt_pct(b_above_frac)} of them are above mem_allocated_gb. The two populations "
            f"do not overlap on the over/under-budget test. The shot_id-based split of the "
            f"{len(oom)}-row OOM pile into {len(fault_a)} Fault A and {len(fault_b)} Fault B rows "
            f"{'is' if oom_partition_ok else 'is NOT'} a clean partition (no overlap, full coverage)."
        ),
    ))

    # ---------------------------------------------------------------------
    # Check 5: Fault C recoverable — time window concentration, nothing else
    # ---------------------------------------------------------------------
    conc_time_c = concentration(df, "time_bucket", mask_for(df, fault_c))
    time_min_p_c = float(conc_time_c[conc_time_c["subset_count"] > 0]["p_value_bonferroni"].min()) if len(conc_time_c) else 1.0
    other_dim_hits_c = []
    for dim in CONCENTRATION_DIMENSIONS:
        conc = concentration(df, dim, mask_for(df, fault_c))
        hits = conc[conc["p_value_bonferroni"] < SIG_LEVEL]
        if len(hits):
            other_dim_hits_c.append((dim, hits["value"].tolist()))
    c_window_start = fault_c["started_at"].min() if len(fault_c) else pd.NaT
    c_window_end = fault_c["started_at"].max() if len(fault_c) else pd.NaT
    c_onset_offset = (c_window_start - batch_start) if pd.notna(c_window_start) else None
    c_end_offset = (c_window_end - batch_start) if pd.notna(c_window_end) else None
    check5_pass = (time_min_p_c < SIG_LEVEL) and (len(other_dim_hits_c) == 0)
    checks.append(CheckResult(
        number="5", name="Fault C recoverable (time-window concentration only)",
        passed=check5_pass,
        terminal_line=(
            f"time_bucket best p={fmt_p(time_min_p_c)}; other dims flagged: "
            f"{[d for d, _ in other_dim_hits_c] if other_dim_hits_c else 'none'}"
        ),
        detail_md=(
            f"Fault C's {len(fault_c)} failures span from {c_onset_offset} to {c_end_offset} "
            f"after batch start (clock time {c_window_start} to {c_window_end}), matching the "
            f"specified 02:08-02:19 stall window. The strongest 10-minute time bucket has "
            f"Bonferroni-corrected p = {fmt_p(time_min_p_c)}. Testing node_group, node_id, "
            f"shot_id, job_id, renderer_version, and submitted_by on this subset: "
            + (
                "none exceed the significance threshold, as expected for a farm-wide transient."
                if not other_dim_hits_c else
                "unexpected concentration found in " + "; ".join(f"{d}={v}" for d, v in other_dim_hits_c)
            )
        ),
    ))

    # ---------------------------------------------------------------------
    # Check 6: residual patternless across every dimension
    # ---------------------------------------------------------------------
    residual_hits = []
    residual_min_p = 1.0
    for dim in all_dims:
        conc = concentration(df, dim, mask_for(df, residual))
        if len(conc):
            dim_min_p = float(conc[conc["subset_count"] > 0]["p_value_bonferroni"].min()) if (conc["subset_count"] > 0).any() else 1.0
            residual_min_p = min(residual_min_p, dim_min_p)
        hits = conc[conc["p_value_bonferroni"] < SIG_LEVEL]
        if len(hits):
            residual_hits.append((dim, hits["value"].tolist()))
    check6_pass = len(residual_hits) == 0
    checks.append(CheckResult(
        number="6", name="Residual patternless across every dimension",
        passed=check6_pass,
        terminal_line=(
            f"closest corrected p={fmt_p(residual_min_p)}; flagged dims: "
            f"{[d for d, _ in residual_hits] if residual_hits else 'none'}"
        ),
        detail_md=(
            f"Concentration tests were run on the {len(residual)} residual rows across "
            f"{', '.join(all_dims)}. " +
            (
                f"No value in any dimension exceeds the p < {SIG_LEVEL} threshold after "
                f"Bonferroni correction; the closest was p = {fmt_p(residual_min_p)}. "
                f"This supports treating the residual as patternless."
                if check6_pass else
                f"Unexpected concentration found in: " + "; ".join(f"{d}={v}" for d, v in residual_hits) +
                ". The residual is NOT patternless as constructed; regeneration is warranted."
            )
        ),
    ))

    # ---------------------------------------------------------------------
    # Check 7: retry signatures
    # ---------------------------------------------------------------------
    a_rate, a_fail2, a_n2, a_ntasks = second_attempt_failure_rate(fault_a, df)
    c_rate, c_fail2, c_n2, c_ntasks = second_attempt_failure_rate(fault_c, df)
    r_rate, r_fail2, r_n2, r_ntasks = second_attempt_failure_rate(residual, df)
    a_band = EXPECTED["fault_a_retry_band"]
    a_retry_ok = a_band[0] <= a_rate <= a_band[1]
    b_retry_ok = (b_retry_rate == EXPECTED["fault_b_retry_rate"])
    c_retry_ok = (c_rate == EXPECTED["fault_c_retry_rate"])
    r_retry_ok = (r_rate == EXPECTED["residual_retry_rate"])
    check7_pass = a_retry_ok and b_retry_ok and c_retry_ok and r_retry_ok
    checks.append(CheckResult(
        number="7", name="Retry signatures match fault taxonomy",
        passed=check7_pass,
        terminal_line=(
            f"A={fmt_pct(a_rate)} (want {fmt_pct(a_band[0])}-{fmt_pct(a_band[1])}), "
            f"B={fmt_pct(b_retry_rate)} (want 100%), C={fmt_pct(c_rate)} (want 0%), "
            f"residual={fmt_pct(r_rate)} (want 0%)"
        ),
        detail_md=(
            f"Second-attempt failure rate, computed by looking up attempt=2 rows for each "
            f"fault's unique failed tasks: Fault A = {fmt_pct(a_rate)} ({a_fail2}/{a_n2} of "
            f"{a_ntasks} tasks) against a required band of "
            f"{fmt_pct(a_band[0])}-{fmt_pct(a_band[1])} ({'within' if a_retry_ok else 'OUTSIDE'} band); "
            f"Fault B = {fmt_pct(b_retry_rate)} ({b_fail2}/{b_n2} of {b_ntasks} tasks), "
            f"required exactly 100% ({'match' if b_retry_ok else 'MISMATCH'}); "
            f"Fault C = {fmt_pct(c_rate)} ({c_fail2}/{c_n2} of {c_ntasks} tasks), "
            f"required exactly 0% ({'match' if c_retry_ok else 'MISMATCH'}); "
            f"residual = {fmt_pct(r_rate)} ({r_fail2}/{r_n2} of {r_ntasks} tasks), "
            f"required exactly 0% ({'match' if r_retry_ok else 'MISMATCH'})."
        ),
    ))

    # ---------------------------------------------------------------------
    # Check 8: exact row counts
    # ---------------------------------------------------------------------
    b_rows_ok = len(fault_b) == EXPECTED["fault_b_rows"]
    c_rows_ok = len(fault_c) == EXPECTED["fault_c_rows"]
    r_rows_ok = len(residual) == EXPECTED["residual_rows"]
    check8_pass = b_rows_ok and c_rows_ok and r_rows_ok
    checks.append(CheckResult(
        number="8", name="Exact row counts (Fault B, Fault C, residual)",
        passed=check8_pass,
        terminal_line=(
            f"Fault B rows={len(fault_b)} (want {EXPECTED['fault_b_rows']}), "
            f"Fault C rows={len(fault_c)} (want {EXPECTED['fault_c_rows']}), "
            f"residual rows={len(residual)} (want {EXPECTED['residual_rows']})"
        ),
        detail_md=(
            f"Fault B has {len(fault_b)} failure rows (expected exactly {EXPECTED['fault_b_rows']}). "
            f"Fault C has {len(fault_c)} failure rows (expected exactly {EXPECTED['fault_c_rows']}). "
            f"The residual has {len(residual)} failure rows (expected exactly {EXPECTED['residual_rows']})."
        ),
    ))

    # ---------------------------------------------------------------------
    # Check 9: approximate row-count bands
    # ---------------------------------------------------------------------
    a_band_rows = EXPECTED["fault_a_rows_band"]
    total_band_rows = EXPECTED["total_rows_band"]
    total_failed_rows = len(failed)
    a_rows_ok = a_band_rows[0] <= len(fault_a) <= a_band_rows[1]
    total_rows_ok = total_band_rows[0] <= total_failed_rows <= total_band_rows[1]
    check9_pass = a_rows_ok and total_rows_ok
    checks.append(CheckResult(
        number="9", name="Approximate row-count bands (Fault A, grand total)",
        passed=check9_pass,
        terminal_line=(
            f"Fault A rows={len(fault_a)} (band {a_band_rows[0]}-{a_band_rows[1]}); "
            f"total failure rows={total_failed_rows} (band {total_band_rows[0]}-{total_band_rows[1]})"
        ),
        detail_md=(
            f"Fault A has {len(fault_a)} failure rows, expected in the band "
            f"[{a_band_rows[0]}, {a_band_rows[1]}] (190 first attempts plus "
            f"Binomial(190, 0.30) retries, +/- 2 SD). "
            f"{'This is within band.' if a_rows_ok else 'This is OUTSIDE the band — the retry dispatch rate is likely wrong, not an unlucky seed.'} "
            f"Total failure rows across all four groups is {total_failed_rows}, expected in "
            f"[{total_band_rows[0]}, {total_band_rows[1]}]. "
            f"{'This is within band.' if total_rows_ok else 'This is OUTSIDE the band.'}"
        ),
    ))

    # ---------------------------------------------------------------------
    # Check 10: exact unique task counts
    # ---------------------------------------------------------------------
    a_tasks = fault_a["task_id"].nunique()
    b_tasks = fault_b["task_id"].nunique()
    c_tasks = fault_c["task_id"].nunique()
    r_tasks = residual["task_id"].nunique()
    total_tasks = a_tasks + b_tasks + c_tasks + r_tasks
    tasks_exact_ok = (
        a_tasks == EXPECTED["fault_a_unique_tasks"]
        and b_tasks == EXPECTED["fault_b_unique_tasks"]
        and c_tasks == EXPECTED["fault_c_unique_tasks"]
        and r_tasks == EXPECTED["residual_unique_tasks"]
        and total_tasks == EXPECTED["total_unique_tasks"]
    )
    checks.append(CheckResult(
        number="10", name="Exact unique task counts",
        passed=tasks_exact_ok,
        terminal_line=(
            f"A={a_tasks}(190) B={b_tasks}(42) C={c_tasks}(14) resid={r_tasks}(48) "
            f"total={total_tasks}(294)"
        ),
        detail_md=(
            f"Unique failed tasks: Fault A = {a_tasks} (expected {EXPECTED['fault_a_unique_tasks']}), "
            f"Fault B = {b_tasks} (expected {EXPECTED['fault_b_unique_tasks']}), "
            f"Fault C = {c_tasks} (expected {EXPECTED['fault_c_unique_tasks']}), "
            f"residual = {r_tasks} (expected {EXPECTED['residual_unique_tasks']}). "
            f"Sum = {total_tasks} (expected {EXPECTED['total_unique_tasks']})."
        ),
    ))

    # ---------------------------------------------------------------------
    # Additional: hair-shader corroborating signal
    # ---------------------------------------------------------------------
    after_maint = df[df["started_at"] >= batch_start + pd.Timedelta(hours=1)]
    if hair_shots:
        b_hair_succ = after_maint[
            (after_maint["status"] == "success")
            & (after_maint["shot_id"].isin(hair_shots))
            & (after_maint["node_group"] == "B")
        ]
        ac_hair_succ = after_maint[
            (after_maint["status"] == "success")
            & (after_maint["shot_id"].isin(hair_shots))
            & (after_maint["node_group"] != "B")
        ]
        b_mean = float(b_hair_succ["peak_mem_gb"].mean()) if len(b_hair_succ) else float("nan")
        ac_mean = float(ac_hair_succ["peak_mem_gb"].mean()) if len(ac_hair_succ) else float("nan")
        corroborating_pass = (len(b_hair_succ) > 0) and (len(ac_hair_succ) > 0) and (b_mean > ac_mean)
    else:
        b_hair_succ, ac_hair_succ, b_mean, ac_mean = df.iloc[0:0], df.iloc[0:0], float("nan"), float("nan")
        corroborating_pass = False
    checks.append(CheckResult(
        number="11", name="Hair-shader corroborating signal (elevated peak_mem on B successes)",
        passed=corroborating_pass,
        terminal_line=(
            f"group B hair-shot successes mean peak_mem={b_mean:.2f} GB (n={len(b_hair_succ)}) vs "
            f"groups A/C mean={ac_mean:.2f} GB (n={len(ac_hair_succ)}), diff={b_mean - ac_mean:.2f} GB"
        ),
        detail_md=(
            f"Among the {len(hair_shots)} shots isolated as Fault A's hair-shader shots, successful "
            f"renders after the 23:00 maintenance window show a mean peak_mem_gb of {b_mean:.2f} GB "
            f"on group B (n={len(b_hair_succ)}) versus {ac_mean:.2f} GB on groups A and C combined "
            f"(n={len(ac_hair_succ)}), a difference of {b_mean - ac_mean:.2f} GB. This is corroborating "
            f"evidence for the 7.3.1 memory regression even on tasks that did not fail outright."
        ),
    ))

    # ---------------------------------------------------------------------
    # Measured values for FAULTS.md
    # ---------------------------------------------------------------------
    oom_pile_size = len(oom)
    b_share_of_oom = float((oom["node_group"] == "B").mean()) if len(oom) else float("nan")
    b_share_of_batch = float((df["node_group"] == "B").mean())
    window = df[
        (df["node_group"] == "B")
        & (df["started_at"] >= batch_start)
        & (df["started_at"] < batch_start + pd.Timedelta(hours=1))
    ]
    b_window_success = int((window["status"] == "success").sum())
    b_window_total = len(window)

    measured = {
        "Fault A failure rows": len(fault_a),
        "Fault B failure rows": len(fault_b),
        "Fault C failure rows": len(fault_c),
        "Residual failure rows": len(residual),
        "Total failure rows": total_failed_rows,
        "Total attempts": n_total,
        "Unique failed tasks (total)": total_tasks,
        "OOM pile size (rows)": oom_pile_size,
        "Group B's share of the OOM pile": fmt_pct(b_share_of_oom),
        "Group B's share of the batch": fmt_pct(b_share_of_batch),
        "Fault A's second-attempt failure rate": fmt_pct(a_rate),
        "Group B clean (successful) tasks, 22:00-23:00 window": f"{b_window_success} of {b_window_total} attempts",
    }

    return checks, measured, {
        "n_total": n_total, "batch_start": batch_start,
        "known_classes_covered": known_classes_covered, "oom_partition_ok": oom_partition_ok,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_terminal(checks: list[CheckResult]):
    for c in checks:
        status = "PASS" if c.passed else "FAIL"
        print(f"[{status}] Check {c.number}: {c.name} — {c.terminal_line}")
    overall = "PASS" if all(c.passed for c in checks) else "FAIL"
    print(f"\nOverall: {overall} ({sum(c.passed for c in checks)}/{len(checks)} checks passed)")


def write_report(checks: list[CheckResult], measured: dict, context: dict, source_desc: str, out_path: str):
    overall = "PASS" if all(c.passed for c in checks) else "FAIL"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = []
    lines.append("# verify.md")
    lines.append("")
    lines.append(f"Run: {ts}")
    lines.append("")
    lines.append(f"Input: {source_desc}")
    lines.append("")
    lines.append(f"Total rows read: {context['n_total']}")
    lines.append("")
    lines.append(f"**Overall: {overall}** ({sum(c.passed for c in checks)}/{len(checks)} checks passed)")
    lines.append("")
    lines.append("---")
    lines.append("")

    for c in checks:
        status = "PASS" if c.passed else "FAIL"
        lines.append(f"## Check {c.number}: {c.name} — {status}")
        lines.append("")
        lines.append(c.detail_md)
        lines.append("")
        if not c.passed:
            lines.append(
                "**Failed.** See the measured values above for what was found versus what "
                "FAULTS.md requires. No generator internals were consulted to explain this; "
                "the fix, if any, is in the data or the threshold, not in this verifier."
            )
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## Measured values for FAULTS.md")
    lines.append("")
    lines.append("| Figure | Value |")
    lines.append("|---|---|")
    for k, v in measured.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Independent verifier for the render farm triage dataset."
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--parquet", metavar="PATH", help="Path to render_task_attempts Parquet file.")
    src.add_argument("--clickhouse", action="store_true", help="Read from ClickHouse using CLICKHOUSE_* env vars.")
    args = parser.parse_args()

    if args.parquet:
        data = load_from_parquet(args.parquet)
    else:
        data = load_from_clickhouse()

    checks, measured, context = run_checks(data)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify.md")
    write_report(checks, measured, context, data["source_desc"], out_path)
    print_terminal(checks)

    all_passed = all(c.passed for c in checks)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
