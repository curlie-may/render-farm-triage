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

function overlappingWords(a: Set<string>, b: Set<string>): string[] {
  const out: string[] = [];
  for (const w of a) if (b.has(w)) out.push(w);
  return out;
}

const MAX_RESULTS = 4;

/** Fixed thresholds for match_strength, applied to the keyword overlap count.
 * An error-class match alone (no keyword overlap) is "weak" regardless of the
 * class bonus dominating the sort score — sharing only error_class is exactly
 * the case a caller must not mistake for an explanation. */
type MatchStrength = "strong" | "partial" | "weak";

function classifyStrength(exactClassMatch: boolean, keywordCount: number): MatchStrength {
  if (!exactClassMatch) return "weak";
  if (keywordCount >= 3) return "strong";
  if (keywordCount >= 1) return "partial";
  return "weak";
}

function describeBasis(
  exactClassMatch: boolean,
  errorClass: string,
  incidentErrorClass: string,
  matchedWords: string[]
): string {
  if (exactClassMatch && matchedWords.length === 0) {
    return `error class only ('${errorClass}')`;
  }
  if (exactClassMatch && matchedWords.length > 0) {
    return `error class ('${errorClass}') plus keyword overlap on: ${matchedWords.join(", ")}`;
  }
  if (!exactClassMatch && matchedWords.length > 0) {
    return `error class differs ('${incidentErrorClass}' vs '${errorClass}'); keyword overlap only on: ${matchedWords.join(", ")}`;
  }
  return `error class differs ('${incidentErrorClass}' vs '${errorClass}'); no keyword overlap`;
}

/** Fixed, server-generated sentence per incident so the caller never has to
 * infer what a bare strength label means. A weak match must say plainly that
 * it is offered for comparison, not as an explanation. */
function describeMatch(
  strength: MatchStrength,
  exactClassMatch: boolean,
  incidentId: string,
  errorClass: string,
  matchedWords: string[]
): string {
  if (strength === "weak" && exactClassMatch) {
    return (
      `${incidentId} shares only the error_class ('${errorClass}') with this query, with no ` +
      `overlap on the dimension signature — it is offered for comparison, not as an explanation ` +
      `of the current problem. A shared error_class means a similar-looking failure, not a shared cause.`
    );
  }
  if (strength === "weak") {
    return (
      `${incidentId} does not even share the error_class of this query and has ` +
      `${matchedWords.length ? `only incidental keyword overlap (${matchedWords.join(", ")})` : "no meaningful overlap"} — ` +
      `treat it as unrelated background, not a comparison.`
    );
  }
  if (strength === "partial") {
    return (
      `${incidentId} shares error_class ('${errorClass}') and partially overlaps the dimension ` +
      `signature on ${matchedWords.length} keyword(s) (${matchedWords.join(", ")}) — worth reading as a ` +
      `candidate precedent, but confirm its root_cause against this batch's own data before relying on it.`
    );
  }
  return (
    `${incidentId} shares error_class ('${errorClass}') and closely overlaps the dimension signature ` +
    `on ${matchedWords.length} keywords (${matchedWords.join(", ")}) — a plausible precedent, still confirm ` +
    `its root_cause against this batch's own data rather than assuming it applies.`
  );
}

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
      const matchedWords = queryTokens.size ? overlappingWords(queryTokens, incidentTokens) : [];
      const score = (exactClassMatch ? 1000 : 0) + matchedWords.length;
      const strength = classifyStrength(exactClassMatch, matchedWords.length);
      return { incident, exactClassMatch, matchedWords, score, strength };
    });

    scored.sort((a, b) => b.score - a.score);
    const top = scored.slice(0, MAX_RESULTS);
    const exactCount = top.filter((s) => s.exactClassMatch).length;
    const weakCount = top.filter((s) => s.strength === "weak").length;

    const summary =
      `${exactCount} of ${top.length} returned incident(s) share error_class = '${errorClass}'; ` +
      `the rest are near-misses ranked by keyword overlap with the dimension signature, included because a ` +
      `different root cause with a similar symptom is exactly the kind of confusion worth ruling out. ` +
      `${weakCount} of ${top.length} are weak matches — comparison only, not an explanation of the current ` +
      `problem. ` +
      top.map((s) => `${s.incident.incident_id} (${s.incident.occurred_on}, ${s.strength} match)`).join("; ");

    return jsonOk({
      summary,
      data: {
        error_class: errorClass,
        dimension_signature: dimensionSignature ?? null,
        incidents: top.map((s) => ({
          incident_id: s.incident.incident_id,
          occurred_on: s.incident.occurred_on,
          error_class: s.incident.error_class,
          matches_error_class: s.exactClassMatch,
          keyword_overlap_score: s.matchedWords.length,
          match_score: s.score,
          match_basis: describeBasis(s.exactClassMatch, errorClass, s.incident.error_class, s.matchedWords),
          match_strength: s.strength,
          match_note: describeMatch(s.strength, s.exactClassMatch, s.incident.incident_id, errorClass, s.matchedWords),
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
