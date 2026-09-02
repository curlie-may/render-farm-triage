import { NextRequest } from "next/server";
import { queryRows } from "@/lib/clickhouse";
import { jsonError, jsonOk, roundDeep } from "@/lib/api";
import { BATCH_START, BATCH_END } from "@/lib/constants";

export const dynamic = "force-dynamic";

interface GroupRow {
  node_group: string;
  node_count: number;
  online_count: number;
  mem_gb: number;
  cpu_cores: number;
  renderer_version: string;
}

interface DurationRow {
  mean_duration_sec: number;
  n_tasks: number;
}

export async function GET(req: NextRequest) {
  try {
    const params = req.nextUrl.searchParams;
    const windowHoursRaw = params.get("window_hours");
    let windowHours = windowHoursRaw ? parseFloat(windowHoursRaw) : 8;
    if (!Number.isFinite(windowHours) || windowHours <= 0) windowHours = 8;

    // farm_nodes carries CURRENT fleet state, not per-attempt history — this
    // can legitimately differ from renderer_version seen on old attempt rows
    // if a rollback has since happened.
    const groups = await queryRows<GroupRow>(
      `SELECT
         node_group,
         count() AS node_count,
         countIf(online) AS online_count,
         any(mem_gb) AS mem_gb,
         any(cpu_cores) AS cpu_cores,
         anyIf(renderer_version, online) AS renderer_version
       FROM farm_nodes
       GROUP BY node_group
       ORDER BY node_group`
    );

    if (groups.length === 0) {
      return jsonError("No rows in farm_nodes.");
    }

    const [duration] = await queryRows<DurationRow>(
      `SELECT avg(duration_sec) AS mean_duration_sec, count() AS n_tasks
       FROM render_task_attempts
       WHERE started_at >= {start:DateTime} AND started_at < {end:DateTime}`,
      { start: BATCH_START, end: BATCH_END }
    );

    const totalNodes = groups.reduce((s, g) => s + g.node_count, 0);
    const totalOnline = groups.reduce((s, g) => s + g.online_count, 0);
    const availableNodeHours = totalOnline * windowHours;
    const meanDurationSec = duration?.mean_duration_sec ?? 0;
    const meanDurationMin = meanDurationSec / 60;

    const groupSummaries = groups
      .map((g) => `${g.node_group}: ${g.online_count}/${g.node_count} online, ${g.mem_gb} GB/node, Arnold ${g.renderer_version}`)
      .join("; ");

    const summary =
      `Fleet: ${totalOnline} of ${totalNodes} nodes online across ${groups.length} groups (${groupSummaries}). ` +
      `Over a ${windowHours}h window that's ${availableNodeHours} available node-hours. ` +
      `Mean task duration in the batch is ${meanDurationMin.toFixed(2)} min (${meanDurationSec.toFixed(0)}s), ` +
      `so a re-queue of N tasks costs roughly N * ${meanDurationMin.toFixed(2)} task-minutes of farm time before parallelism.`;

    return jsonOk(
      roundDeep({
        summary,
        data: {
          window_hours: windowHours,
          groups: groups.map((g) => ({
            node_group: g.node_group,
            node_count: g.node_count,
            online_count: g.online_count,
            mem_gb: g.mem_gb,
            cpu_cores: g.cpu_cores,
            renderer_version: g.renderer_version,
          })),
          total_nodes: totalNodes,
          total_online_nodes: totalOnline,
          available_node_hours: availableNodeHours,
          mean_task_duration_sec: meanDurationSec,
          mean_task_duration_min: meanDurationMin,
        },
      })
    );
  } catch (err) {
    return jsonError(err instanceof Error ? err.message : String(err));
  }
}
