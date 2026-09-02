import { NextRequest } from "next/server";
import { queryRows } from "@/lib/clickhouse";
import { jsonError, jsonOk, roundDeep } from "@/lib/api";
import { BATCH_START, BATCH_END, MAINTENANCE_START } from "@/lib/constants";

export const dynamic = "force-dynamic";

// This tool is descriptive, not a hypothesis test: it returns a contingency
// breakdown (attempts / successes / failures / failure_rate per bucket) and a
// summary sentence picked by a fixed ratio threshold, never a p-value or a
// baseline-comparison significance test. Concentration testing across the
// whole dataset is test_dimension_concentration's job; this tool answers a
// narrower, descriptive question about one specific value: "does failure
// concentrate in one bucket of some OTHER dimension, or is it spread evenly?"

const ALLOWED_DIMENSIONS = [
  "node_group",
  "node_id",
  "shot_id",
  "job_id",
  "renderer_version",
  "submitted_by",
] as const;

const ALLOWED_SPLIT_BY = ["node_group", "renderer_version", "uses_hair_shader", "before_after_2300"] as const;
type SplitBy = (typeof ALLOWED_SPLIT_BY)[number];

// Highest bucket's failure rate must be at least this many times the lowest
// NON-ZERO bucket's failure rate to call the split "uneven".
const UNEVEN_RATIO_THRESHOLD = 5;

// Below this absolute rate, even the "worst" bucket isn't failing enough to
// mean anything — a single incidental failure landing in an otherwise-clean
// bucket (e.g. 1 failure in 55 attempts, 0 in the other two buckets) would
// otherwise read as an "infinite" ratio against a zero baseline and get
// reported as a meaningful split. It isn't one; it's background noise. Set
// comfortably above the batch's overall failure rate (~4%).
const MIN_MEANINGFUL_RATE = 0.05;

interface BreakdownRow {
  bucket: string | number | boolean;
  status: string;
  cnt: number;
}

function splitBySqlExpr(splitBy: SplitBy): string {
  switch (splitBy) {
    case "before_after_2300":
      return `if(started_at < {maint:DateTime}, 'before_23:00', 'after_23:00')`;
    case "uses_hair_shader":
      return "uses_hair_shader";
    default:
      return splitBy;
  }
}

