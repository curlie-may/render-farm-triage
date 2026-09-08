"use client";

import { useEffect, useState } from "react";

/** Re-renders the caller every `intervalMs` while `active` is true, purely so
 * elapsed-time displays keep counting up. Returns nothing — read Date.now()
 * (or a timestamp field) directly in render after calling this. */
export function useTicker(active: boolean, intervalMs = 500): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setTick((t) => t + 1), intervalMs);
    return () => clearInterval(id);
  }, [active, intervalMs]);
  return tick;
}

export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem.toString().padStart(2, "0")}`;
}
