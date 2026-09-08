"use client";

import { useState } from "react";
import styles from "@/app/page.module.css";
import type { AgentPlan, PlanStep } from "@/lib/planParser";
import type { StepApproval, StepApprovalStatus } from "@/lib/markdownExport";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  plan: AgentPlan | null;
  planError: string | null;
  prose: string;
  approvals: Record<string, StepApproval>;
  onSetApproval: (id: string, approval: StepApproval) => void;
  operatorCapacityHours: number | null;
}

function statusSatisfiesDependency(status: StepApprovalStatus | undefined): boolean {
  return status === "accepted" || status === "modified";
}

type Blocker = (PlanStep & { approvedStatus?: StepApprovalStatus }) | null;

function StepCard({
  step,
  index,
  approval,
  blockedBy,
  onSetApproval,
}: {
  step: PlanStep;
  index: number;
  approval: StepApproval;
  blockedBy: Blocker;
  onSetApproval: (approval: StepApproval) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(step.action);

  const isBlocked = blockedBy !== null;
  const status = approval.status;

  return (
    <li
      data-testid="step-card"
      data-blocked={isBlocked}
      className={`${styles.stepCard} ${isBlocked ? styles.stepBlocked : ""}`}
    >
      <div className={styles.stepHeader}>
        <span className={styles.stepIndex}>{index + 1}</span>
        <h3 className={styles.stepTitle}>{step.title}</h3>
        <span
          className={[
            styles.stepStatusBadge,
            status === "accepted" ? styles.badgeAccepted : "",
            status === "rejected" ? styles.badgeRejected : "",
            status === "modified" ? styles.badgeModified : "",
          ].join(" ")}
        >
          {status === "pending" ? "Pending" : status === "accepted" ? "Accepted" : status === "rejected" ? "Rejected" : "Modified"}
        </span>
      </div>

      {isBlocked && (
        <p className={styles.blockedNotice}>
          Blocked — waiting on <strong>{blockedBy!.title}</strong>
          {blockedBy!.approvedStatus === "rejected" ? " (rejected — this step cannot proceed until that's resolved)" : " to be accepted"}
        </p>
      )}

      <dl className={styles.stepMeta}>
        <div>
          <dt>Action</dt>
          <dd>
            {editing ? (
              <div className={styles.editBox}>
                <textarea
                  className={styles.editTextarea}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={3}
                />
                <div className={styles.editActions}>
                  <button
                    className={styles.smallButton}
                    onClick={() => {
                      onSetApproval({ status: "modified", editedAction: draft });
                      setEditing(false);
                    }}
                  >
                    Save
                  </button>
                  <button
                    className={styles.smallButtonGhost}
                    onClick={() => {
                      setDraft(status === "modified" && approval.editedAction ? approval.editedAction : step.action);
                      setEditing(false);
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <span>{status === "modified" && approval.editedAction ? approval.editedAction : step.action}</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Depends on</dt>
          <dd>{step.depends_on ? step.depends_on : "nothing"}</dd>
        </div>
        <div>
          <dt>Affected tasks</dt>
          <dd>{step.affected_tasks}</dd>
        </div>
        <div>
          <dt>Cost</dt>
          <dd>{step.cost_node_hours} node-hours</dd>
        </div>
        <div className={styles.stepReason}>
          <dt>Reason</dt>
          <dd>{step.reason}</dd>
        </div>
      </dl>

      {!editing && (
        <div className={styles.stepActions}>
          <button
            className={styles.smallButton}
            disabled={isBlocked}
            title={isBlocked ? "Accept the blocking step first" : undefined}
            onClick={() => onSetApproval({ status: "accepted" })}
          >
            Accept
          </button>
          <button
            className={styles.smallButtonGhost}
            disabled={isBlocked}
            title={isBlocked ? "Accept the blocking step first" : undefined}
            onClick={() => {
              setDraft(status === "modified" && approval.editedAction ? approval.editedAction : step.action);
              setEditing(true);
            }}
          >
            Modify
          </button>
          <button className={styles.smallButtonDanger} onClick={() => onSetApproval({ status: "rejected" })}>
            Reject
          </button>
        </div>
      )}
    </li>
  );
}

export function PlanPanel({ plan, planError, prose, approvals, onSetApproval, operatorCapacityHours }: Props) {
  if (!plan) {
    return (
      <section data-testid="plan-panel" className={styles.panel}>
        <h2 className={styles.panelTitle}>Plan</h2>
        <p data-testid="plan-unavailable-warning" className={styles.warningNote}>
          The structured plan view is unavailable{planError ? ` (${planError})` : " (no plan block was found)"}. Showing
          the plan as written instead.
        </p>
        <div className={styles.markdown}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{prose}</ReactMarkdown>
        </div>
      </section>
    );
  }

  const byId = new Map(plan.steps.map((s) => [s.id, s]));
  const pct = plan.capacity.fraction_of_capacity * 100;
  const operatorPct =
    operatorCapacityHours && operatorCapacityHours > 0
      ? (plan.capacity.required_node_hours / operatorCapacityHours) * 100
      : null;
  const operatorShortfall = operatorPct !== null && operatorPct > 100;

  return (
    <section data-testid="plan-panel" className={styles.panel}>
      <h2 className={styles.panelTitle}>Plan</h2>
      <p className={styles.mutedNote}>
        This is a proposal only. Accepting, modifying, or rejecting a step below changes nothing on the farm — it only
        records what you'd approve.
      </p>

      <div className={styles.subPanel}>
        <h3 className={styles.subPanelTitle}>Resolved work</h3>
        {plan.resolved_work.task_count > 0 ? (
          <p>
            <strong>{plan.resolved_work.task_count}</strong> task(s) already resolved on their own — no action needed.{" "}
            {plan.resolved_work.summary}
          </p>
        ) : (
          <p className={styles.mutedNote}>No failures resolved on their own this run.</p>
        )}
      </div>

      <div className={styles.subPanel}>
        <h3 className={styles.subPanelTitle}>Capacity</h3>
        <div className={styles.capacityBarTrack}>
          <div
            className={styles.capacityBarFill}
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        </div>
        <p>
          <strong>{plan.capacity.required_node_hours}</strong> node-hours required of{" "}
          <strong>{plan.capacity.available_node_hours}</strong> available in the window ({pct.toFixed(1)}%).
        </p>
        {plan.capacity.note && <p className={styles.mutedNote}>{plan.capacity.note}</p>}

        {operatorPct !== null && (
          <div className={operatorShortfall ? styles.shortfallBox : styles.okBox}>
            Against your stated capacity of {operatorCapacityHours} node-hours: {operatorPct.toFixed(1)}% used.
            {operatorShortfall
              ? " This exceeds what you have available — something in the plan below has to slip."
              : " That still fits."}
          </div>
        )}
      </div>

      <h3 className={styles.subPanelTitle}>Steps</h3>
      <ol className={styles.stepList}>
        {plan.steps.map((step, i) => {
          const blockerId = step.depends_on;
          const blocker = blockerId ? byId.get(blockerId) ?? null : null;
          const blockerApproval = blockerId ? approvals[blockerId] : undefined;
          const satisfied = !blocker || statusSatisfiesDependency(blockerApproval?.status);
          const blockedBy: Blocker = !satisfied && blocker ? { ...blocker, approvedStatus: blockerApproval?.status } : null;

          return (
            <StepCard
              key={step.id}
              step={step}
              index={i}
              approval={approvals[step.id] ?? { status: "pending" }}
              blockedBy={blockedBy}
              onSetApproval={(a) => onSetApproval(step.id, a)}
            />
          );
        })}
      </ol>
    </section>
  );
}
