# FAULTS.md

Fault specification for the synthetic render farm dataset.
Every column in the schema exists because a fault below requires it to be detectable.

**Status: frozen.** Fault design is closed and every figure below is a measured value
from the generated dataset, not a target.

**Provenance of the numbers.** The dataset is produced by `generate.py` from a
committed RNG seed (`SEED = 20260909`). Every figure in this document was measured by
`verify.py`, which was written in a separate session without access to `generate.py`
and which identifies the fault groups from observable columns — `error_class`,
`shot_id`, `node_group`, `renderer_version`, `started_at`, `peak_mem_gb` — rather
than from any label or task list carried over from generation. It reports 11 of 11
checks passing. The same checks were run twice: against the Parquet artifact and
against the loaded ClickHouse table, and the measured values were byte-for-byte
identical, so nothing was altered during ingest. Full evidence is in `verify.md` and
`verify_parquet.md`.

---

## Farm configuration

| Property | Value |
|---|---|
| Nodes | 100 |
| Node groups | A (40 nodes, 64 GB), B (30 nodes, 64 GB), C (30 nodes, 128 GB high-mem) |
| Renderer | Arnold |
| Baseline version | 7.3.0 on groups A and C |
| Batch window | 22:00, scheduled to 06:00; last task ended 07:14 |
| Total task attempts | 9,996 |
| Unique tasks | 9,702 |
| Total failure rows | 396 |
| Unique failed tasks | 294 |
| Scheduler retry limit | 2 attempts per task (Deadline-style; error limit 100 per job) |

Retries re-dispatch to whatever node is free. They do **not** prefer the original
node, so a retry lands in group B roughly 30% of the time. Group B ran 29.9% of the
batch.
**A note on the window.** The batch was scheduled 22:00 to 06:00, but queue overrun
and second attempts push the tail past it: the last task started at 07:08:49 and
ended at 07:14:14. All 9,996 attempts fall inside 22:00–08:00, and every
concentration denominator in `verify.py` and in the tool layer is computed over all
9,996 rows, so the two agree exactly. Queries that clip at a literal 06:00 drop
roughly 1,049 attempts and will not reproduce the figures in this document.


---

## Timeline

| Time | Event |
|---|---|
| 22:00 | Batch starts. All groups clean. |
| 06:00 | Scheduled end of window. Queue overrun and retries push the tail to 07:09. |
| 23:00 | Maintenance window. Group B updated to Arnold 7.3.1. |
| 23:04 | First group B failure. |
| 22:00–07:09 | shot_047 fails whenever its frames run. No time signature. |
| 02:08–02:19 | Asset server stall. All groups. Self-resolves. |
| 22:00–07:09 | Residual failures, uniformly distributed. |

---

## What the agent must produce

This is the grading criteria. Four things are scored.

**1. Root cause per fault, stated in words.** Not a dimension name, not a row count —
a causal sentence. "Group B is failing" is not a root cause. "The 23:00 maintenance
window put Arnold 7.3.1 on group B, and that build inflates memory on hair-shader
scenes past the allocation" is.

**2. Remediation per fault.** A concrete action with the parameters that make it
executable: which tasks, which target, which setting changed.

**3. The order across faults: C, then A, then B.**
- **C first** because it needs no fix at all. Fourteen tasks, six minutes of farm
  time, every retry already succeeded. It blocks nothing and it is free.
- **A second** because it is the largest block of work (190 tasks) and its fix is a
  precondition. Until group B is rolled back to 7.3.0, *any* re-queue is unsafe —
  roughly 30% of re-dispatched tasks land on 7.3.1 nodes. The rollback protects
  everything queued after it, so it comes before the remaining work rather than
  after.
- **B third** because its fix is a scoped configuration change (raise shot_047's
  allocation, target group C) that depends on nothing else and blocks nothing else.
- The residual is re-queued last, at lowest priority.

**4. Correct restraint on the residual.** The agent tests the dimensions, finds
nothing above base rate, and says so. Recommending re-queue as-is at lowest priority
is the right answer. Inventing a fifth fault to explain these 48 rows is a failure,
and it is the specific failure this dataset is built to catch.

**Resolution paths below are illustrative, not graded.** They show one route to each
conclusion. A different sequence of tool calls that reaches the same root cause and
the same remediation is equally correct. Do not score the path.

---

## Retry signatures

