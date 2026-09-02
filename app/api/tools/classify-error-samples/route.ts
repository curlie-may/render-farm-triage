import { NextRequest } from "next/server";
import { queryRows } from "@/lib/clickhouse";
import { jsonError, jsonOk, roundDeep } from "@/lib/api";
import { BATCH_START, BATCH_END } from "@/lib/constants";

export const dynamic = "force-dynamic";

interface TotalsRow {
  total_rows: number;
  unique_tasks: number;
}

interface SampleRow {
  error_text: string;
  cnt: number;
}

export async function GET(req: NextRequest) {
  try {
    const params = req.nextUrl.searchParams;
    const errorClass = params.get("error_class");
    const limitRaw = params.get("limit");

    if (!errorClass) {
      return jsonError("Missing required parameter: error_class");
    }
    let limit = limitRaw ? parseInt(limitRaw, 10) : 3;
    if (!Number.isFinite(limit) || limit < 1) limit = 3;
    if (limit > 10) limit = 10;

    const [totals] = await queryRows<TotalsRow>(
      `SELECT count() AS total_rows, uniqExact(task_id) AS unique_tasks
       FROM render_task_attempts
       WHERE status = 'failed' AND error_class = {error_class:String}
         AND started_at >= {start:DateTime} AND started_at < {end:DateTime}`,
      { error_class: errorClass, start: BATCH_START, end: BATCH_END }
    );

    if (!totals || totals.total_rows === 0) {
      return jsonOk({
        summary: `No failure rows found with error_class = '${errorClass}' in the batch window.`,
        data: {
          error_class: errorClass,
          total_rows: 0,
          unique_tasks: 0,
          distinct_shot_ids: [],
          distinct_node_groups: [],
          samples: [],
        },
      });
    }

    const [dims] = await queryRows<{ shots: string[]; groups: string[] }>(
      `SELECT groupUniqArray(shot_id) AS shots, groupUniqArray(node_group) AS groups
       FROM render_task_attempts
       WHERE status = 'failed' AND error_class = {error_class:String}
         AND started_at >= {start:DateTime} AND started_at < {end:DateTime}`,
      { error_class: errorClass, start: BATCH_START, end: BATCH_END }
    );

    const samples = await queryRows<SampleRow>(
      `SELECT error_text, count() AS cnt
       FROM render_task_attempts
       WHERE status = 'failed' AND error_class = {error_class:String}
         AND started_at >= {start:DateTime} AND started_at < {end:DateTime}
       GROUP BY error_text
       ORDER BY cnt DESC
       LIMIT {limit:UInt8}`,
      { error_class: errorClass, start: BATCH_START, end: BATCH_END, limit }
    );

    const shots = dims?.shots ?? [];
    const groups = dims?.groups ?? [];

    const summary =
      `error_class '${errorClass}' has ${totals.total_rows} failure rows (${totals.unique_tasks} unique tasks), ` +
      `spanning ${shots.length} shot(s) and node group(s) [${groups.join(", ")}]. ` +
      `${samples.length} representative error_text sample(s) below — read the full text to infer mechanism, ` +
      `not just the class label.`;

    return jsonOk(
      roundDeep({
        summary,
        data: {
          error_class: errorClass,
          total_rows: totals.total_rows,
          unique_tasks: totals.unique_tasks,
          distinct_shot_ids: shots,
          distinct_node_groups: groups,
          samples: samples.map((s) => ({ error_text: s.error_text, count: s.cnt })),
        },
      })
    );
  } catch (err) {
    return jsonError(err instanceof Error ? err.message : String(err));
  }
}
