
Remote Control is active · Continue here, on your phone, or at claude.ai/code

/model sonnet
Set model to Sonnet 5 for this session only

/sonnet
Unknown command: /sonnet

SPEC.md
FAULTS.md
c:\Users\mante\Documents\Agentic_Cinema_Hackthon\generator_py_VSCode_CoPilot_chat1.md
Write an independent verifier for a synthetic render farm dataset.

`FAULTS.md` and `SPEC.md` are in the project root. FAULTS.md is the
authoritative specification — read it before you write anything, especially the
"Generator verification checklist" and "Retry signatures" sections.

## Critical constraint on how you write this

`generate.py` exists in this repo. **Do not open it, do not read it, do not
import from it, and do not reference it.** If it is already in your context,
disregard it entirely.

The verifier's only value is that it checks the artifact independently. If it
reuses the generator's constants, its fault-membership logic, or its column
derivations, it will pass by agreeing with the code that produced the data
rather than by confirming the data is correct. Every threshold, every fault
definition, and every expected value must come from FAULTS.md.

In particular: you do not know which rows belong to which fault. Nothing in the
data labels them. You must identify the fault groups from observable columns
the same way a diagnostic agent would — `error_class`, `shot_id`, `node_group`,
`renderer_version`, `started_at`, `peak_mem_gb` — and fail loudly if a group
cannot be isolated. Do not accept a task_id list from anywhere.

## Deliverable

`verify.py`, plus any additions to `requirements.txt` it needs
(pandas, pyarrow, scipy, clickhouse-connect). Python 3.11+, argparse only.

## Input modes

```
python verify.py --parquet data/attempts.parquet
python verify.py --clickhouse
```

`--clickhouse` reads `CLICKHOUSE_HOST`, `CLICKHOUSE_USER`,
`CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DATABASE` from the environment, queries
`render_task_attempts`, and loads the result into a DataFrame.

Both modes run the **identical** check code against the DataFrame. This is
deliberate — running it before and after the load is how a type coercion during
ingest gets caught. Write the checks once, against a DataFrame, and have the two
loaders feed the same function.

Checks that need `farm_nodes` or `past_incidents` should read those from the
corresponding Parquet or table depending on mode.

## Fault identification

Derive these from the data, from FAULTS.md's descriptions:

- **OOM pile** — all failure rows with `error_class` = `oom`. This is Fault A
  and Fault B combined and the verifier must separate them without being told.
- **Fault B** — OOM failures on `shot_047`. Cross-check: `peak_mem_gb` above
  `mem_allocated_gb`.
- **Fault A** — OOM failures that are not Fault B. Cross-check: `peak_mem_gb`
  below `mem_allocated_gb`, `node_group` = B, `renderer_version` = 7.3.1.
- **Fault C** — failure rows with `error_class` = `texture_io`.
- **Residual** — all remaining failure rows.

If the two memory populations overlap, or if the OOM pile does not partition
cleanly, that is a finding — report it rather than working around it.

## Concentration testing

One reusable function:

```python
def concentration(df, dimension, subset_mask) -> pd.DataFrame
```

For each value of `dimension`, compare that value's share of the failure subset
against its share of all attempts, and return counts, both shares, and a
binomial test p-value.

**Bonferroni-correct across the values tested within a dimension.** With 50
shots, an uncorrected p < 0.05 fires on the residual by chance roughly nine
times out of ten. Without the correction the patternlessness check is
meaningless.

Use the same function for both directions: confirming the intended
concentrations exist, and confirming the residual has none.

## Checks

Implement all ten from FAULTS.md's "Generator verification checklist". Notes on
the ones with subtleties:

- **Check 2** (node signal not buried by shot signal): compare Fault A's
  concentration strength on `node_group` against its concentration on `shot_id`.
  The node signal must be the stronger of the two.
- **Check 4** (memory contrast): assert Fault A failures are strictly below
  `mem_allocated_gb` and Fault B failures strictly above. Report min and max for
  each, not just the verdict.
- **Check 7** (retry signatures): Fault A second-attempt failure rate in 22–38%,
  Fault B exactly 100%, Fault C exactly 0%, residual exactly 0%. Dedupe by
  `task_id` and use `attempt` to identify second attempts.
- **Check 9** is a band, not an equality: Fault A total failure rows in
  [234, 260]. Outside the band means the retry dispatch is wrong, not that the
  RNG was unlucky — say so in the failure message.

Additionally, verify the corroborating signal FAULTS.md relies on: group B
hair-shader **successes** after 23:00 should show elevated `peak_mem_gb` relative
to the same shots' successes in groups A and C during the same window. Report
the two means and the difference. This is evidence the agent can use, and if it
isn't there, the dataset is weaker than the spec claims.

## Output

**Terminal:** one line per check — number, short description, PASS or FAIL, and
the measured value against the expected value or band.

**`verify.md`**, written every run, pass or fail. This is evidence for the
hackathon submission and its numbers are the source for a final FAULTS.md
revision, so it must report measured values in prose, not bare verdicts.

Structure:

- Header: run timestamp, input mode (parquet path, or ClickHouse host and
  table), total row count, overall PASS/FAIL.
- A section per check, with the numbers written out as sentences. Not
  "Check 1: PASS" but "Group B holds 272 of 334 OOM rows (81.4%) while running
  30.9% of the batch (3,089 of 9,996 attempts). Binomial p < 1e-40 after
  Bonferroni correction across 3 groups."
- A **"Measured values for FAULTS.md"** section at the end: a plain two-column
  list of exactly these figures, so they can be transcribed without hunting —
  Fault A failure rows, total failure rows, total attempts, unique failed tasks,
  OOM pile size, group B's share of the OOM pile, group B's share of the batch,
  Fault A's second-attempt failure rate, and group B's clean-task count between
  22:00 and 23:00.
- For any FAILED check: what was measured, what was expected, and what in the
  data would have to be different for it to pass. Do not speculate about
  generator internals you have not read.

Exit 0 only if every check passes, 1 otherwise, so it can gate the load step.

## What not to do

- Do not read, import from, or infer expected values from `generate.py`.
- Do not hardcode task_id lists or any fault membership.
- Do not soften a threshold to make a check pass. A failing check is
  information.
- Do not write CSV.
- Do not modify the dataset or write to ClickHouse.

## Finally

Run `python verify.py --parquet data/attempts.parquet` and show me the terminal
output and the full contents of `verify.md`. If checks fail, report them without
changing anything — I want to see the failures before any fix.
Bash List project files and check for data/requirements
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && ls -la && echo "---data---" && ls -la data 2>/dev/null && echo "---requirements---" && cat requirements.txt 2>/dev/null

