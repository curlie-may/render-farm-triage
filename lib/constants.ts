// Batch window and shared constants for the render farm triage tool layer.
// Values transcribed from FAULTS.md / SPEC.md — do not derive these from the data.

export const BATCH_START = "2026-09-08 22:00:00";
// The dispatch window is nominally 22:00-06:00, but retries (2-8 min delay
// plus up to a 14-min render) and queue overrun push some real attempts'
// started_at past 06:00 — the latest is 07:08:49. 08:00 gives headroom to
// include every attempt belonging to this batch (verified: 9996 rows / 396
// failure rows / 294 unique failed tasks, matching FAULTS.md) without
// stretching into a different batch.
export const BATCH_END = "2026-09-09 08:00:00";
export const MAINTENANCE_START = "2026-09-08 23:00:00";

export const SIG_LEVEL = 0.05;
export const STRONG_SIG_LEVEL = 0.001;

export const CONCENTRATION_DIMENSIONS = [
  "node_group",
  "node_id",
  "shot_id",
  "job_id",
  "renderer_version",
  "submitted_by",
  "uses_hair_shader",
  "error_class",
  "time_bucket",
] as const;

export type ConcentrationDimension = (typeof CONCENTRATION_DIMENSIONS)[number];

export const TIME_BUCKET_MINUTES = 10;

export const MAX_ROWS = 50;

/** Maps a dimension name to the SQL expression that produces it. */
export function dimensionSqlExpr(dimension: ConcentrationDimension): string {
  switch (dimension) {
    case "time_bucket":
      return `toStartOfInterval(started_at, INTERVAL ${TIME_BUCKET_MINUTES} MINUTE)`;
    case "uses_hair_shader":
      return "uses_hair_shader";
    default:
      return dimension;
  }
}