Second-attempt failure rate alone discriminates between the three fault types. This
is the cheapest single discriminator in the dataset and the agent should reach for it
early. Rates below are measured.

| Fault | Retry outcome | Rate | What it means |
|---|---|---|---|
| A | Fails again only when the retry lands back on group B | 31.6% (60 of 190) | **Node-located.** The fault lives on specific machines. Escape the machines and the task succeeds. |
| B | Fails again on whatever node it lands on | 100% (42 of 42) | **Content-located.** The fault travels with the scene. No node escapes it. |
| C | Succeeds | 0% (0 of 14) | **Transient.** The condition was gone by the time the retry ran. |
| Residual | Succeeds | 0% (0 of 48) | Transient one-offs, unrelated to each other. |

The 31.6% for Fault A is not a coincidence — it is group B's share of the fleet
(30 of 100 nodes; 29.9% of the batch by task count), which is what you expect when
retries re-dispatch at random and the fault is confined to one group. An agent that
notices the retry-failure rate *matches the group's fleet share* has effectively
proved the fault is node-located without needing any other test.

Retry rate does not separate C from the residual — both are 0%. Time clustering does.

---

## Fault A — Arnold 7.3.1 memory regression on group B

**Root cause.** The 23:00 maintenance window pushed Arnold 7.3.1 to group B only.
That build has a shader memory regression that inflates peak memory by roughly 30%
on scenes using the standard hair shader. Groups A and C remain on 7.3.0.

**Failure rows.** 250 — 190 first attempts, all of which fail, plus 60 retries that
re-dispatched back onto group B and failed again.
**Unique tasks.** 190
**Concentration.** `node_group` = B, **and partially** `shot_id` (four hair-shader shots)
**Onset.** 23:04, sharp
**Peak memory on failure rows.** 11.41 to 11.95 GB, every row below the 12.0 GB
allocation.

**Error text.** Standard Arnold OOM, identical in form to Fault B:

```
00:04:17 61204MB ERROR | can't allocate 2214592512 bytes with alignment 64 in ?:?():0 (virtual memory : 65536 Mb)
00:04:17 61204MB WARNING | render terminating early: out of memory
```

**Three conditions must coincide for a failure.** Task ran on group B; scene uses
hair shaders; frame heavy enough that a 30% inflation crosses the allocation. Remove
any one and the task succeeds. The *cause* is the version, because that is the only
one of the three that changed at 23:00 — hair shaders and heavy frames were both
true yesterday and nothing failed.

**Why it is not obvious.**
- Same `error_class` and message shape as Fault B. Grouping by error text merges the
  two faults into one 334-row pile.
- Group B ran 341 of 348 tasks cleanly between 22:00 and 23:00. "Group B is bad" is
  false for most of the night. Time and node must be considered jointly.
- Because the regression only affects hair-shader scenes, the four affected shots
  show real concentration too. **Both dimensions light up.** This is deliberate.

**Resolution path (illustrative).**
1. `test_dimension_concentration(node_group)` → group B holds 278 of the 334 OOM rows
   (83.2%) while running 29.9% of the batch. Not all 278 are Fault A: 28 of
   shot_047's 84 failure rows land on group B as well. The node test alone cannot
   separate the two faults — that is what step 3 is for.
2. `test_dimension_concentration(shot_id)` → four shots also concentrate. Ambiguous
   so far. Measured: the node signal is the stronger of the two
   (node_group p = 1.96e-131 against shot_id p = 1.32e-38).
3. `check_success_elsewhere(shot)` → all four shots rendered successfully in groups
   A and C during the same window. Shots ruled out.
4. `test_dimension_concentration(renderer_version)` → 7.3.1 accounts for all of them.
5. Onset at 23:04 aligns with the maintenance window.

**Secondary signals.** Two, both measured and both available to a thorough agent:
- Retry outcomes fail at 31.6%, matching group B's share of the fleet, because
  retries re-dispatch at random and some land back on 7.3.1 nodes.
- Group B hair-shader tasks that **succeeded** after 23:00 average 11.48 GB peak
  memory (n = 196), against 9.80 GB for the same shots in groups A and C during the
  same window (n = 1,125) — a 1.67 GB elevation visible in the success rows, before
  any failure is examined.