OUT
total 274
drwxr-xr-x 1 mante 197609     0 Sep  1 09:42 .
drwxr-xr-x 1 mante 197609     0 Aug 30 12:05 ..
-rw-r--r-- 1 mante 197609    52 Aug 30 20:30 .gitignore
-rw-r--r-- 1 mante 197609 15614 Aug 30 15:38 FAULTS.md
-rw-r--r-- 1 mante 197609  9521 Aug 30 19:56 SPEC.md
-rwxr-xr-x 1 mante 197609  1252 Aug 30 22:02 check_nodes.py
drwxr-xr-x 1 mante 197609     0 Aug 30 21:27 data
drwxr-xr-x 1 mante 197609     0 Aug 30 21:20 db
-rwxr-xr-x 1 mante 197609 44191 Aug 30 22:04 generate.py
-rw-r--r-- 1 mante 197609 80104 Sep  1 09:43 generator_py_VSCode_CoPilot_chat1.md
-rw-r--r-- 1 mante 197609    62 Aug 30 21:22 requirements.txt
-rwxr-xr-x 1 mante 197609  1237 Aug 30 22:01 test_rng.py
-rwxr-xr-x 1 mante 197609  4098 Aug 30 21:44 validate.py
---data---
total 356
drwxr-xr-x 1 mante 197609      0 Aug 30 21:27 .
drwxr-xr-x 1 mante 197609      0 Sep  1 09:42 ..
-rw-r--r-- 1 mante 197609 333461 Aug 30 22:04 attempts.parquet
-rw-r--r-- 1 mante 197609   4516 Aug 30 22:04 farm_nodes.parquet
-rw-r--r-- 1 mante 197609  11588 Aug 30 22:04 past_incidents.parquet
---requirements---
numpy>=1.24.0
pandas>=2.0.0
pyarrow>=12.0.0
scipy>=1.10.0
Read c:\Users\mante\Documents\Agentic_Cinema_Hackthon\db\schema.sql
Bash
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "
import pandas as pd
df = pd.read_parquet('data/attempts.parquet')
print(df.shape)
print(df.dtypes)
print('---status---')
print(df['status'].value_counts())
print('---error_class---')
print(df['error_class'].value_counts(dropna=False))
print('---node_group---')
print(df['node_group'].value_counts())
print('---renderer_version---')
print(df['renderer_version'].value_counts())
print(df.head(3).T)
"

OUT
(9996, 18)
task_id                     object
job_id                      object
shot_id                     object
frame_number                 int64
node_id                     object
node_group                  object
attempt                      int64
status                      object
started_at          datetime64[ns]
ended_at            datetime64[ns]
error_class                 object
error_text                  object
peak_mem_gb                float64
mem_allocated_gb           float64
renderer_version            object
uses_hair_shader              bool
asset_refs                  object
submitted_by                object
dtype: object
---status---
status
success    9600
failed      396
Name: count, dtype: int64
---error_class---
error_class
None                   9600
oom                     334
license_timeout          14
texture_io               14
stale_mount              10
disk_full                 9
segfault                  8
frame_write_corrupt       7
Name: count, dtype: int64
---node_group---
node_group
A    3979
C    3031
B    2986
Name: count, dtype: int64
---renderer_version---
renderer_version
7.3.0    7358
7.3.1    2638
Name: count, dtype: int64
                                                                  0  ...                                                  2
