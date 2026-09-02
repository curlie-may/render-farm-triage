import { queryRows } from "@/lib/clickhouse";
import { jsonError, jsonOk, roundDeep } from "@/lib/api";
import { BATCH_START, BATCH_END } from "@/lib/constants";

export const dynamic = "force-dynamic";

interface TotalsRow {
  total_attempts: number;
  total_failure_rows: number;
  unique_failed_tasks: number;
}

interface ErrorClassRow {
  error_class: string | null;
  rows: number;
  unique_tasks: number;
}

export async function GET() {
  try {
    const [totals] = await queryRows<TotalsRow>(
      `SELECT
         count() AS total_attempts,
         countIf(status = 'failed') AS total_failure_rows,
         uniqExactIf(task_id, status = 'failed') AS unique_failed_tasks
       FROM render_task_attempts
       WHERE started_at >= {start:DateTime} AND started_at < {end:DateTime}`,
      { start: BATCH_START, end: BATCH_END }
    );

    if (!totals) {
      return jsonError("No rows returned for the batch window.");
    }

    const byErrorClass = await queryRows<ErrorClassRow>(
      `SELECT
         error_class,
         count() AS rows,
         uniqExact(task_id) AS unique_tasks
       FROM render_task_attempts
       WHERE status = 'failed'
         AND started_at >= {start:DateTime} AND started_at < {end:DateTime}
       GROUP BY error_class
       ORDER BY rows DESC`,
      { start: BATCH_START, end: BATCH_END }
    );

    const breakdown = byErrorClass.map((r) => ({
      error_class: r.error_class,
      failure_rows: r.rows,
      unique_tasks: r.unique_tasks,
    }));

    const breakdownStr = breakdown
      .map((b) => `${b.error_class}: ${b.failure_rows} rows / ${b.unique_tasks} unique tasks`)
      .join("; ");

    const summary =
      `Batch window ${BATCH_START} to ${BATCH_END}: ${totals.total_attempts} total attempts, ` +
      `${totals.total_failure_rows} failure rows representing ${totals.unique_failed_tasks} unique ` +
      `failed tasks after deduping retries on task_id. By error_class: ${breakdownStr}. ` +
      `Always report the unique-task count, not the row count — retries inflate rows.`;

    return jsonOk(
      roundDeep({
        summary,
        data: {
          window: { start: BATCH_START, end: BATCH_END },
          total_attempts: totals.total_attempts,
          total_failure_rows: totals.total_failure_rows,
          unique_failed_tasks: totals.unique_failed_tasks,
          by_error_class: breakdown,
        },
      })
    );
  } catch (err) {
    return jsonError(err instanceof Error ? err.message : String(err));
  }
}
