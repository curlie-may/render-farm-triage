import { NextRequest } from "next/server";
import { queryRows } from "@/lib/clickhouse";
import { jsonError, jsonOk } from "@/lib/api";

export const dynamic = "force-dynamic";

interface IncidentRow {
  incident_id: string;
  occurred_on: string;
  title: string;
  error_class: string;
  symptom_summary: string;
  dimension_signature: string;
  root_cause: string;
  remediation: string;
  outcome: string;
  time_to_resolve_min: number;
}

const STOPWORDS = new Set([
  "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with", "no", "only", "all", "at",
  "is", "are", "was", "were", "cluster", "pattern", "signature", "concentration",
]);

function tokenize(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .split(/[^a-z0-9_]+/)
      .filter((w) => w.length > 1 && !STOPWORDS.has(w))
  );
}

function overlapScore(a: Set<string>, b: Set<string>): number {
  let score = 0;
  for (const w of a) if (b.has(w)) score += 1;
  return score;
}

const MAX_RESULTS = 4;

export async function GET(req: NextRequest) {
  try {
    const params = req.nextUrl.searchParams;
    const errorClass = params.get("error_class");
    const dimensionSignature = params.get("dimension_signature");

    if (!errorClass) {
      return jsonError("Missing required parameter: error_class");
    }

    const incidents = await queryRows<IncidentRow>(
      `SELECT incident_id, occurred_on, title, error_class, symptom_summary,
              dimension_signature, root_cause, remediation, outcome, time_to_resolve_min
       FROM past_incidents`
    );

    if (incidents.length === 0) {
      return jsonOk({
        summary: "No past incidents in the table.",
        data: { error_class: errorClass, dimension_signature: dimensionSignature ?? null, incidents: [] },
      });
    }

    const queryTokens = dimensionSignature ? tokenize(dimensionSignature) : new Set<string>();

    const scored = incidents.map((incident) => {
      const exactClassMatch = incident.error_class === errorClass;
      const incidentTokens = tokenize(`${incident.dimension_signature} ${incident.symptom_summary}`);
      const keywordScore = queryTokens.size ? overlapScore(queryTokens, incidentTokens) : 0;
      const score = (exactClassMatch ? 1000 : 0) + keywordScore;
      return { incident, exactClassMatch, keywordScore, score };
    });

    scored.sort((a, b) => b.score - a.score);
    const top = scored.slice(0, MAX_RESULTS);
    const exactCount = top.filter((s) => s.exactClassMatch).length;

    const summary =
      `${exactCount} of ${top.length} returned incident(s) share error_class = '${errorClass}'; ` +
      `the rest are near-misses ranked by keyword overlap with the dimension signature, included because a ` +
      `different root cause with a similar symptom is exactly the kind of confusion worth ruling out. ` +
      top.map((s) => `${s.incident.incident_id} (${s.incident.occurred_on}): ${s.incident.title}`).join("; ");

    return jsonOk({
      summary,
      data: {
        error_class: errorClass,
        dimension_signature: dimensionSignature ?? null,
        incidents: top.map((s) => ({
          incident_id: s.incident.incident_id,
          occurred_on: s.incident.occurred_on,
          title: s.incident.title,
          error_class: s.incident.error_class,
          matches_error_class: s.exactClassMatch,
          keyword_overlap_score: s.keywordScore,
          symptom_summary: s.incident.symptom_summary,
          dimension_signature: s.incident.dimension_signature,
          root_cause: s.incident.root_cause,
          remediation: s.incident.remediation,
          outcome: s.incident.outcome,
          time_to_resolve_min: s.incident.time_to_resolve_min,
        })),
      },
    });
  } catch (err) {
    return jsonError(err instanceof Error ? err.message : String(err));
  }
}