**Remediation — order matters.** Roll group B back to 7.3.0, **then** re-queue 190
tasks. A re-queue without the rollback sends ~30% of tasks back onto 7.3.1 nodes,
where they fail again. Rolling back first drives that to zero. This is the clearest
case for why the plan must be sequenced rather than listed.

---

## Fault B — shot_047 exceeds its memory allocation

**Root cause.** shot_047 was re-published with a denser volumetric sim. Peak memory
now runs above 14 GB against a 12 GB allocation. The scene is genuinely too heavy for
its budget. Nothing is broken.

**Failure rows.** 84
**Unique tasks.** 42 — each fails, retries, fails again
**Concentration.** `shot_id` = shot_047, spread across all three groups (A = 37,
B = 28, C = 19)
**Onset.** None. Fails whenever its frames run.
**Peak memory on failure rows.** 13.80 to 14.54 GB, every row above the 12.0 GB
allocation.

**Error text.** Same form as Fault A:

```
00:06:52 14208MB ERROR | can't allocate 1073741824 bytes with alignment 64 in ?:?():0 (virtual memory : 65536 Mb)
00:06:52 14208MB WARNING | render terminating early: out of memory
```

**Why it is not obvious.**
- Identical error class to Fault A.
- Failures appear in group B alongside Fault A's, so a naive node-group test
  attributes some of these to B.
- Only the heaviest frames fail — frames 78 to 119. The rest of the shot succeeds,
  so "shot_047 is broken" is too strong. Frame weight explains *which* tasks failed;
  it does not explain *why*.

**Resolution path (illustrative).**
1. `check_success_elsewhere(shot_047)` → fails in **all three** groups (A = 37,
   B = 28, C = 19), including group C on 7.3.0. Not a node-group fault.
2. Retry outcome → 100% fail again, on different nodes. Follows the content.
3. `peak_mem_gb` against `mem_allocated_gb` (12.0) → over budget on every row.
4. `frame_number` distribution → contiguous run, 78 to 119. Content-driven.

**Remediation.** Raise allocation to 20 GB, re-queue 42 tasks on group C (high-mem).

**Contrast to hold onto.** Fault A's failures top out at 11.95 GB against the same
12 GB allocation — *under* budget. Fault B's floor is 13.80 GB. Same error string,
opposite meaning, and the two populations do not overlap. This contrast is
load-bearing.

---

## Fault C — asset server stall, 02:08 to 02:19

**Root cause.** Brief NFS stall on the texture filer. Reads time out. Self-resolves
after 11 minutes.

**Failure rows.** 14
**Unique tasks.** 14 — all succeed on retry
**Concentration.** `timestamp`, an 11-minute window (p = 1.83e-20). All groups, no
shot pattern.
**Onset.** 02:08:24, ends 02:18:36

**Error text.** Distinct from A and B:

```
00:01:33 8842MB ERROR | [texturesys] /assets/env_forest/bark_diff.tx: Invalid image file "/assets/env_forest/bark_diff.tx": read error: Input/output error
00:01:33 8842MB WARNING | [kick] render aborted due to earlier errors
```

**Why it is easy — and why that is fine.**
Distinct error class, tight window, no node or shot concentration, every retry
succeeded. Its purpose is to test **prioritization**, not diagnosis: it needs no fix,
so it should be re-queued first as a freebie because it blocks nothing and costs six
minutes.

**Resolution path (illustrative).**
1. `test_dimension_concentration(timestamp)` → 14 of 14 inside an 11-minute window.
2. `test_dimension_concentration(node_group)` and `(shot_id)` → nothing above base rate.
3. `query_similar_past_incidents` → matches a stall on 14 Aug where a straight
   re-queue succeeded.

**Remediation.** Re-queue 14 tasks as-is, low priority.

---

## Residual — 48 failures with no shared cause

**Failure rows.** 48
**Unique tasks.** 48 — all succeed on retry

**Construction.** Drawn uniformly from all otherwise-unassigned tasks, so `node_id`,
`shot_id`, and `timestamp` follow the same distributions the *successful* tasks
follow. Error classes sampled from a long tail: license checkout timeout, disk full
on scratch, corrupt frame write, segfault, stale mount. No two share a cause.

**Measured patternlessness.** Concentration tested across every dimension. The
strongest result was p = 0.663 after Bonferroni correction — nothing above base rate
anywhere. The correction matters: with 50 shots, an uncorrected threshold of 0.05
fires by chance most of the time, and a verifier without it would report a pattern
that isn't there.

