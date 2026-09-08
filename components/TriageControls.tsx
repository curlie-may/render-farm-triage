"use client";

import styles from "@/app/page.module.css";
import type { RunStatus } from "@/lib/runTypes";

interface Props {
  deliveryTarget: string;
  onDeliveryTargetChange: (v: string) => void;
  capacityInput: string;
  onCapacityInputChange: (v: string) => void;
  status: RunStatus;
  onStart: () => void;
}

export function TriageControls({
  deliveryTarget,
  onDeliveryTargetChange,
  capacityInput,
  onCapacityInputChange,
  status,
  onStart,
}: Props) {
  const busy = status === "connecting" || status === "running";

  return (
    <div className={styles.controlsRow}>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>Delivery target</span>
        <input
          type="text"
          className={styles.textInput}
          placeholder="e.g. 8am dailies (optional)"
          value={deliveryTarget}
          onChange={(e) => onDeliveryTargetChange(e.target.value)}
          disabled={busy}
        />
      </label>

      <label className={styles.field}>
        <span className={styles.fieldLabel}>Available farm capacity (node-hours)</span>
        <input
          type="number"
          min={0}
          step="0.5"
          className={styles.textInput}
          placeholder="uses fleet capacity if blank"
          value={capacityInput}
          onChange={(e) => onCapacityInputChange(e.target.value)}
          disabled={busy}
        />
      </label>

      <button className={styles.primaryButton} onClick={onStart} disabled={busy}>
        {busy ? "Running…" : status === "done" || status === "error" ? "Run again" : "Start triage"}
      </button>
    </div>
  );
}
