# verify.md

Run: 2026-09-01 18:37:30 UTC

Input: ClickHouse host: jggf38t6ho.us-central1.gcp.clickhouse.cloud, database: default, table: render_task_attempts

Total rows read: 9996

**Overall: PASS** (11/11 checks passed)

---

## Check 1: Fault A recoverable (node concentration + reverse test) — PASS

Group B holds 250 of 250 Fault A failure rows (100.0%) while running 29.9% of the batch (2986 of 9996 attempts). Binomial p = 1.963e-131 after Bonferroni correction across 3 node groups.

Shot-id concentration on the same subset isolates 4 shot(s) at p < 0.05 after correction: shot_044, shot_031, shot_012, shot_023. 100.0% of Fault A rows have uses_hair_shader = True.

Reverse test (do these shots succeed outside group B?): shot_044: 315 successes outside B in groups ['A', 'C']; shot_031: 315 successes outside B in groups ['A', 'C']; shot_012: 308 successes outside B in groups ['A', 'C']; shot_023: 317 successes outside B in groups ['A', 'C'].

## Check 2: Fault A node signal stronger than shot signal — PASS

The strongest (smallest) Bonferroni-corrected p-value on node_group is 1.963e-131, versus 1.323e-38 on shot_id, for the same Fault A subset (250 rows). The node signal is stronger than the shot signal, as required so the node-group test is the one an agent should reach for first.

## Check 3: Fault B recoverable (fails in all groups; retries fail again) — PASS

shot_047 (Fault B) failures appear in all three node groups: A=37, B=28, C=19, including group C which runs Arnold 7.3.0 — ruling out a node-group cause. Of 42 unique Fault B tasks, 42 had a second attempt and 42 of those failed again (100.0%), matching the expected 100% content-located retry signature.

## Check 4: Memory contrast (Fault A under budget, Fault B over budget) — PASS

Fault A failure rows range from 11.41 to 11.95 GB peak memory, and 100.0% of them are below mem_allocated_gb (12.0 GB). Fault B failure rows range from 13.80 to 14.54 GB, and 100.0% of them are above mem_allocated_gb. The two populations do not overlap on the over/under-budget test. The shot_id-based split of the 334-row OOM pile into 250 Fault A and 84 Fault B rows is a clean partition (no overlap, full coverage).

## Check 5: Fault C recoverable (time-window concentration only) — PASS

Fault C's 14 failures span from 0 days 04:08:24 to 0 days 04:18:36 after batch start (clock time 2026-09-09 02:08:24 to 2026-09-09 02:18:36), matching the specified 02:08-02:19 stall window. The strongest 10-minute time bucket has Bonferroni-corrected p = 1.829e-20. Testing node_group, node_id, shot_id, job_id, renderer_version, and submitted_by on this subset: none exceed the significance threshold, as expected for a farm-wide transient.

## Check 6: Residual patternless across every dimension — PASS

Concentration tests were run on the 48 residual rows across node_group, node_id, shot_id, job_id, renderer_version, submitted_by, time_bucket. No value in any dimension exceeds the p < 0.05 threshold after Bonferroni correction; the closest was p = 0.6627. This supports treating the residual as patternless.

## Check 7: Retry signatures match fault taxonomy — PASS

Second-attempt failure rate, computed by looking up attempt=2 rows for each fault's unique failed tasks: Fault A = 31.6% (60/190 of 190 tasks) against a required band of 22.0%-38.0% (within band); Fault B = 100.0% (42/42 of 42 tasks), required exactly 100% (match); Fault C = 0.0% (0/14 of 14 tasks), required exactly 0% (match); residual = 0.0% (0/48 of 48 tasks), required exactly 0% (match).

## Check 8: Exact row counts (Fault B, Fault C, residual) — PASS

Fault B has 84 failure rows (expected exactly 84). Fault C has 14 failure rows (expected exactly 14). The residual has 48 failure rows (expected exactly 48).

## Check 9: Approximate row-count bands (Fault A, grand total) — PASS

Fault A has 250 failure rows, expected in the band [234, 260] (190 first attempts plus Binomial(190, 0.30) retries, +/- 2 SD). This is within band. Total failure rows across all four groups is 396, expected in [380, 406]. This is within band.

## Check 10: Exact unique task counts — PASS

Unique failed tasks: Fault A = 190 (expected 190), Fault B = 42 (expected 42), Fault C = 14 (expected 14), residual = 48 (expected 48). Sum = 294 (expected 294).

## Check 11: Hair-shader corroborating signal (elevated peak_mem on B successes) — PASS

Among the 4 shots isolated as Fault A's hair-shader shots, successful renders after the 23:00 maintenance window show a mean peak_mem_gb of 11.48 GB on group B (n=196) versus 9.80 GB on groups A and C combined (n=1125), a difference of 1.67 GB. This is corroborating evidence for the 7.3.1 memory regression even on tasks that did not fail outright.

---

## Measured values for FAULTS.md

| Figure | Value |
|---|---|
| Fault A failure rows | 250 |
| Fault B failure rows | 84 |
| Fault C failure rows | 14 |
| Residual failure rows | 48 |
| Total failure rows | 396 |
| Total attempts | 9996 |
| Unique failed tasks (total) | 294 |
| OOM pile size (rows) | 334 |
| Group B's share of the OOM pile | 83.2% |
| Group B's share of the batch | 29.9% |
| Fault A's second-attempt failure rate | 31.6% |
| Group B clean (successful) tasks, 22:00-23:00 window | 341 of 348 attempts |