**Expected agent behavior.** Test the dimensions, find nothing, say so. Recommend
re-queue as-is at lowest priority. An agent that invents a story for these 48 has
failed the scenario.

---

## Confound summary

| Confound | Faults | Resolved by |
|---|---|---|
| Same error text, different cause | A, B | Reverse test: follows the node or the shot |
| Group B implicated by both | A, B | shot_047 also fails in A and C |
| Shot dimension genuinely concentrated | A | Those four shots succeed outside group B |
| Time cluster looks like infrastructure | A | Onset aligns with a version change, not load |
| Raw counts overstate the problem | A | 250 rows are 190 unique tasks |
| Retry rate 0% for two different reasons | C, residual | Time clustering separates them |
| Pattern where none exists | Residual | Concentration tests return nothing above base rate |

---

## Ranking trap

By raw failure rows: A (250), B (84), residual (48), C (14).
By unique tasks: A (190), B (42), residual (48), C (14).
By urgency: **C first** — six minutes of farm time, blocks nothing, needs no fix.

The agent must dedupe before counting, and rank by remediation dependency and cost
rather than by volume. Graded order is C, A, B, residual — see "What the agent must
produce".

---

## Schema columns required

| Column | Required by |
|---|---|
| `task_id` | dedupe across attempts |
| `job_id` | grouping |
| `shot_id` | Fault B concentration; Fault A partial concentration |
| `frame_number` | Fault B; distinguishing content weight within a shot |
| `node_id` | node-level tests |
| `node_group` | Fault A concentration |
| `attempt` | retry dedupe; retry-outcome signal |
| `status` | success rows are the comparison group |
| `started_at`, `ended_at` | Fault C window; Fault A onset |
| `error_class` | cheap grouping before reading text |
| `error_text` | mechanism inference |
| `peak_mem_gb` | separating A from B; logged on successes too |
| `mem_allocated_gb` | interpreting peak memory |
| `renderer_version` | Fault A root cause |
| `uses_hair_shader` | Fault A scoping; explains partial shot concentration |
| `asset_refs` | Fault C, and future asset faults |
| `submitted_by` | demonstrating the cross-artist view |

Success rows must carry `peak_mem_gb`. Without them there is no baseline to compare
failures against, the control-group logic has nothing to stand on, and the 1.67 GB
elevation on group B's hair-shader successes is invisible.

---

## Verification checklist — all passing

Implemented in `verify.py`. Runs against the Parquet artifact or the loaded
ClickHouse table; both produce identical measured values.

| # | Check | Result |
|---|---|---|
| 1 | Fault A recoverable: group B concentration above base rate, four hair shots clear the reverse test | PASS — p = 1.96e-131 |
| 2 | Fault A's node signal not buried by the shot signal | PASS — node p = 1.96e-131 against shot p = 1.32e-38 |
| 3 | Fault B recoverable: fails in all three groups, retries fail again | PASS — 100%, 42 of 42 |
| 4 | Memory contrast: Fault A below allocation, Fault B above | PASS — [11.41, 11.95] against [13.80, 14.54] |
| 5 | Fault C recoverable: time window concentration, nothing else above base rate | PASS — p = 1.83e-20; node_group, node_id, shot_id, job_id, renderer_version, submitted_by all clear |
| 6 | Residual patternless across every dimension | PASS — closest corrected p = 0.663 |
| 7 | Retry signatures: A in 22–38%, B 100%, C 0%, residual 0% | PASS — 31.6% / 100% / 0% / 0% |
| 8 | Exact row counts: B = 84, C = 14, residual = 48 | PASS |
| 9 | Fault A rows in 234–260; grand total in 380–406 | PASS — 250 and 396 |
| 10 | Unique task counts: 190 / 42 / 14 / 48 = 294 | PASS |
| 11 | Group B hair-shader successes elevated against A and C | PASS — 11.48 GB (n=196) against 9.80 GB (n=1,125), +1.67 GB |

The seed is committed. The run is reproducible.

---

## Fault D — Deferred

**Frame/node memory interaction.** A marginal frame that fits on a 128 GB group C
node and fails on a 64 GB group A node. Neither the frame nor the node is faulty
alone. Produces a scattered pattern that resolves only by cross-tabbing frame weight
against node memory. Noted as future work.
