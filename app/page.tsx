"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import styles from "./page.module.css";
import { TriageControls } from "@/components/TriageControls";
import { RunStatusBanner } from "@/components/RunStatusBanner";
import { ActivityFeed } from "@/components/ActivityFeed";
import { FindingsPanel } from "@/components/FindingsPanel";
import { PlanPanel } from "@/components/PlanPanel";
import { DownloadButton } from "@/components/DownloadButton";
import {
  ActivityItem,
  AgentEvent,
  AgentStreamError,
  eventToActivityItems,
  isStreamError,
} from "@/lib/agentEvents";
import { parseFindings } from "@/lib/planParser";
import { buildMarkdownExport, triggerMarkdownDownload, StepApproval } from "@/lib/markdownExport";
import type { RunStatus } from "@/lib/runTypes";

export default function Home() {
  const [deliveryTarget, setDeliveryTarget] = useState("");
  const [capacityInput, setCapacityInput] = useState("");
  const [status, setStatus] = useState<RunStatus>("idle");
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [firstByteAt, setFirstByteAt] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<Record<string, StepApproval>>({});

  // Guards against a stale in-flight fetch loop writing state after a new
  // run has already started (e.g. the user clicks "Run again" quickly).
  const runToken = useRef(0);

  // A chronological walk, not a set-difference on ids: the deployed agent
  // has been observed reusing the same functionCall id across unrelated
  // calls in one run, so pairing must track "the most recently opened call
  // for this id," not just "has this id ever been responded to."
  const inFlight = useMemo(() => {
    const pending = new Map<string, Extract<ActivityItem, { kind: "tool_call" }>>();
    let unkeyedCounter = 0;
    for (const item of activity) {
      if (item.kind === "tool_call") {
        const k = item.callId || `__unkeyed_call_${unkeyedCounter++}`;
        pending.set(k, item);
      } else if (item.kind === "tool_response" && item.callId) {
        pending.delete(item.callId);
      }
    }
    return [...pending.values()];
  }, [activity]);

  const inFlightLabel = inFlight.length > 0 ? inFlight.map((c) => c.name).join(", ") : null;
  const inFlightSince =
    inFlight.length > 0 ? Math.min(...inFlight.map((c) => c.timestamp)) * 1000 : null;

  const finalAnswerText = useMemo(() => {
    const textItems = activity.filter((a): a is Extract<ActivityItem, { kind: "text" }> => a.kind === "text");
    const withFence = [...textItems].reverse().find((t) => t.text.includes("```json"));
    if (withFence) return withFence.text;
    if (status === "done" || status === "error") return textItems.at(-1)?.text ?? "";
    return "";
  }, [activity, status]);

  const findings = useMemo(() => parseFindings(finalAnswerText), [finalAnswerText]);

  const operatorCapacityHours = useMemo(() => {
    const n = parseFloat(capacityInput);
    return Number.isFinite(n) && n > 0 ? n : null;
  }, [capacityInput]);

  const handleSetApproval = useCallback((id: string, approval: StepApproval) => {
    setApprovals((prev) => ({ ...prev, [id]: approval }));
  }, []);

  const startRun = useCallback(async () => {
    const myToken = ++runToken.current;
    setActivity([]);
    setApprovals({});
    setErrorMessage(null);
    setFirstByteAt(null);
    setStartedAt(Date.now());
    setStatus("connecting");

    try {
      const res = await fetch("/api/agent/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          deliveryTarget: deliveryTarget.trim() || undefined,
          capacityHours: operatorCapacityHours ?? undefined,
        }),
      });

      if (runToken.current !== myToken) return;

      if (!res.ok || !res.body) {
        const errBody = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
        throw new Error(errBody.error ?? `HTTP ${res.status}`);
      }

      setStatus("running");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let recordedFirstByte = false;

      while (true) {
        const { done, value } = await reader.read();
        if (runToken.current !== myToken) return;
        if (done) break;

        if (!recordedFirstByte) {
          recordedFirstByte = true;
          setFirstByteAt(Date.now());
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const data = line.slice(5).trim();
          if (!data) continue;

          let parsed: AgentEvent | AgentStreamError;
          try {
            parsed = JSON.parse(data);
          } catch {
            continue;
          }

          if (isStreamError(parsed)) {
            setErrorMessage(parsed.error);
            setActivity((prev) => [
              ...prev,
              { kind: "error", key: `stream-error-${Date.now()}`, message: parsed.error, timestamp: Date.now() / 1000 },
            ]);
            continue;
          }

          const items = eventToActivityItems(parsed);
          if (items.length > 0) setActivity((prev) => [...prev, ...items]);
        }
      }

      if (runToken.current !== myToken) return;
      setStatus("done");
    } catch (err) {
      if (runToken.current !== myToken) return;
      const message = err instanceof Error ? err.message : String(err);
      setErrorMessage(message);
      setActivity((prev) => [
        ...prev,
        { kind: "error", key: `fatal-${Date.now()}`, message, timestamp: Date.now() / 1000 },
      ]);
      setStatus("error");
    }
  }, [deliveryTarget, operatorCapacityHours]);

  const handleDownload = useCallback(() => {
    const content = buildMarkdownExport({
      generatedAt: new Date(),
      status: status === "connecting" ? "running" : status === "idle" ? "running" : status,
      startedAt,
      activity,
      prose: findings.prose,
      plan: findings.plan,
      approvals,
      errorMessage,
    });
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    triggerMarkdownDownload(`render-farm-triage-${stamp}.md`, content);
  }, [status, startedAt, activity, findings, approvals, errorMessage]);

  const hasOutput = activity.length > 0;
  const showFindings = finalAnswerText !== "";

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Render Farm Triage</h1>
        <p className={styles.subtitle}>
          Diagnoses last night&rsquo;s batch failures and proposes a re-queue plan. It never executes anything — every
          step below is a proposal for a human to accept, modify, or reject.
        </p>
      </header>

      <section className={styles.controlsSection}>
        <TriageControls
          deliveryTarget={deliveryTarget}
          onDeliveryTargetChange={setDeliveryTarget}
          capacityInput={capacityInput}
          onCapacityInputChange={setCapacityInput}
          status={status}
          onStart={startRun}
        />
        <RunStatusBanner
          status={status}
          startedAt={startedAt}
          firstByteAt={firstByteAt}
          inFlightLabel={inFlightLabel}
          inFlightSince={inFlightSince}
          errorMessage={errorMessage}
        />
      </section>

      <div className={styles.mainGrid}>
        <section className={styles.activityColumn}>
          <h2 className={styles.columnTitle}>Live activity</h2>
          <div className={styles.activityScroll}>
            <ActivityFeed items={activity} startedAt={startedAt} />
          </div>
        </section>

        <section className={styles.resultsColumn}>
          {!showFindings && (
            <p className={styles.placeholder}>
              Findings and the remediation plan will appear here once the run produces its final answer.
            </p>
          )}
          {showFindings && (
            <>
              <FindingsPanel prose={findings.prose} />
              <PlanPanel
                plan={findings.plan}
                planError={findings.planError}
                prose={findings.prose}
                approvals={approvals}
                onSetApproval={handleSetApproval}
                operatorCapacityHours={operatorCapacityHours}
              />
            </>
          )}
        </section>
      </div>

      <footer className={styles.footer}>
        <DownloadButton disabled={!hasOutput} onDownload={handleDownload} />
      </footer>
    </div>
  );
}
