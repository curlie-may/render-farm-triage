# render-farm-triage

An agent that diagnoses overnight render farm failures across every job at once, separates simultaneous root causes from unrelated noise, and proposes an ordered re-queue plan that a human approves step by step.

Built for the **Agentic Cinema: The Blockbuster Hackathon**, ClickHouse track. Gemini agent on Google ADK, deployed on Cloud Run, reading from ClickHouse Cloud via the official `mcp-clickhouse` MCP server.

- **Live app:** https://render-farm-triage.vercel.app
- **Demo video:** [VIDEO_URL]
- **Ground-truth fault spec:** [`FAULTS.md`](FAULTS.md) · **Design spec:** [`SPEC.md`](SPEC.md) · **Verification results:** [`verify.md`](verify.md)

---

## The problem

A render farm is a few hundred machines that render movie frames overnight — one task per frame, thousands of tasks a night, every failure logged. In the morning, someone has to look at the failed tasks and work out which failures share a cause, which are noise, and what to re-run first, before dailies.

Schedulers show failures per job and per node. Nobody looks across the whole farm at once, and nothing separates two faults that happen to throw the same error. That is the gap this agent fills.

## What the agent does

Given last night's batch (9,996 task attempts, 294 failed tasks across a dozen jobs), the agent:

1. **Summarizes failures** and pulls representative error samples.
2. **Tests each dimension for concentration above base rate** — shot, node group, renderer version, time window — using a binomial test with Bonferroni correction for multiple comparisons. A dimension lighting up is a hypothesis, not a cause.
3. **Runs the reverse test** before attributing anything: where did the *same tasks* succeed?
4. **Writes its own SQL through `mcp-clickhouse`** when the fixed tools run out — for example, self-joining first attempts to retries to measure recovery.
5. **Checks farm capacity** so the plan is costed in node-hours.
6. **Produces an ordered plan** with dependencies. Nothing executes: the agent proposes, a person accepts, modifies, or rejects each step.

### The hard part

Two different faults in this dataset produce the **identical out-of-memory error**. Group by error message and they merge into one pile. The agent finds them by cross-tabbing task weight against node memory rather than by reading the message:

| Fault | Mechanism | Fix |
|---|---|---|
| Renderer update on one node group | Scenes using a particular shader need ~2 GB more under the new version, pushing them over the 12 GB limit. The same tasks succeed every time on other groups. | Roll back the renderer on that group |
| Heavy frames in one shot | 42 frames need over 14 GB and fail everywhere, on both renderer versions. | Raise the memory allocation for that shot |

Same error. Opposite causes. Opposite fixes.

The agent also reports that 192 tasks recovered on their own retry, ties 14 texture-loading failures to a tight window around 2 AM, and states that the remaining 48 failures show no pattern — rather than inventing one.

### The plan

Four steps, individually approvable. Two are zero-cost configuration changes; the re-queues are blocked behind them. The agent computes why: re-queueing before the rollback sends roughly 30% of tasks straight back to the bad nodes, and re-queueing before the allocation change fails 100% of them. Accepting the rollback in the UI unblocks the dependent re-queue. The whole plan is about 9 node-hours — roughly 1% of the farm's morning.

## Why the dataset is synthetic

On purpose. The faults were injected by `generate.py`, and `verify.py` independently confirms them — 11 checks, run twice, once against the Parquet files and once against ClickHouse Cloud (11/11 both times). `FAULTS.md` is frozen to the measured values. That means the correct answer is known, and every number in the agent's report can be checked against ground truth. Most agents you can only ask whether they gave an answer; this one you can grade.

## Architecture

```
Browser (Next.js on Vercel)
   │  SSE stream of every tool call, then Findings + Plan with Accept / Modify / Reject
   ▼
ADK agent (Gemini, google-adk) on Cloud Run
   │
   ├── OpenAPI toolset ──► six deterministic tools (TypeScript routes on Vercel)
   │                        └── @clickhouse/client ──► ClickHouse Cloud
   │
   └── MCP toolset ──────► mcp-clickhouse (stdio subprocess) ──► ClickHouse Cloud
```

The design separates **deterministic computation** from **LLM reasoning**. The six tools do the statistics in code and return numbers; Gemini decides which tests to run, interprets the results, and writes free-form SQL through MCP when it needs something the tools don't provide.

### The six tools

