import { NextRequest } from "next/server";

// Proxies to the deployed ADK agent (Cloud Run) so its URL never reaches the
// client bundle. No credentials are forwarded — the agent endpoint currently
// allows unauthenticated invocation — but the URL itself stays server-side.
//
// A cold run has measured at ~222s end to end with ~15s before the first SSE
// byte; a warm run ~184s / ~10s. 300s is both the Hobby-plan default and its
// hard ceiling (Vercel Functions, Fluid compute), so it's set explicitly here
// rather than left implicit, and comfortably covers the cold case.
export const maxDuration = 300;
export const dynamic = "force-dynamic";

const APP_NAME = "agent";
const USER_ID = "web-ui";

interface RunRequestBody {
  deliveryTarget?: string;
  capacityHours?: number;
}

function buildMessage(body: RunRequestBody): string {
  const parts = ["Triage last night's batch."];
  if (body.deliveryTarget && body.deliveryTarget.trim()) {
    parts.push(`Delivery target: ${body.deliveryTarget.trim()}.`);
  }
  if (typeof body.capacityHours === "number" && Number.isFinite(body.capacityHours) && body.capacityHours > 0) {
    parts.push(`Available farm capacity for this window: ${body.capacityHours} node-hours.`);
  }
  return parts.join(" ");
}

export async function POST(req: NextRequest) {
  const baseUrl = process.env.AGENT_BASE_URL;
  if (!baseUrl) {
    return Response.json(
      { error: "AGENT_BASE_URL is not configured on the server." },
      { status: 500 }
    );
  }

  let body: RunRequestBody;
  try {
    body = await req.json();
  } catch {
    body = {};
  }

  const sessionId = crypto.randomUUID();

  let sessionResp: Response;
  try {
    sessionResp = await fetch(
      `${baseUrl}/apps/${APP_NAME}/users/${USER_ID}/sessions/${sessionId}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
        signal: req.signal,
      }
    );
  } catch (err) {
    return Response.json(
      { error: `Could not reach the agent to start a session: ${err instanceof Error ? err.message : String(err)}` },
      { status: 502 }
    );
  }

  if (!sessionResp.ok) {
    const detail = await sessionResp.text().catch(() => "");
    return Response.json(
      { error: `Agent rejected session creation (${sessionResp.status}): ${detail}` },
      { status: 502 }
    );
  }

  const runPayload = {
    app_name: APP_NAME,
    user_id: USER_ID,
    session_id: sessionId,
    new_message: {
      role: "user",
      parts: [{ text: buildMessage(body) }],
    },
    streaming: false,
  };

  let runResp: Response;
  try {
    runResp = await fetch(`${baseUrl}/run_sse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(runPayload),
      signal: req.signal,
    });
  } catch (err) {
    return Response.json(
      { error: `Could not reach the agent to start the run: ${err instanceof Error ? err.message : String(err)}` },
      { status: 502 }
    );
  }

  if (!runResp.ok || !runResp.body) {
    const detail = await runResp.text().catch(() => "");
    return Response.json(
      { error: `Agent rejected the run request (${runResp.status}): ${detail}` },
      { status: 502 }
    );
  }

  return new Response(runResp.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
