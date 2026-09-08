// Parses the agent's final answer into prose + a machine-readable plan.
//
// The agent (agent/instructions.py, "## Machine-readable plan") is instructed
// to end its answer with exactly one fenced ```json block restating the plan
// and capacity picture. Everything before that block is prose meant to be
// rendered as written. The block can be missing or malformed — the model is
// not a parser — so every step here is defensive, and the caller always gets
// something to render.

export interface PlanStep {
  id: string;
  title: string;
  action: string;
  reason: string;
  depends_on: string | null;
  affected_tasks: number;
  cost_node_hours: number;
}

export interface ResolvedWork {
  task_count: number;
  summary: string;
}

export interface CapacityPicture {
  available_node_hours: number;
  required_node_hours: number;
  fraction_of_capacity: number;
  note: string;
}

export interface AgentPlan {
  resolved_work: ResolvedWork;
  capacity: CapacityPicture;
  steps: PlanStep[];
}

export interface ParsedFindings {
  /** The full answer with the trailing JSON fence (if any) removed. */
  prose: string;
  /** Present only if a fenced json block was found AND parsed AND matched
   * the expected shape closely enough to render. */
  plan: AgentPlan | null;
  /** Set when a fence was found but couldn't be parsed/validated, so the
   * caller can say specifically that the structured view is unavailable
   * rather than silently showing nothing. */
  planError: string | null;
}

const FENCE_RE = /```json\s*([\s\S]*?)```/g;

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function asNumber(v: unknown, fallback = 0): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

/** Validates just enough structure to render safely — extra/missing fields
 * are coerced with sane fallbacks rather than rejected, since a plan that's
 * 90% right is far more useful to show than a hard failure. Only a
 * completely wrong shape (no steps array at all) is treated as unparseable. */
function coercePlan(raw: unknown): AgentPlan | null {
  if (!isPlainObject(raw)) return null;
  const rawSteps = raw.steps;
  if (!Array.isArray(rawSteps)) return null;

  const steps: PlanStep[] = rawSteps
    .filter(isPlainObject)
    .map((s, i) => ({
      id: asString(s.id, `step-${i + 1}`),
      title: asString(s.title, `Step ${i + 1}`),
      action: asString(s.action),
      reason: asString(s.reason),
      depends_on: typeof s.depends_on === "string" ? s.depends_on : null,
      affected_tasks: asNumber(s.affected_tasks),
      cost_node_hours: asNumber(s.cost_node_hours),
    }));

  const rw = isPlainObject(raw.resolved_work) ? raw.resolved_work : {};
  const cap = isPlainObject(raw.capacity) ? raw.capacity : {};

  return {
    resolved_work: {
      task_count: asNumber(rw.task_count),
      summary: asString(rw.summary),
    },
    capacity: {
      available_node_hours: asNumber(cap.available_node_hours),
      required_node_hours: asNumber(cap.required_node_hours),
      fraction_of_capacity: asNumber(cap.fraction_of_capacity),
      note: asString(cap.note),
    },
    steps,
  };
}

/** The agent tends to introduce the trailing JSON block with its own heading
 * (echoing "## Machine-readable plan" from the instructions) or a horizontal
 * rule, since from its side that's just another section of one continuous
 * answer. Once the fence itself is cut out for the Plan panel, that heading
 * is left dangling with nothing under it. Strip trailing heading-only and
 * rule-only lines so the prose ends cleanly on real content. */
function stripTrailingSectionNoise(text: string): string {
  let result = text;
  const trailingNoise = /(^|\n)\s*(#{1,6}[^\n]*|-{3,}|\*{3,}|_{3,})\s*$/;
  while (trailingNoise.test(result)) {
    result = result.replace(trailingNoise, "").trimEnd();
  }
  return result;
}

export function parseFindings(fullText: string): ParsedFindings {
  const matches = [...fullText.matchAll(FENCE_RE)];
  if (matches.length === 0) {
    return { prose: fullText.trim(), plan: null, planError: null };
  }

  // The instructions ask for exactly one block, at the end. If the model
  // emits more than one anyway, the last one is the one meant to be final.
  const last = matches[matches.length - 1];
  const prose = stripTrailingSectionNoise(fullText.slice(0, last.index).trim());
  const jsonText = last[1].trim();

  try {
    const raw = JSON.parse(jsonText);
    const plan = coercePlan(raw);
    if (!plan) {
      return {
        prose,
        plan: null,
        planError: "The plan block didn't match the expected shape.",
      };
    }
    return { prose, plan, planError: null };
  } catch (err) {
    return {
      prose,
      plan: null,
      planError: `The plan block wasn't valid JSON (${err instanceof Error ? err.message : String(err)}).`,
    };
  }
}
