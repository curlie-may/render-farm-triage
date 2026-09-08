import { ActivityItem, formatArgs, summarizeToolResponse } from "./agentEvents";
import { AgentPlan } from "./planParser";

export type StepApprovalStatus = "pending" | "accepted" | "modified" | "rejected";

export interface StepApproval {
  status: StepApprovalStatus;
  editedAction?: string;
}

function elapsed(startedAt: number, timestamp: number): string {
  const s = Math.max(0, Math.round(timestamp - startedAt));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function renderActivityLog(activity: ActivityItem[], startedAt: number | null): string {
  if (activity.length === 0) return "_No activity recorded._\n";
  const base = startedAt ?? activity[0].timestamp;
  const lines: string[] = [];
  for (const item of activity) {
    const t = elapsed(base, item.timestamp);
    switch (item.kind) {
      case "tool_call": {
        const args = formatArgs(item.args)
          .map((a) => `  ${a.label}: ${a.value}`)
          .join("\n");
        lines.push(`**[${t}] Tool call — \`${item.name}\`**`);
        if (args) lines.push("```\n" + args + "\n```");
        break;
      }
      case "tool_response": {
        const { text, isError } = summarizeToolResponse(item.response);
        lines.push(`**[${t}] Tool response — \`${item.name}\`**${isError ? " ⚠️ error" : ""}`);
        lines.push(`> ${text.replace(/\n/g, "\n> ")}`);
        break;
      }
      case "text": {
        lines.push(`**[${t}] Agent**`);
        lines.push(`> ${item.text.replace(/\n/g, "\n> ")}`);
        break;
      }
      case "error": {
        lines.push(`**[${t}] Error**`);
        lines.push(`> ${item.message}`);
        break;
      }
    }
    lines.push("");
  }
  return lines.join("\n");
}

function renderPlan(plan: AgentPlan | null, approvals: Record<string, StepApproval>): string {
  if (!plan) return "_No structured plan was produced for this run._\n";

  const cap = plan.capacity;
  const pct = (cap.fraction_of_capacity * 100).toFixed(1);
  const capacitySection = [
    "### Capacity",
    "",
    `- Available: ${cap.available_node_hours} node-hours`,
    `- Required: ${cap.required_node_hours} node-hours`,
    `- Proportion: ${pct}%`,
    cap.note ? `- ${cap.note}` : "",
    "",
  ]
    .filter(Boolean)
    .join("\n");

  const resolvedSection = [
    "### Resolved work",
    "",
    plan.resolved_work.task_count > 0
      ? `${plan.resolved_work.task_count} task(s) already resolved. ${plan.resolved_work.summary}`
      : "No work reported as already resolved.",
    "",
  ].join("\n");

  const stepLines = plan.steps.map((step, i) => {
    const approval = approvals[step.id];
    const status = approval?.status ?? "pending";
    const statusLabel =
      status === "accepted"
        ? "✅ Accepted"
        : status === "rejected"
          ? "❌ Rejected"
          : status === "modified"
            ? "✏️ Modified"
            : "⏳ Pending";
    const action = status === "modified" && approval?.editedAction ? approval.editedAction : step.action;
    return [
      `#### Step ${i + 1}: ${step.title} — ${statusLabel}`,
      "",
      `- Action: ${action}`,
      `- Depends on: ${step.depends_on ?? "nothing"}`,
      `- Affected tasks: ${step.affected_tasks}`,
      `- Cost: ${step.cost_node_hours} node-hours`,
      `- Reason: ${step.reason}`,
      "",
    ].join("\n");
  });

  return [resolvedSection, capacitySection, "### Steps", "", ...stepLines].join("\n");
}

export function buildMarkdownExport(params: {
  generatedAt: Date;
  status: "running" | "done" | "error";
  startedAt: number | null;
  activity: ActivityItem[];
  prose: string;
  plan: AgentPlan | null;
  approvals: Record<string, StepApproval>;
  errorMessage: string | null;
}): string {
  const { generatedAt, status, startedAt, activity, prose, plan, approvals, errorMessage } = params;

  const header = [
    "# Render Farm Triage Run",
    "",
    `Generated: ${generatedAt.toISOString()}`,
    `Run status: ${status}${status === "error" && errorMessage ? ` (${errorMessage})` : ""}`,
    "",
  ].join("\n");

  const sections = [
    header,
    "## Activity Log",
    "",
    renderActivityLog(activity, startedAt),
    "## Findings",
    "",
    prose || "_No findings text was produced before the run ended._",
    "",
    "## Plan",
    "",
    renderPlan(plan, approvals),
  ];

  return sections.join("\n");
}

export function triggerMarkdownDownload(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
