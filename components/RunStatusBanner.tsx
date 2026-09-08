"use client";

import styles from "@/app/page.module.css";
import type { RunStatus } from "@/lib/runTypes";
import { useTicker, formatElapsed } from "@/lib/useTicker";

interface Props {
  status: RunStatus;
  startedAt: number | null;
  firstByteAt: number | null;
  inFlightLabel: string | null;
  inFlightSince: number | null;
  errorMessage: string | null;
}

export function RunStatusBanner({
  status,
  startedAt,
  firstByteAt,
  inFlightLabel,
  inFlightSince,
  errorMessage,
}: Props) {
  useTicker(status === "connecting" || status === "running");

  if (status === "idle") return null;

  const runElapsed = startedAt ? (Date.now() - startedAt) / 1000 : 0;
  const callElapsed = inFlightSince ? (Date.now() - inFlightSince) / 1000 : 0;

  return (
    <div
      className={[
        styles.statusBanner,
        status === "error" ? styles.statusBannerError : "",
        status === "done" ? styles.statusBannerDone : "",
      ].join(" ")}
    >
      <div className={styles.statusMain}>
        {status === "connecting" && (
          <>
            <span className={styles.spinnerDot} aria-hidden />
            <span>
              Starting the agent — the first request can take up to ~15 seconds while the
              container wakes up. This is normal, not a hang.
            </span>
          </>
        )}
        {status === "running" && (
          <>
            <span className={styles.spinnerDot} aria-hidden />
            <span>{inFlightLabel ? `In progress: ${inFlightLabel}` : "Agent is working…"}</span>
          </>
        )}
        {status === "done" && <span>Run complete.</span>}
        {status === "error" && <span>Run failed: {errorMessage ?? "unknown error"}</span>}
      </div>
      <div className={styles.statusTimers}>
        {startedAt && <span>run {formatElapsed(runElapsed)}</span>}
        {status === "running" && inFlightSince && <span>call {formatElapsed(callElapsed)}</span>}
        {status === "running" && !firstByteAt && <span>waiting for first response…</span>}
      </div>
    </div>
  );
}
