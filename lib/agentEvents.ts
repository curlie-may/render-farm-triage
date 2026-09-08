// Types and parsing for the ADK api_server's /run_sse event stream.
//
// Shape confirmed directly against the installed google-adk version by
// constructing sample google.adk.events.event.Event objects and inspecting
// event.model_dump_json(exclude_none=True, by_alias=True) — the exact call
// api_server.py makes before writing each `data: <json>\n\n` line. Do not
// change these field names without re-checking that call; camelCase aliases
// (functionCall, functionResponse) come from google-genai's Pydantic models,
// not from anything in this repo.

export interface AgentFunctionCall {
  id?: string;
  name: string;
  args?: Record<string, unknown>;
}

export interface AgentFunctionResponse {
  id?: string;
  name: string;
  response?: unknown;
}

export interface AgentEventPart {
  text?: string;
  functionCall?: AgentFunctionCall;
  functionResponse?: AgentFunctionResponse;
}

export interface AgentEvent {
  author?: string;
  content?: {
    role?: string;
    parts?: AgentEventPart[];
  };
  id?: string;
  timestamp?: number;
}

/** The distinct error payload api_server.py emits instead of an Event when
 * the run itself fails (`{"error": "...", "error_details": {...}}`), rather
 * than a normal Event with no error. Events always carry an `author`. */
export interface AgentStreamError {
  error: string;
  error_details?: unknown;
}

export function isStreamError(
  data: AgentEvent | AgentStreamError
): data is AgentStreamError {
  return "error" in data && !("author" in data);
}

/** One line of activity for the live feed / downloadable log. Mirrors what a
 * single Event can carry, but flattened to one kind per item since the feed
 * renders top to bottom in arrival order.
 *
 * `key` is unique per item for React's sake. `callId` is the id ADK's
 * functionCall/functionResponse pair shares — it correlates a call with its
 * response, but is NOT globally unique across a whole run: a live run
 * against the deployed agent showed the same id reused across unrelated
 * calls, which broke both React's keys and call/response matching when they
 * shared one field. Keep them separate. */
export type ActivityItem =
  | {
      kind: "tool_call";
      key: string;
      callId: string;
      author: string;
      name: string;
      args: Record<string, unknown>;
      timestamp: number;
    }
  | {
      kind: "tool_response";
      key: string;
      callId: string;
      author: string;
      name: string;
      response: unknown;
      timestamp: number;
    }
  | {
      kind: "text";
      key: string;
      author: string;
      text: string;
      timestamp: number;
    }
  | {
      kind: "error";
      key: string;
      message: string;
      timestamp: number;
    };

let _keyCounter = 0;
function nextKey(prefix: string): string {
  _keyCounter += 1;
  return `${prefix}-${_keyCounter}`;
}

/** Splits one Event into activity items, in the order its parts appear. A
 * single event can carry more than one part (rare, but the schema allows
 * it), so this returns an array rather than assuming exactly one. */
export function eventToActivityItems(event: AgentEvent): ActivityItem[] {
  const author = event.author ?? "agent";
  const timestamp = event.timestamp ?? Date.now() / 1000;
  const items: ActivityItem[] = [];
  for (const part of event.content?.parts ?? []) {
    if (part.functionCall) {
      items.push({
        kind: "tool_call",
        key: nextKey("call"),
        callId: part.functionCall.id ?? "",
        author,
        name: part.functionCall.name,
        args: part.functionCall.args ?? {},
        timestamp,
      });
    }
    if (part.functionResponse) {
      items.push({
        kind: "tool_response",
        key: nextKey("response"),
        callId: part.functionResponse.id ?? "",
        author,
        name: part.functionResponse.name,
        response: part.functionResponse.response,
        timestamp,
      });
    }
    if (part.text) {
      items.push({
        kind: "text",
        key: nextKey("text"),
        author,
        text: part.text,
        timestamp,
      });
    }
  }
  return items;
}

/** Best-effort one-line summary of a tool's response, for the live feed.
 * Fixed OpenAPI tools always carry a `summary` string — prefer that. MCP
 * tools (list_databases, list_tables, run_query) wrap their payload as
 * `{content: [{type: "text", text: "<json string>"}], isError}`. */
export function summarizeToolResponse(response: unknown): {
  text: string;
  isError: boolean;
} {
  if (response === null || response === undefined) {
    return { text: "(no response)", isError: false };
  }
  if (typeof response !== "object") {
    return { text: String(response), isError: false };
  }
  const obj = response as Record<string, unknown>;

  if (typeof obj.error === "string") {
    return { text: obj.error, isError: true };
  }
  if (typeof obj.summary === "string") {
    return { text: obj.summary, isError: false };
  }

  // MCP tool shape.
  if (Array.isArray(obj.content)) {
    const isError = obj.isError === true;
    const firstText = obj.content.find(
      (c): c is { type: string; text: string } =>
        typeof c === "object" && c !== null && typeof (c as { text?: unknown }).text === "string"
    );
    if (firstText) {
      const raw = firstText.text;
      try {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object" && Array.isArray((parsed as { rows?: unknown }).rows)) {
          const rows = (parsed as { rows: unknown[] }).rows;
          const cols = (parsed as { columns?: unknown[] }).columns ?? [];
          return {
            text: `${rows.length} row(s) returned (columns: ${cols.join(", ")})`,
            isError,
          };
        }
        return { text: truncate(JSON.stringify(parsed), 300), isError };
      } catch {
        return { text: truncate(raw, 300), isError };
      }
    }
    return { text: isError ? "Tool reported an error." : "(empty response)", isError };
  }

  return { text: truncate(JSON.stringify(obj), 300), isError: false };
}

export function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

/** Readable "key: value" lines for a tool call's arguments. SQL queries in
 * particular are long and multi-line, so they're rendered as their own
 * block rather than inline. */
export function formatArgs(args: Record<string, unknown>): { label: string; value: string; block?: boolean }[] {
  return Object.entries(args).map(([key, value]) => {
    if (typeof value === "string") {
      return { label: key, value, block: value.includes("\n") || value.length > 80 };
    }
    return { label: key, value: JSON.stringify(value), block: false };
  });
}