| Tool | Purpose |
|---|---|
| `get_failure_summary` | Failure counts and unique failed tasks by job, node group, and error class |
| `classify_error_samples` | Representative error messages per class |
| `test_dimension_concentration` | Binomial test of failure rate vs. base rate along a dimension, Bonferroni-corrected |
| `check_success_elsewhere` | For a set of tasks, where and when did the same tasks succeed |
| `query_similar_past_incidents` | Historical incidents with similar signatures |
| `get_farm_capacity` | Node counts, memory tiers, and available node-hours |

### Stack

- **Google Cloud:** Gemini via `google-adk`, deployed with `adk deploy cloud_run` (Cloud Build source deploy, `adk api_server` with SSE)
- **ClickHouse:** ClickHouse Cloud; runtime access via the official `mcp-clickhouse` MCP server (track requirement) plus `@clickhouse/client` in the tool routes
- **App:** Next.js on Vercel
- **Data:** Python (`generate.py`, `verify.py`, `load.py`), Parquet, pandas/scipy

## Repository layout

```
agent/            ADK agent: instructions.py, agent definition, requirements.txt
app/, lib/        Next.js UI and the six tool routes (lib/stats.ts, lib/clickhouse.ts)
data/             Committed Parquet dataset — clone and you have the same data
db/schema.sql     ClickHouse DDL
scripts/          test-tools.sh and helpers
transcripts/      Saved agent runs
generate.py       Synthetic data generator (seeded, PCG64)
verify.py         Independent fault verifier — Parquet mode and --clickhouse mode
load.py           Loads Parquet into ClickHouse Cloud
openapi.yaml      Tool schema consumed by the ADK OpenAPI toolset
FAULTS.md         Authoritative injected-fault spec (frozen)
SPEC.md           Design spec
verify.md         Verification checklist and results
```

## Running it yourself

### Prerequisites

- Node 20+, Python 3.11+
- A ClickHouse Cloud service (or self-hosted ClickHouse)
- A Gemini API key
- `gcloud` CLI with a billed project, for the Cloud Run deploy

### 1. Data

```bash
pip install -r requirements.txt
python generate.py            # writes data/*.parquet (or skip — they're committed)
python verify.py              # 11 checks against Parquet
python load.py                # loads into ClickHouse using CLICKHOUSE_* env vars
python verify.py --clickhouse # same 11 checks against ClickHouse
```

### 2. Tools and UI

```bash
npm install
cp .env.example .env.local    # set CLICKHOUSE_HOST, CLICKHOUSE_USER, CLICKHOUSE_PASSWORD, CLICKHOUSE_DATABASE
npm run dev
scripts/test-tools.sh         # hits all six routes and checks expected values
```

`CLICKHOUSE_HOST` must include the scheme and port, e.g. `https://<host>.clickhouse.cloud:8443`.

### 3. Agent

```bash
cd agent
pip install -r requirements.txt   # google-adk[mcp], mcp-clickhouse
```

Set `GOOGLE_API_KEY` and the `CLICKHOUSE_*` variables, then run locally with `adk api_server` or deploy:

```bash
adk deploy cloud_run --project <PROJECT> --region <REGION> --service_name render-farm-triage-agent agent \
  -- --timeout=3600 --allow-unauthenticated \
     --set-env-vars GOOGLE_GENAI_USE_ENTERPRISE=0,GOOGLE_API_KEY=...,CLICKHOUSE_HOST=...,CLICKHOUSE_USER=...,CLICKHOUSE_PASSWORD=...,CLICKHOUSE_DATABASE=...
```

`GOOGLE_GENAI_USE_ENTERPRISE=0` keeps the deployed agent on API-key auth, matching the local run. Point the UI at the Cloud Run URL via `AGENT_URL` and redeploy on Vercel.

**Cold starts:** ClickHouse Cloud idles to zero and takes 10–30 s to wake; Cloud Run does the same for the agent. The first request after idle may be slow. 

## Hackathon requirements checklist

- Gemini-powered agent using an accepted Google Cloud SDK (`google-adk`), deployed on Google Cloud (Cloud Run)
- ClickHouse reached at runtime through the official `mcp-clickhouse` MCP server — visible in the live activity log, not just in config
- Hosted, working URL: https://render-farm-triage.vercel.app
- Public repository with an open-source license (see [`LICENSE`](LICENSE))

## License

see (LICENSE) file.