export async function GET(req: NextRequest) {
  try {
    const params = req.nextUrl.searchParams;
    const dimension = params.get("dimension");
    const value = params.get("value");
    const splitByParam = params.get("split_by");
    const errorClass = params.get("error_class");

    if (!dimension || !value || !splitByParam) {
      return jsonError("Missing required parameters: dimension, value, split_by");
    }
    if (!(ALLOWED_DIMENSIONS as readonly string[]).includes(dimension)) {
      return jsonError(`Unsupported dimension '${dimension}'. Supported: ${ALLOWED_DIMENSIONS.join(", ")}`);
    }
    if (!(ALLOWED_SPLIT_BY as readonly string[]).includes(splitByParam)) {
      return jsonError(`Unsupported split_by '${splitByParam}'. Supported: ${ALLOWED_SPLIT_BY.join(", ")}`);
    }
    const splitBy = splitByParam as SplitBy;
    const splitExpr = splitBySqlExpr(splitBy);

    let failureFilter = "status = 'failed'";
    const queryParams: Record<string, unknown> = {
      value,
      start: BATCH_START,
      end: BATCH_END,
      maint: MAINTENANCE_START,
    };
    if (errorClass) {
      failureFilter += " AND error_class = {error_class:String}";
      queryParams.error_class = errorClass;
    }

    const rows = await queryRows<BreakdownRow>(
      `SELECT
         ${splitExpr} AS bucket,
         status,
         count() AS cnt
       FROM render_task_attempts
       WHERE ${dimension} = {value:String}
         AND started_at >= {start:DateTime} AND started_at < {end:DateTime}
         AND (status = 'success' OR (${failureFilter}))
       GROUP BY bucket, status
       ORDER BY bucket, status`,
      queryParams
    );

    if (rows.length === 0) {
      return jsonOk({
        summary: `No attempts found where ${dimension} = '${value}' in the batch window.`,
        data: { dimension, value, split_by: splitBy, error_class_filter: errorClass ?? null, buckets: [] },
      });
    }

    const byBucket = new Map<string, { bucket: string | number | boolean; successes: number; failures: number }>();
    for (const r of rows) {
      const key = String(r.bucket);
      const b = byBucket.get(key) ?? { bucket: r.bucket, successes: 0, failures: 0 };
      if (r.status === "success") b.successes += r.cnt;
      else b.failures += r.cnt;
      byBucket.set(key, b);
    }

    const buckets = Array.from(byBucket.values())
      .map((b) => {
        const attempts = b.successes + b.failures;
        return {
          bucket: b.bucket,
          attempts,
          successes: b.successes,
          failures: b.failures,
          failure_rate: attempts > 0 ? b.failures / attempts : 0,
        };
      })
      .sort((a, b) => b.failure_rate - a.failure_rate);

    const fmtBucket = (b: (typeof buckets)[number]) => `${b.bucket} (${(b.failure_rate * 100).toFixed(1)}%)`;
    const highest = buckets[0];

    let summary: string;
    if (buckets.length <= 1) {
      summary = `${dimension} = '${value}' only has one ${splitBy} bucket in this window (${fmtBucket(highest)}); nothing to compare it against.`;
    } else if (highest.failure_rate === 0) {
      summary =
        `${dimension} = '${value}' has zero failures in every ${splitBy} bucket ` +
        `(${buckets.map((b) => `${b.bucket}: ${b.attempts} attempts`).join(", ")}). Nothing to explain here.`;
    } else if (highest.failure_rate < MIN_MEANINGFUL_RATE) {
      const rateStr = buckets.map(fmtBucket).join(", ");
      summary =
        `${dimension} = '${value}' shows no ${splitBy} bucket with a meaningful failure rate (${rateStr}) — ` +
        `whatever failures exist are consistent with background noise, not a real split.`;
    } else {
      const nonZero = buckets.filter((b) => b.failure_rate > 0);
      const lowestNonZero = nonZero[nonZero.length - 1];
      const ratio = lowestNonZero.failure_rate > 0 ? highest.failure_rate / lowestNonZero.failure_rate : Infinity;
      const uneven = ratio >= UNEVEN_RATIO_THRESHOLD;

      if (uneven) {
        const highBuckets = buckets.filter((b) => b.failure_rate * UNEVEN_RATIO_THRESHOLD >= highest.failure_rate);
        const lowBuckets = buckets.filter((b) => !highBuckets.includes(b));
        const highStr = highBuckets.map((b) => b.bucket).join(", ");
        const lowStr = lowBuckets.map(fmtBucket).join(", ");
        summary =
          `${dimension} = '${value}' fails in ${splitBy} = ${highStr} (${highBuckets.map((b) => `${(b.failure_rate * 100).toFixed(1)}%`).join(", ")}) ` +
          `and succeeds in ${splitBy} = ${lowStr}.`;
      } else {
        const rateStr = buckets.map(fmtBucket).join(", ");
        summary =
          `${dimension} = '${value}' fails at a similar rate across every ${splitBy} bucket (${rateStr}): ` +
          `it does not escape by changing ${splitBy}.`;
      }
    }

    return jsonOk(
      roundDeep({
        summary,
        data: {
          dimension,
          value,
          split_by: splitBy,
          error_class_filter: errorClass ?? null,
          window: { start: BATCH_START, end: BATCH_END, maintenance_start: MAINTENANCE_START },
          buckets,
          uneven_ratio_threshold: UNEVEN_RATIO_THRESHOLD,
          min_meaningful_rate: MIN_MEANINGFUL_RATE,
        },
      })
    );
  } catch (err) {
    return jsonError(err instanceof Error ? err.message : String(err));
  }
}
