import { NextRequest } from "next/server";
import { queryRows } from "@/lib/clickhouse";
import { jsonError, jsonOk, roundDeep } from "@/lib/api";
import {
  BATCH_START,
  BATCH_END,
  CONCENTRATION_DIMENSIONS,
  ConcentrationDimension,
  dimensionSqlExpr,
  MAX_ROWS,
  SIG_LEVEL,
} from "@/lib/constants";
import { bonferroni, twoSidedBinomTest, verdictForValue } from "@/lib/stats";

export const dynamic = "force-dynamic";

interface PopRow {
  value: string | number | boolean | null;
  attempts: number;
}

interface SubsetRow {
  value: string | number | boolean | null;
  observed_failures: number;
}

interface CountRow {
  n: number;
}

interface SpanRow {
  span_start: string;
  span_end: string;
  failures_in_span: number;
  span_seconds: number;
  window_seconds: number;
}

/** Fraction of the batch window under which a failure span counts as
 * "tightly clustered" enough to state a boundary-independent window,
 * alongside the (boundary-dependent) fixed-bucket breakdown. */
const CONTIGUOUS_WINDOW_MAX_SHARE_OF_BATCH = 0.05;

function parseList(param: string | null): string[] | null {
  if (!param) return null;
  const items = param
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  return items.length ? items : null;
}