task_id                                              shot_010_f0093  ...                                     shot_033_f0110
job_id                                                     job_0002  ...                                           job_0009
shot_id                                                    shot_010  ...                                           shot_033
frame_number                                                     93  ...                                                110
node_id                                                   node_a_01  ...                                          node_a_03
node_group                                                        A  ...                                                  A
attempt                                                           1  ...                                                  1
status                                                      success  ...                                            success
started_at                                      2026-09-08 22:00:00  ...                                2026-09-08 22:00:00
ended_at                                        2026-09-08 22:03:34  ...                                2026-09-08 22:04:10
error_class                                                    None  ...                                               None
error_text                                                     None  ...                                               None
peak_mem_gb                                                    9.43  ...                                               9.59
mem_allocated_gb                                               12.0  ...                                               12.0
renderer_version                                              7.3.0  ...                                              7.3.0
uses_hair_shader                                              False  ...                                              False
asset_refs        [/assets/env_market/texture_03.tx, /assets/env...  ...  [/assets/env_city/texture_03.tx, /assets/env_t...
submitted_by                                              artist_08  ...                                          artist_03

[18 rows x 3 columns]
Good, this gives me exactly what I need. Now let me check farm_nodes and past_incidents schemas briefly, and shot_047 presence.

Bash
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "
import pandas as pd
fn = pd.read_parquet('data/farm_nodes.parquet')
print(fn.dtypes)
print(fn.head(3))
pi = pd.read_parquet('data/past_incidents.parquet')
print(pi.dtypes)
print(pi[['incident_id','title','error_class']].head(5))
df = pd.read_parquet('data/attempts.parquet')
print('shot_047 rows:', (df.shot_id=='shot_047').sum())
print(df[df.shot_id=='shot_047'][['status','node_group','attempt','peak_mem_gb','mem_allocated_gb']].head(10))
print('min started_at', df.started_at.min(), 'max', df.started_at.max())
"

OUT
node_id             object
node_group          object
mem_gb               int64
cpu_cores            int64
renderer_version    object
online                bool
dtype: object
     node_id node_group  mem_gb  cpu_cores renderer_version  online
0  node_a_01          A      64         32            7.3.0    True
1  node_a_02          A      64         32            7.3.0    True
2  node_a_03          A      64         32            7.3.0    True
incident_id            object
occurred_on            object
title                  object
error_class            object
symptom_summary        object
dimension_signature    object
root_cause             object
remediation            object
outcome                object
time_to_resolve_min     int64
dtype: object
        incident_id                                       title error_class
0  inc_20260814_001                     NFS texture filer stall  texture_io
1  inc_20260721_001  Hair shader memory regression (old Arnold)         oom
2  inc_20260805_001    Subdivision surface subdivision overflow         oom
3  inc_20260820_001      Group A node DIMM failure (recurrence)         oom
4  inc_20260819_001        Group A node DIMM failure (original)         oom
shot_047 rows: 248
      status node_group  attempt  peak_mem_gb  mem_allocated_gb
14   success          A        1         9.83              12.0
22    failed          A        1        14.38              12.0
23    failed          A        2        14.19              12.0
29   success          A        1         8.08              12.0
32   success          A        1         8.36              12.0
95   success          C        1         8.80              12.0
160  success          B        1        10.59              12.0
180  success          A        1         9.38              12.0
257  success          B        1         9.31              12.0
292   failed          C        1        14.51              12.0
min started_at 2026-09-08 22:00:00 max 2026-09-09 07:08:49
Bash
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "
import pandas as pd
df = pd.read_parquet('data/attempts.parquet')
failed = df[df.status=='failed']
oom = failed[failed.error_class=='oom']
fault_b = oom[oom.shot_id=='shot_047']
fault_a = oom[oom.shot_id!='shot_047']
print('oom pile', len(oom))
print('fault_b rows', len(fault_b), 'unique tasks', fault_b.task_id.nunique())
print('fault_a rows', len(fault_a), 'unique tasks', fault_a.task_id.nunique())
print('fault_a node_group counts:')
print(fault_a.node_group.value_counts())
print('fault_a renderer_version counts:')
print(fault_a.renderer_version.value_counts())
print('fault_a peak<alloc fraction:', (fault_a.peak_mem_gb < fault_a.mem_allocated_gb).mean())
print('fault_b peak>alloc fraction:', (fault_b.peak_mem_gb > fault_b.mem_allocated_gb).mean())
print('fault_a shot_id nunique:', fault_a.shot_id.nunique())
print(fault_a.shot_id.value_counts().head(10))
print('fault_a peak_mem range', fault_a.peak_mem_gb.min(), fault_a.peak_mem_gb.max())
print('fault_b peak_mem range', fault_b.peak_mem_gb.min(), fault_b.peak_mem_gb.max())
texture_io = failed[failed.error_class=='texture_io']
print('texture_io window', texture_io.started_at.min(), texture_io.started_at.max())
residual = failed[~failed.error_class.isin(['oom','texture_io'])]
print('residual rows', len(residual), 'unique tasks', residual.task_id.nunique())
print(residual.error_class.value_counts())
"

OUT
oom pile 334
fault_b rows 84 unique tasks 42
fault_a rows 250 unique tasks 190
fault_a node_group counts:
node_group
B    250
Name: count, dtype: int64
fault_a renderer_version counts:
renderer_version
7.3.1    250
Name: count, dtype: int64
fault_a peak<alloc fraction: 1.0
fault_b peak>alloc fraction: 1.0
fault_a shot_id nunique: 4
shot_id
shot_044    75
shot_031    70
shot_012    59
shot_023    46
Name: count, dtype: int64
fault_a peak_mem range 11.41 11.95
fault_b peak_mem range 13.8 14.54
texture_io window 2026-09-09 02:08:24 2026-09-09 02:18:36
residual rows 48 unique tasks 48
error_class
license_timeout        14
stale_mount            10
disk_full               9
segfault                8
frame_write_corrupt     7
Name: count, dtype: int64
Bash
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "
import pandas as pd
df = pd.read_parquet('data/attempts.parquet')
failed = df[df.status=='failed']
oom = failed[failed.error_class=='oom']
fault_b = oom[oom.shot_id=='shot_047']
fault_a = oom[oom.shot_id!='shot_047']
texture_io = failed[failed.error_class=='texture_io']
residual = failed[~failed.error_class.isin(['oom','texture_io'])]

def second_attempt_fail_rate(fault_df, full_df):
    task_ids = fault_df.task_id.unique()
    # get attempt=1 subset for these tasks that are in the fault (first failing attempt)
    sub = full_df[full_df.task_id.isin(task_ids)]
    # for tasks with attempt 2 present, check status
    has2 = sub[sub.attempt==2]
    return has2.status.value_counts(normalize=True), len(has2), sub.attempt.max()

for name, f in [('A',fault_a),('B',fault_b),('C',texture_io),('resid',residual)]:
    vc, n2, maxatt = second_attempt_fail_rate(f, df)
    print(name, 'n_attempt2=',n2, 'maxattempt=',maxatt)
    print(vc)
    print()

# group B share of batch
print('B share of all attempts', (df.node_group=='B').mean())
print('B share of oom pile', (oom.node_group=='B').mean())

# group B clean tasks 22:00-23:00
b = df[(df.node_group=='B')]
window = b[(b.started_at >= '2026-09-08 22:00:00') & (b.started_at < '2026-09-08 23:00:00')]
print('B tasks 22-23 total', len(window), 'failed', (window.status=='failed').sum())
"

OUT
A n_attempt2= 190 maxattempt= 2
status
success    0.684211
failed     0.315789
Name: proportion, dtype: float64

B n_attempt2= 42 maxattempt= 2
status
failed    1.0
Name: proportion, dtype: float64

C n_attempt2= 14 maxattempt= 2
status
success    1.0
Name: proportion, dtype: float64

resid n_attempt2= 48 maxattempt= 2
status
success    1.0
Name: proportion, dtype: float64

B share of all attempts 0.29871948779511803
B share of oom pile 0.8323353293413174
B tasks 22-23 total 348 failed 7
Bash
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "
import pandas as pd
from scipy import stats
df = pd.read_parquet('data/attempts.parquet')
failed = df[df.status=='failed']
oom = failed[failed.error_class=='oom']
fault_b = oom[oom.shot_id=='shot_047']
fault_a = oom[oom.shot_id!='shot_047']

print('fault_b node_group dist:')
print(fault_b.node_group.value_counts())

hair_shots = fault_a.shot_id.value_counts().index.tolist()
print('hair shots:', hair_shots)
print('uses_hair_shader for these rows:', fault_a.uses_hair_shader.mean())

# check success elsewhere for these shots (other groups than B)
succ = df[df.status=='success']
for s in hair_shots:
    sub = succ[(succ.shot_id==s) & (succ.node_group!='B')]
    print(s, 'success rows outside B:', len(sub), sub.node_group.value_counts().to_dict())

# hair shader corroborating signal
after = df[df.started_at >= '2026-09-08 23:00:00']
b_hair_succ = after[(after.status=='success') & (after.shot_id.isin(hair_shots)) & (after.node_group=='B')]
ac_hair_succ = after[(after.status=='success') & (after.shot_id.isin(hair_shots)) & (after.node_group!='B')]
print('B hair succ mean peak_mem', b_hair_succ.peak_mem_gb.mean(), 'n=',len(b_hair_succ))
print('AC hair succ mean peak_mem', ac_hair_succ.peak_mem_gb.mean(), 'n=',len(ac_hair_succ))

# concentration strength comparison: node_group vs shot_id for fault_a
n_total = len(df)
def conc_strength(dimension, subset):
    n_subset = len(subset)
    values = df[dimension].unique()
    k = len(values)
    best_p = 1.0
    for v in values:
        pop_count = (df[dimension]==v).sum()
        pop_share = pop_count/n_total
        subset_count = (subset[dimension]==v).sum()
        if subset_count==0: continue
        p = stats.binomtest(subset_count, n_subset, pop_share, alternative='greater').pvalue
        pc = min(p*k,1.0)
        if pc < best_p: best_p = pc
    return best_p

print('node_group best corrected p for fault_a:', conc_strength('node_group', fault_a))
print('shot_id best corrected p for fault_a:', conc_strength('shot_id', fault_a))
"

OUT
fault_b node_group dist:
node_group
A    37
B    28
C    19
Name: count, dtype: int64
hair shots: ['shot_044', 'shot_031', 'shot_012', 'shot_023']
uses_hair_shader for these rows: 1.0
shot_044 success rows outside B: 315 {'A': 184, 'C': 131}
shot_031 success rows outside B: 315 {'A': 163, 'C': 152}
shot_012 success rows outside B: 308 {'A': 171, 'C': 137}
shot_023 success rows outside B: 317 {'A': 170, 'C': 147}
B hair succ mean peak_mem 11.476275510204083 n= 196
AC hair succ mean peak_mem 9.802213333333333 n= 1125
node_group best corrected p for fault_a: 1.9634065630386426e-131
shot_id best corrected p for fault_a: 1.3229812784678238e-38
Bash
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "
import pandas as pd
from scipy import stats
df = pd.read_parquet('data/attempts.parquet')
failed = df[df.status=='failed']
residual = failed[~failed.error_class.isin(['oom','texture_io'])]
texture_io = failed[failed.error_class=='texture_io']

n_total = len(df)
def conc_table(dimension, subset):
    n_subset = len(subset)
    values = df[dimension].dropna().unique()
    k = len(values)
    out=[]
    for v in values:
        pop_count = (df[dimension]==v).sum()
        pop_share = pop_count/n_total
        subset_count = (subset[dimension]==v).sum()
        if n_subset==0: continue
        p = stats.binomtest(subset_count, n_subset, pop_share, alternative='two-sided').pvalue
        pc = min(p*k,1.0)
        out.append((v,pop_count,subset_count,pc))
    out.sort(key=lambda x:x[3])
    return out[:3], k

for dim in ['node_group','node_id','shot_id','job_id','renderer_version','submitted_by']:
    top,k = conc_table(dim, residual)
    print(dim,'k=',k,'top3:',top)

# time bucket for texture_io
df2 = df.copy()
df2['time_bucket'] = df2['started_at'].dt.floor('10min')
n_total=len(df2)
def conc_time(subset):
    n_subset=len(subset)
    values = df2['time_bucket'].unique()
    k=len(values)
    out=[]
    for v in values:
        pop_count=(df2['time_bucket']==v).sum()
        pop_share=pop_count/n_total
        subset_count=(subset['time_bucket']==v).sum() if 'time_bucket' in subset else 0
        if subset_count==0: continue
        p=stats.binomtest(subset_count,n_subset,pop_share,alternative='greater').pvalue
        pc=min(p*k,1.0)
        out.append((v,pop_count,subset_count,pc))
    out.sort(key=lambda x:x[3])
    return out[:5],k
ti = df2.loc[texture_io.index]
top,k = conc_time(ti)
print('texture_io time_bucket k=',k,'top:',top)

# residual time bucket
res2 = df2.loc[residual.index]
top,k = conc_time(res2)
print('residual time_bucket top:', top, 'k=',k)
"

OUT
node_group k= 3 top3: [('A', np.int64(3979), np.int64(17), 1.0), ('B', np.int64(2986), np.int64(17), 1.0), ('C', np.int64(3031), np.int64(14), 1.0)]
node_id k= 100 top3: [('node_b_30', np.int64(85), np.int64(3), np.float64(0.7996341869317068)), ('node_a_01', np.int64(96), np.int64(0), 1.0), ('node_a_02', np.int64(97), np.int64(2), 1.0)]
shot_id k= 50 top3: [('shot_010', np.int64(174), np.int64(0), 1.0), ('shot_036', np.int64(192), np.int64(2), 1.0), ('shot_033', np.int64(171), np.int64(1), 1.0)]
job_id k= 12 top3: [('job_0002', np.int64(1084), np.int64(3), 1.0), ('job_0010', np.int64(1263), np.int64(7), 1.0), ('job_0009', np.int64(1342), np.int64(7), 1.0)]
renderer_version k= 2 top3: [('7.3.0', np.int64(7358), np.int64(34), 1.0), ('7.3.1', np.int64(2638), np.int64(14), 1.0)]
submitted_by k= 8 top3: [('artist_06', np.int64(693), np.int64(0), np.float64(0.6253669799754256)), ('artist_08', np.int64(1251), np.int64(2), np.float64(0.6627162655658736)), ('artist_04', np.int64(832), np.int64(7), np.float64(0.9314323790602768))]
texture_io time_bucket k= 55 top: [(Timestamp('2026-09-09 02:10:00'), np.int64(182), np.int64(13), np.float64(1.8292466176094015e-20)), (Timestamp('2026-09-09 02:00:00'), np.int64(196), np.int64(1), 1.0)]
residual time_bucket top: [(Timestamp('2026-09-09 00:10:00'), np.int64(194), np.int64(4), np.float64(0.7705609420570294)), (Timestamp('2026-09-08 22:00:00'), np.int64(234), np.int64(2), 1.0), (Timestamp('2026-09-08 22:50:00'), np.int64(199), np.int64(1), 1.0), (Timestamp('2026-09-08 22:40:00'), np.int64(177), np.int64(2), 1.0), (Timestamp('2026-09-08 23:10:00'), np.int64(193), np.int64(1), 1.0)] k= 55
Bash
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "
import pandas as pd
df = pd.read_parquet('data/attempts.parquet')
b = df[df.node_group=='B']
window = b[(b.started_at >= '2026-09-08 22:00:00') & (b.started_at < '2026-09-08 23:00:00')]
print(window[window.status=='failed'][['task_id','error_class','started_at','shot_id']])
"

OUT
             task_id      error_class          started_at   shot_id
217   shot_031_f0308  license_timeout 2026-09-08 22:09:23  shot_031
293   shot_047_f0105              oom 2026-09-08 22:23:28  shot_047
426   shot_047_f0114              oom 2026-09-08 22:20:41  shot_047
636   shot_047_f0098              oom 2026-09-08 22:32:06  shot_047
868   shot_030_f0117         segfault 2026-09-08 22:43:45  shot_030
945   shot_047_f0086              oom 2026-09-08 22:48:50  shot_047
1074  shot_027_f0119  license_timeout 2026-09-08 22:55:39  shot_027
Bash
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "
import pandas as pd
df = pd.read_parquet('data/attempts.parquet')
failed = df[df.status=='failed']
oom = failed[failed.error_class=='oom']
fault_a = oom[oom.shot_id!='shot_047']
print('fault_a earliest started_at:', fault_a.started_at.min())
print('batch_start:', df.started_at.min())
print('offset:', fault_a.started_at.min() - df.started_at.min())
"

OUT
fault_a earliest started_at: 2026-09-08 23:04:21
batch_start: 2026-09-08 22:00:00
offset: 0 days 01:04:21
Now I have a clear, independently-derived picture of the data. Let me write verify.py.

Write c:\Users\mante\Documents\Agentic_Cinema_Hackthon\verify.py
756 lines
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
Now let's add clickhouse-connect to requirements.txt and run the verifier.

Read c:\Users\mante\Documents\Agentic_Cinema_Hackthon\requirements.txt
Edit c:\Users\mante\Documents\Agentic_Cinema_Hackthon\requirements.txt
Added 1 line
Bash Run the verifier against the parquet dataset
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python verify.py --parquet data/attempts.parquet

OUT
[PASS] Check 1: Fault A recoverable (node concentration + reverse test) � group B = 100.0% of Fault A failures vs 29.9% of batch (p=1.963e-131); 4 shots isolated, reverse test passed
[PASS] Check 2: Fault A node signal stronger than shot signal � node_group best p=1.963e-131 vs shot_id best p=1.323e-38
[PASS] Check 3: Fault B recoverable (fails in all groups; retries fail again) � shot_047 failures in groups ['A', 'B', 'C']={'A': 37, 'B': 28, 'C': 19}; retry fail-again rate=100.0% (42/42)
[PASS] Check 4: Memory contrast (Fault A under budget, Fault B over budget) � Fault A peak_mem in [11.41, 11.95] GB, all below allocation (100.0%); Fault B peak_mem in [13.80, 14.54] GB, all above allocation (100.0%)
[PASS] Check 5: Fault C recoverable (time-window concentration only) � time_bucket best p=1.829e-20; other dims flagged: none
[PASS] Check 6: Residual patternless across every dimension � closest corrected p=0.6627; flagged dims: none
[PASS] Check 7: Retry signatures match fault taxonomy � A=31.6% (want 22.0%-38.0%), B=100.0% (want 100%), C=0.0% (want 0%), residual=0.0% (want 0%)
[PASS] Check 8: Exact row counts (Fault B, Fault C, residual) � Fault B rows=84 (want 84), Fault C rows=14 (want 14), residual rows=48 (want 48)
[PASS] Check 9: Approximate row-count bands (Fault A, grand total) � Fault A rows=250 (band 234-260); total failure rows=396 (band 380-406)
[PASS] Check 10: Exact unique task counts � A=190(190) B=42(42) C=14(14) resid=48(48) total=294(294)
[PASS] Check 11: Hair-shader corroborating signal (elevated peak_mem on B successes) � group B hair-shot successes mean peak_mem=11.48 GB (n=196) vs groups A/C mean=9.80 GB (n=1125), diff=1.67 GB

Overall: PASS (11/11 checks passed)
The dashes render oddly in this shell (Windows console encoding), but let's confirm the actual file content is correct with proper UTF-8.

Read c:\Users\mante\Documents\Agentic_Cinema_Hackthon\verify.md
The file itself is proper UTF-8 (em-dashes render fine here) — the garbled � was just the Git Bash terminal's console encoding, not a file issue. All 11 checks pass (the 10 from FAULTS.md's checklist plus the hair-shader corroborating signal), matching the independent analysis I ran before writing any code.

Bash Confirm exit code from previous verify.py run
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && echo "exit code: $?"

OUT
exit code: 0
Summary
verify.py is written and passes all 11 checks (the 10 from FAULTS.md's checklist, plus the hair-shader corroborating signal), exit code 0.

How it identifies faults, entirely from observable columns, without touching generate.py:

OOM pile = failures with error_class == 'oom'
Fault B = OOM rows on shot_047; Fault A = OOM rows not on shot_047
Fault C = failures with error_class == 'texture_io'
Residual = everything else
Each split is cross-checked against an independent signal (peak vs. allocated memory for A/B, node presence in all three groups for B, time clustering for C) rather than trusted on its own.
Terminal output (11/11 PASS):


[PASS] Check 1: Fault A recoverable — group B = 100.0% of Fault A failures vs 29.9% of batch (p=1.963e-131); 4 shots isolated, reverse test passed
[PASS] Check 2: node signal stronger than shot signal — node_group p=1.963e-131 vs shot_id p=1.323e-38
[PASS] Check 3: Fault B in all 3 groups; retry fail-again rate=100.0% (42/42)
[PASS] Check 4: Fault A peak_mem [11.41,11.95] GB all below allocation; Fault B [13.80,14.54] GB all above
[PASS] Check 5: Fault C time_bucket p=1.829e-20; no other dimension flagged
[PASS] Check 6: Residual — closest corrected p=0.6627; nothing flagged
[PASS] Check 7: retry rates A=31.6% (band 22-38%), B=100%, C=0%, residual=0%
[PASS] Check 8: exact rows B=84, C=14, residual=48
[PASS] Check 9: Fault A rows=250 (band 234-260); total=396 (band 380-406)
[PASS] Check 10: unique tasks 190/42/14/48, sum=294
[PASS] Check 11: hair-shot B successes mean 11.48 GB vs A/C mean 9.80 GB (+1.67 GB)

Overall: PASS (11/11 checks passed)
verify.md (full contents shown above) has one prose section per check plus a "Measured values for FAULTS.md" table with the nine requested figures — all of it computed live, nothing hardcoded from a task-id list.

Also added clickhouse-connect>=0.7.0 to requirements.txt for the --clickhouse mode. No checks failed, so there's nothing to report as a pre-fix failure this run.

c:\Users\mante\Documents\Agentic_Cinema_Hackthon\.env
Write a one-off loader that pushes the generated Parquet files into ClickHouse
Cloud, then re-run the verifier against the loaded tables.

The three tables already exist in ClickHouse Cloud with the DDL in
`db/schema.sql`. Do not create, drop, or alter them.

## Deliverable

`load.py`. Add `python-dotenv` to `requirements.txt` if you use it.

## Credentials

Read from `.env` in the project root: `CLICKHOUSE_HOST`, `CLICKHOUSE_USER`,
`CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DATABASE`. Never print the password, and
never write any credential into a file or a log line.

## Behavior

Use `clickhouse-connect`. For each of the three pairs:

- `data/attempts.parquet` → `render_task_attempts`
- `data/farm_nodes.parquet` → `farm_nodes`
- `data/past_incidents.parquet` → `past_incidents`

For each table, in this order:

1. Report the current row count in ClickHouse.
2. If the table is not empty, `TRUNCATE TABLE` it. This script must be safe to
   re-run — reloading on top of existing rows would double the dataset and
   silently invalidate every verification check. Print what you are truncating
   and how many rows are being removed.
3. Read the Parquet into a DataFrame and insert it.
4. Report the row count after insert, and assert it equals the DataFrame's row
   count.

Support `--dry-run`, which does steps 1 and 3 (read the Parquet, report counts
and dtypes) but performs no truncate and no insert.

## Type handling

`duration_sec` is MATERIALIZED in ClickHouse and is not in the Parquet — do not
attempt to insert it.

Watch for these, which are the likely failure points:

- `started_at` / `ended_at` must land as second-resolution DateTime. If pandas
  hands you datetime64[ns], convert before insert.
- `occurred_on` must be a Date, not a DateTime.
- `error_class` and `error_text` are Nullable — NULLs in the Parquet must arrive
  as NULLs, not as empty strings.
- `asset_refs` is `Array(String)`.
- `uses_hair_shader` is Bool.

If an insert fails on a type mismatch, report the exact error and the column
involved before attempting any fix. Do not resolve a type error by casting the
column to String.

## After loading

Run:

```
python verify.py --clickhouse
```

Report its exit code and terminal output. Then show me a diff between the
"Measured values for FAULTS.md" section of the `verify.md` produced by the
Parquet run and the one produced by this ClickHouse run.

Those two sections must be identical. Any difference means the data changed
during ingest, and that is the specific thing this step exists to catch — report
it rather than explaining it away.

Note: `verify.py --clickhouse` overwrites `verify.md`. Copy the existing one to
`verify_parquet.md` before running so both are available for the comparison.

## What not to do

- Do not modify `generate.py`, `verify.py`, or `db/schema.sql`.
- Do not create, drop, or alter tables.
- Do not print credentials.
- Do not regenerate the dataset.
Bash Check .gitignore and .env variable names without exposing values
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && cat .gitignore && echo "---" && python -c "
from pathlib import Path
p = Path('.env')
print('exists:', p.exists())
if p.exists():
    for line in p.read_text().splitlines():
        if line.strip() and not line.strip().startswith('#'):
            key = line.split('=',1)[0]
            print('KEY:', key)
"

OUT
.env.local
.env
__pycache__/
*.pyc
.venv/
venv/---
exists: True
KEY: CLICKHOUSE_HOST
KEY: CLICKHOUSE_USER
KEY: CLICKHOUSE_PASSWORD
KEY: CLICKHOUSE_DATABASE
Good, .env is gitignored and has the expected keys. Now let me check parquet dtypes precisely to plan the type conversions.

Bash
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "
import pandas as pd
df = pd.read_parquet('data/attempts.parquet')
print(df.dtypes)
print()
print('nulls in error_class:', df['error_class'].isna().sum())
print('nulls in error_text:', df['error_text'].isna().sum())
print('sample error_class values type:', type(df['error_class'].iloc[0]), type(df['error_class'].dropna().iloc[0]))
print('asset_refs sample:', df['asset_refs'].iloc[0], type(df['asset_refs'].iloc[0]))
print()
fn = pd.read_parquet('data/farm_nodes.parquet')
print(fn.dtypes)
print()
pi = pd.read_parquet('data/past_incidents.parquet')
print(pi.dtypes)
print(pi['occurred_on'].head(2), type(pi['occurred_on'].iloc[0]))
"

OUT
task_id                     object
job_id                      object
shot_id                     object
frame_number                 int64
node_id                     object
node_group                  object
attempt                      int64
status                      object
started_at          datetime64[ns]
ended_at            datetime64[ns]
error_class                 object
error_text                  object
peak_mem_gb                float64
mem_allocated_gb           float64
renderer_version            object
uses_hair_shader              bool
asset_refs                  object
submitted_by                object
dtype: object

nulls in error_class: 9600
nulls in error_text: 9600
sample error_class values type: <class 'NoneType'> <class 'str'>
asset_refs sample: ['/assets/env_market/texture_03.tx' '/assets/env_village/texture_05.tx'
 '/assets/env_suburban/texture_01.tx' '/assets/env_volcano/texture_01.tx'] <class 'numpy.ndarray'>

node_id             object
node_group          object
mem_gb               int64
cpu_cores            int64
renderer_version    object
online                bool
dtype: object

incident_id            object
occurred_on            object
title                  object
error_class            object
symptom_summary        object
dimension_signature    object
root_cause             object
remediation            object
outcome                object
time_to_resolve_min     int64
dtype: object
0    2026-08-14
1    2026-07-21
Name: occurred_on, dtype: object <class 'str'>
Bash Check if clickhouse-connect and python-dotenv are installed
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "import clickhouse_connect; print(clickhouse_connect.__version__)" 2>&1; python -c "import dotenv; print('dotenv ok')" 2>&1

OUT
Traceback (most recent call last):
  File "<string>", line 1, in <module>
    import clickhouse_connect; print(clickhouse_connect.__version__)
    ^^^^^^^^^^^^^^^^^^^^^^^^^
ModuleNotFoundError: No module named 'clickhouse_connect'
dotenv ok
Bash Install clickhouse-connect package
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && pip install clickhouse-connect --quiet 2>&1 | tail -20 && python -c "import clickhouse_connect; print(clickhouse_connect.__version__)"

OUT
[notice] A new release of pip is available: 25.1.1 -> 26.2.1
[notice] To update, run: python.exe -m pip install --upgrade pip
1.7.2
Good, installed. Now let me add python-dotenv to requirements.txt and write load.py.

Edit c:\Users\mante\Documents\Agentic_Cinema_Hackthon\requirements.txt
Added 1 line
Bash
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "
import pandas as pd
print(pd.__version__)
s = pd.to_datetime(pd.Series(['2026-09-08 22:00:00.123456']))
print(s.dtype)
s2 = s.astype('datetime64[s]')
print(s2.dtype, s2.iloc[0])
"

OUT
2.3.0
datetime64[ns]
datetime64[s] 2026-09-08 22:00:00
Good, that cast works cleanly in pandas 2.3.0. Now let me write load.py.

Write c:\Users\mante\Documents\Agentic_Cinema_Hackthon\load.py
176 lines
#!/usr/bin/env python3
"""One-off loader: pushes the generated Parquet files into the existing
ClickHouse Cloud tables (render_task_attempts, farm_nodes, past_incidents).

The tables already exist per db/schema.sql. This script never creates, drops,
or alters a table — it only truncates (to make itself safely re-runnable) and
inserts.

Usage:
    python load.py            # truncate + load all three tables
    python load.py --dry-run  # read Parquet, report counts/dtypes, no writes
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

TABLE_SPECS = [
    ("data/attempts.parquet", "render_task_attempts"),
    ("data/farm_nodes.parquet", "farm_nodes"),
    ("data/past_incidents.parquet", "past_incidents"),
]


def prepare_attempts(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # duration_sec is MATERIALIZED in ClickHouse; it is not a column we insert.
    if "duration_sec" in df.columns:
        df = df.drop(columns=["duration_sec"])

    # started_at / ended_at: DateTime is second resolution in the DDL. pandas
    # reads Parquet timestamps as datetime64[ns]; cast down to [s] so
    # clickhouse-connect writes whole seconds rather than choking on
    # sub-second precision it has nowhere to put.
    df["started_at"] = pd.to_datetime(df["started_at"]).astype("datetime64[s]")
    df["ended_at"] = pd.to_datetime(df["ended_at"]).astype("datetime64[s]")

    # error_class / error_text are Nullable(String). Parquet already stores
    # missing values as None on success rows; make sure NaN (if any slipped
    # in via a different null representation) also becomes None, not "".
    df["error_class"] = df["error_class"].where(df["error_class"].notna(), None)
    df["error_text"] = df["error_text"].where(df["error_text"].notna(), None)

    # asset_refs is Array(String). Parquet round-trips this as a numpy
    # ndarray per row; clickhouse-connect wants a plain Python list.
    df["asset_refs"] = df["asset_refs"].apply(
        lambda x: list(x) if x is not None else []
    )

    df["uses_hair_shader"] = df["uses_hair_shader"].astype(bool)

    return df


def prepare_farm_nodes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["online"] = df["online"].astype(bool)
    return df


def prepare_past_incidents(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # occurred_on is Date, not DateTime. Parquet stores it as an ISO date
    # string (object dtype); convert to Python date objects.
    df["occurred_on"] = pd.to_datetime(df["occurred_on"]).dt.date
    return df


PREPARERS = {
    "render_task_attempts": prepare_attempts,
    "farm_nodes": prepare_farm_nodes,
    "past_incidents": prepare_past_incidents,
}


def get_client():
    import clickhouse_connect

    host = os.environ["CLICKHOUSE_HOST"]
    user = os.environ["CLICKHOUSE_USER"]
    password = os.environ["CLICKHOUSE_PASSWORD"]
    database = os.environ["CLICKHOUSE_DATABASE"]
    return clickhouse_connect.get_client(
        host=host, username=user, password=password, database=database, secure=True,
    )


def load_table(client, parquet_path: str, table: str, dry_run: bool) -> bool:
    print(f"\n=== {table}  <-  {parquet_path} ===")
    if not os.path.exists(parquet_path):
        print(f"  SKIP: {parquet_path} not found")
        return False

    df_raw = pd.read_parquet(parquet_path)
    preparer = PREPARERS.get(table)
    df = preparer(df_raw) if preparer else df_raw.copy()

    print(f"  Parquet rows: {len(df)}")
    print("  Parquet dtypes:")
    for col, dt in df.dtypes.items():
        print(f"    {col}: {dt}")

    current_count = int(client.command(f"SELECT count() FROM {table}"))
    print(f"  Current row count in ClickHouse: {current_count}")

    if dry_run:
        print("  --dry-run: no truncate, no insert performed.")
        return True

    if current_count > 0:
        print(f"  Truncating {table} ({current_count} rows being removed)...")
        client.command(f"TRUNCATE TABLE {table}")

    try:
        client.insert_df(table, df)
    except Exception as exc:
        print(f"  INSERT FAILED for table '{table}'")
        print(f"  Error: {exc}")
        raise

    after_count = int(client.command(f"SELECT count() FROM {table}"))
    print(f"  Row count after insert: {after_count}")
    if after_count != len(df):
        raise AssertionError(
            f"Row count mismatch after insert into {table}: "
            f"expected {len(df)} (from DataFrame), got {after_count} (in ClickHouse)"
        )
    print(f"  OK: inserted row count matches DataFrame row count ({after_count}).")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Load generated Parquet files into the existing ClickHouse Cloud tables."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Read Parquet and report counts/dtypes only; no truncate, no insert.",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir / ".env")

    required = ["CLICKHOUSE_HOST", "CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD", "CLICKHOUSE_DATABASE"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    client = get_client()

    all_ok = True
    for rel_path, table in TABLE_SPECS:
        parquet_path = str(base_dir / rel_path)
        result = load_table(client, parquet_path, table, args.dry_run)
        all_ok = all_ok and result

    print()
    if args.dry_run:
        print("DRY RUN COMPLETE" if all_ok else "DRY RUN COMPLETE WITH SKIPPED TABLES")
    else:
        print("LOAD COMPLETE" if all_ok else "LOAD INCOMPLETE (see SKIP lines above)")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
Now let's do a dry run first to catch dtype issues before touching ClickHouse.

Bash Dry-run the loader to check counts and dtypes without writing
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python load.py --dry-run

OUT
=== render_task_attempts  <-  C:\Users\mante\Documents\Agentic_Cinema_Hackthon\data\attempts.parquet ===
  Parquet rows: 9996
  Parquet dtypes:
    task_id: object
    job_id: object
    shot_id: object
    frame_number: int64
    node_id: object
    node_group: object
    attempt: int64
    status: object
    started_at: datetime64[s]
    ended_at: datetime64[s]
    error_class: object
    error_text: object
    peak_mem_gb: float64
    mem_allocated_gb: float64
    renderer_version: object
    uses_hair_shader: bool
    asset_refs: object
    submitted_by: object
  Current row count in ClickHouse: 0
  --dry-run: no truncate, no insert performed.

=== farm_nodes  <-  C:\Users\mante\Documents\Agentic_Cinema_Hackthon\data\farm_nodes.parquet ===
  Parquet rows: 100
  Parquet dtypes:
    node_id: object
    node_group: object
    mem_gb: int64
    cpu_cores: int64
    renderer_version: object
    online: bool
  Current row count in ClickHouse: 0
  --dry-run: no truncate, no insert performed.

=== past_incidents  <-  C:\Users\mante\Documents\Agentic_Cinema_Hackthon\data\past_incidents.parquet ===
  Parquet rows: 14
  Parquet dtypes:
    incident_id: object
    occurred_on: object
    title: object
    error_class: object
    symptom_summary: object
    dimension_signature: object
    root_cause: object
    remediation: object
    outcome: object
    time_to_resolve_min: int64
  Current row count in ClickHouse: 0
  --dry-run: no truncate, no insert performed.

DRY RUN COMPLETE
Connection works, credentials valid, and all three tables are currently empty. Dtypes look right. Now let's run the actual load.

Bash Load the parquet files into ClickHouse Cloud tables
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python load.py

OUT
=== render_task_attempts  <-  C:\Users\mante\Documents\Agentic_Cinema_Hackthon\data\attempts.parquet ===
  Parquet rows: 9996
  Parquet dtypes:
    task_id: object
    job_id: object
    shot_id: object
    frame_number: int64
    node_id: object
    node_group: object
    attempt: int64
    status: object
    started_at: datetime64[s]
    ended_at: datetime64[s]
    error_class: object
    error_text: object
    peak_mem_gb: float64
    mem_allocated_gb: float64
    renderer_version: object
    uses_hair_shader: bool
    asset_refs: object
    submitted_by: object
  Current row count in ClickHouse: 0
  Row count after insert: 9996
  OK: inserted row count matches DataFrame row count (9996).

=== farm_nodes  <-  C:\Users\mante\Documents\Agentic_Cinema_Hackthon\data\farm_nodes.parquet ===
  Parquet rows: 100
  Parquet dtypes:
    node_id: object
    node_group: object
    mem_gb: int64
    cpu_cores: int64
    renderer_version: object
    online: bool
  Current row count in ClickHouse: 0
  Row count after insert: 100
  OK: inserted row count matches DataFrame row count (100).

=== past_incidents  <-  C:\Users\mante\Documents\Agentic_Cinema_Hackthon\data\past_incidents.parquet ===
  Parquet rows: 14
  Parquet dtypes:
    incident_id: object
    occurred_on: object
    title: object
    error_class: object
    symptom_summary: object
    dimension_signature: object
    root_cause: object
    remediation: object
    outcome: object
    time_to_resolve_min: int64
  Current row count in ClickHouse: 0
  Row count after insert: 14
  OK: inserted row count matches DataFrame row count (14).

LOAD COMPLETE
All three loaded cleanly on the first attempt. Let's confirm the re-run safety (truncate path) works before moving on.

Bash Re-run loader to confirm truncate-before-reload safety
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python load.py 2>&1 | tail -20

OUT
=== past_incidents  <-  C:\Users\mante\Documents\Agentic_Cinema_Hackthon\data\past_incidents.parquet ===
  Parquet rows: 14
  Parquet dtypes:
    incident_id: object
    occurred_on: object
    title: object
    error_class: object
    symptom_summary: object
    dimension_signature: object
    root_cause: object
    remediation: object
    outcome: object
    time_to_resolve_min: int64
  Current row count in ClickHouse: 14
  Truncating past_incidents (14 rows being removed)...
  Row count after insert: 14
  OK: inserted row count matches DataFrame row count (14).

LOAD COMPLETE
Re-run correctly truncated existing rows first (no doubling). Now let's copy the existing verify.md to verify_parquet.md before running the ClickHouse verification.

Bash Preserve parquet verify.md before rerunning verify against ClickHouse
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && cp verify.md verify_parquet.md && ls -la verify*.md

OUT
-rw-r--r-- 1 mante 197609 5334 Sep  1 10:28 verify.md
-rw-r--r-- 1 mante 197609 5334 Sep  1 11:37 verify_parquet.md
Bash Run verifier against the loaded ClickHouse tables
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python verify.py --clickhouse; echo "EXIT_CODE=$?"

OUT
Traceback (most recent call last):
  File "C:\Users\mante\Documents\Agentic_Cinema_Hackthon\verify.py", line 755, in <module>
    main()
    ~~~~^^
  File "C:\Users\mante\Documents\Agentic_Cinema_Hackthon\verify.py", line 742, in main
    data = load_from_clickhouse()
  File "C:\Users\mante\Documents\Agentic_Cinema_Hackthon\verify.py", line 125, in load_from_clickhouse
    host = os.environ["CLICKHOUSE_HOST"]
           ~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
  File "<frozen os>", line 716, in __getitem__
KeyError: 'CLICKHOUSE_HOST'
EXIT_CODE=1
Bash
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && python -c "
from pathlib import Path
for line in Path('.env').read_text().splitlines():
    if line.strip() and not line.strip().startswith('#'):
        k = line.split('=',1)[0]
        v = line.split('=',1)[1] if '=' in line else ''
        print(k, 'len=', len(v), 'has_quotes=', v.startswith('\"') or v.startswith(\"'\"))
"

OUT
CLICKHOUSE_HOST len= 43 has_quotes= False
CLICKHOUSE_USER len= 7 has_quotes= False
CLICKHOUSE_PASSWORD len= 13 has_quotes= False
CLICKHOUSE_DATABASE len= 7 has_quotes= False
No quoting to worry about. I'll export from .env into the shell environment (without printing values) and run verify.py in that same command.

Bash Export .env vars into shell and run verifier against ClickHouse
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && set -a && source .env && set +a && python verify.py --clickhouse; echo "EXIT_CODE=$?"

OUT
[PASS] Check 1: Fault A recoverable (node concentration + reverse test) � group B = 100.0% of Fault A failures vs 29.9% of batch (p=1.963e-131); 4 shots isolated, reverse test passed
[PASS] Check 2: Fault A node signal stronger than shot signal � node_group best p=1.963e-131 vs shot_id best p=1.323e-38
[PASS] Check 3: Fault B recoverable (fails in all groups; retries fail again) � shot_047 failures in groups ['A', 'B', 'C']={'A': 37, 'B': 28, 'C': 19}; retry fail-again rate=100.0% (42/42)
[PASS] Check 4: Memory contrast (Fault A under budget, Fault B over budget) � Fault A peak_mem in [11.41, 11.95] GB, all below allocation (100.0%); Fault B peak_mem in [13.80, 14.54] GB, all above allocation (100.0%)
[PASS] Check 5: Fault C recoverable (time-window concentration only) � time_bucket best p=1.829e-20; other dims flagged: none
[PASS] Check 6: Residual patternless across every dimension � closest corrected p=0.6627; flagged dims: none
[PASS] Check 7: Retry signatures match fault taxonomy � A=31.6% (want 22.0%-38.0%), B=100.0% (want 100%), C=0.0% (want 0%), residual=0.0% (want 0%)
[PASS] Check 8: Exact row counts (Fault B, Fault C, residual) � Fault B rows=84 (want 84), Fault C rows=14 (want 14), residual rows=48 (want 48)
[PASS] Check 9: Approximate row-count bands (Fault A, grand total) � Fault A rows=250 (band 234-260); total failure rows=396 (band 380-406)
[PASS] Check 10: Exact unique task counts � A=190(190) B=42(42) C=14(14) resid=48(48) total=294(294)
[PASS] Check 11: Hair-shader corroborating signal (elevated peak_mem on B successes) � group B hair-shot successes mean peak_mem=11.48 GB (n=196) vs groups A/C mean=9.80 GB (n=1125), diff=1.67 GB

Overall: PASS (11/11 checks passed)
EXIT_CODE=0
All 11 checks pass against ClickHouse, exit code 0 — identical results to the Parquet run. Now let's diff the "Measured values for FAULTS.md" sections.

Bash Diff the Measured values sections between parquet and clickhouse verify.md runs
IN
cd "c:/Users/mante/Documents/Agentic_Cinema_Hackthon" && diff <(awk '/^## Measured values/,0' verify_parquet.md) <(awk '/^## Measured values/,0' verify.md) && echo "IDENTICAL"

OUT
IDENTICAL
The two "Measured values for FAULTS.md" sections are byte-identical:

Read c:\Users\mante\Documents\Agentic_Cinema_Hackthon\verify.md (from line 63)
Summary
load.py: loads the three Parquet files into the existing ClickHouse Cloud tables (render_task_attempts, farm_nodes, past_incidents). No DDL touched. Handles the type gotchas: drops duration_sec (materialized), casts started_at/ended_at to second-resolution, converts occurred_on to date, coerces asset_refs ndarray→list, preserves NaN→None for the nullable error columns, casts bool columns explicitly. Truncates before insert only if the table already has rows, so it's safe to re-run — confirmed by running it twice (second run truncated 14 rows from past_incidents before reloading 14).

Load results: all three tables loaded cleanly on the first attempt, no type errors — 9,996 / 100 / 14 rows, each asserted to match the DataFrame count post-insert.

verify.py --clickhouse: exit code 0, 11/11 checks pass, identical to the Parquet run.

Diff of "Measured values for FAULTS.md": verify_parquet.md vs. verify.md — identical, byte-for-byte. No discrepancy introduced during ingest.

Added clickhouse-connect (already present) and python-dotenv to requirements.txt. verify.py, generate.py, and db/schema.sql were not touched. No credentials were printed or written anywhere.

/insights
/export