export async function GET(req: NextRequest) {
  try {
    const params = req.nextUrl.searchParams;
    const dimensionParam = params.get("dimension");
    const start = params.get("start") ?? BATCH_START;
    const end = params.get("end") ?? BATCH_END;
    const includeClasses = parseList(params.get("error_class"));
    const excludeClasses = parseList(params.get("exclude_error_class"));

    if (!dimensionParam) {
      return jsonError(
        `Missing required parameter: dimension. Supported: ${CONCENTRATION_DIMENSIONS.join(", ")}`
      );
    }
    if (!(CONCENTRATION_DIMENSIONS as readonly string[]).includes(dimensionParam)) {
      return jsonError(
        `Unsupported dimension '${dimensionParam}'. Supported: ${CONCENTRATION_DIMENSIONS.join(", ")}`
      );
    }
    const dimension = dimensionParam as ConcentrationDimension;
    const dimExpr = dimensionSqlExpr(dimension);

    let subsetWhere = "status = 'failed'";
    const subsetParams: Record<string, unknown> = { start, end };
    if (includeClasses) {
      subsetWhere += " AND error_class IN {include_classes:Array(String)}";
      subsetParams.include_classes = includeClasses;
    }
    if (excludeClasses) {
      subsetWhere += " AND error_class NOT IN {exclude_classes:Array(String)}";
      subsetParams.exclude_classes = excludeClasses;
    }

    // Population: every distinct non-null value of the dimension across ALL
    // attempts in the window — this is the base rate, not the failure rate.
    const popRows = await queryRows<PopRow>(
      `SELECT ${dimExpr} AS value, count() AS attempts
       FROM render_task_attempts
       WHERE started_at >= {start:DateTime} AND started_at < {end:DateTime}
       GROUP BY value
       HAVING value IS NOT NULL`,
      { start, end }
    );

    const [{ n: totalAttempts }] = await queryRows<CountRow>(
      `SELECT count() AS n FROM render_task_attempts
       WHERE started_at >= {start:DateTime} AND started_at < {end:DateTime}`,
      { start, end }
    );

    const subsetRows = await queryRows<SubsetRow>(
      `SELECT ${dimExpr} AS value, count() AS observed_failures
       FROM render_task_attempts
       WHERE ${subsetWhere}
         AND started_at >= {start:DateTime} AND started_at < {end:DateTime}
       GROUP BY value`,
      subsetParams
    );

    const [{ n: totalFailures }] = await queryRows<CountRow>(
      `SELECT count() AS n FROM render_task_attempts
       WHERE ${subsetWhere}
         AND started_at >= {start:DateTime} AND started_at < {end:DateTime}`,
      subsetParams
    );

    if (popRows.length === 0 || totalAttempts === 0) {
      return jsonError(`No attempts found in window ${start} to ${end}.`);
    }

    // Boundary-independent companion to the time_bucket breakdown: a fixed
    // bucket edge (e.g. :10) can split one contiguous event across two
    // buckets, understating its concentration for a reason that has nothing
    // to do with the underlying fault (see the Fault C 02:08:24-02:18:36
    // stall, which straddles the 02:10 edge). This finds the actual span of
    // the failure subset and how many attempts of any status fell inside it.
    let contiguousWindow: {
      start: string;
      end: string;
      span_minutes: number;
      failures_in_span: number;
      total_failures: number;
      attempts_in_span: number;
      share_of_span: number;
    } | null = null;
    let tightlyClustered = false;

    if (dimension === "time_bucket" && totalFailures > 0) {
      const [span] = await queryRows<SpanRow>(
        `SELECT
           min(started_at) AS span_start,
           max(started_at) AS span_end,
           count() AS failures_in_span,
           dateDiff('second', min(started_at), max(started_at)) AS span_seconds,
           dateDiff('second', toDateTime({start:DateTime}), toDateTime({end:DateTime})) AS window_seconds
         FROM render_task_attempts
         WHERE ${subsetWhere}
           AND started_at >= {start:DateTime} AND started_at < {end:DateTime}`,
        subsetParams
      );

      const [{ n: attemptsInSpan }] = await queryRows<CountRow>(
        `SELECT count() AS n FROM render_task_attempts
         WHERE started_at >= {span_start:DateTime} AND started_at <= {span_end:DateTime}`,
        { span_start: span.span_start, span_end: span.span_end }
      );

      const spanMinutes = Math.ceil(span.span_seconds / 60);
      const shareOfSpan = attemptsInSpan > 0 ? span.failures_in_span / attemptsInSpan : 0;

      contiguousWindow = {
        start: span.span_start,
        end: span.span_end,
        span_minutes: spanMinutes,
        failures_in_span: span.failures_in_span,
        total_failures: totalFailures,
        attempts_in_span: attemptsInSpan,
        share_of_span: shareOfSpan,
      };

      tightlyClustered =
        span.failures_in_span === totalFailures &&
        span.span_seconds < CONTIGUOUS_WINDOW_MAX_SHARE_OF_BATCH * span.window_seconds;
    }

    const k = popRows.length; // number of distinct dimension values tested, matching FAULTS.md's Bonferroni convention
    const subsetMap = new Map<string, number>();
    for (const r of subsetRows) {
      subsetMap.set(String(r.value), r.observed_failures);
    }

    const values = popRows.map((r) => {
      const key = String(r.value);
      const attempts = r.attempts;
      const observedFailures = subsetMap.get(key) ?? 0;
      const expectedShare = attempts / totalAttempts;
      const observedShare = totalFailures > 0 ? observedFailures / totalFailures : 0;
      const pValue = totalFailures > 0 ? twoSidedBinomTest(observedFailures, totalFailures, expectedShare) : 1;
      const pCorrected = bonferroni(pValue, k);
      const verdict = verdictForValue(pCorrected, observedShare, expectedShare);
      return {
        value: r.value,
        attempts,
        expected_share: expectedShare,
        observed_failures: observedFailures,
        observed_share: observedShare,
        p_value: pValue,
        p_corrected: pCorrected,
        verdict,
      };
    });

    values.sort((a, b) => b.observed_failures - a.observed_failures || b.attempts - a.attempts);
    const topValues = values.slice(0, MAX_ROWS);

    const concentrating = values.filter(
      (v) => v.p_corrected < SIG_LEVEL && v.observed_share > v.expected_share
    );
    concentrating.sort((a, b) => a.p_corrected - b.p_corrected);

    const dimensionVerdictStr =
      concentrating.length === 0
        ? "no value in this dimension concentrates above base rate"
        : `${concentrating.length} value(s) concentrate above base rate, strongest: ` +
          concentrating
            .slice(0, 3)
            .map(
              (v) =>
                `${v.value} (${(v.observed_share * 100).toFixed(1)}% of failures vs ${(v.expected_share * 100).toFixed(1)}% of batch, p_corrected=${v.p_corrected.toExponential(3)}, ${v.verdict})`
            )
            .join("; ");

    const filterDesc = includeClasses
      ? ` restricted to error_class in [${includeClasses.join(", ")}]`
      : excludeClasses
        ? ` excluding error_class in [${excludeClasses.join(", ")}]`
        : "";

    const clusterSentence =
      contiguousWindow && tightlyClustered
        ? ` ${contiguousWindow.failures_in_span} of ${contiguousWindow.total_failures} failures fall within a ` +
          `${contiguousWindow.span_minutes}-minute span (${contiguousWindow.start} to ${contiguousWindow.end}), ` +
          `against ${contiguousWindow.attempts_in_span} attempts in that span.`
        : "";

    const summary =
      `Concentration test on '${dimension}'${filterDesc}: ${totalFailures} failure rows tested against ` +
      `${totalAttempts} total attempts, ${k} distinct values, Bonferroni-corrected across ${k} hypotheses. ` +
      dimensionVerdictStr +
      "." +
      clusterSentence;

    return jsonOk(
      roundDeep({
        summary,
        data: {
          dimension,
          window: { start, end },
          error_class_filter: includeClasses ?? null,
          exclude_error_class_filter: excludeClasses ?? null,
          total_attempts: totalAttempts,
          total_failures: totalFailures,
          n_values_tested: k,
          verdict: dimensionVerdictStr,
          values: topValues,
          rows_truncated: values.length > MAX_ROWS,
          ...(dimension === "time_bucket" ? { contiguous_window: contiguousWindow } : {}),
        },
      })
    );
  } catch (err) {
    return jsonError(err instanceof Error ? err.message : String(err));
  }
}
