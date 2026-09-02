import { NextResponse } from "next/server";
import { roundSig } from "./stats";

/** Every tool route returns HTTP 200 always. Errors are a structured field,
 * not a transport failure — Agent Builder handles that better. */
export function jsonOk<T extends object>(body: T) {
  return NextResponse.json(body, { status: 200 });
}

export function jsonError(message: string) {
  return NextResponse.json({ error: message }, { status: 200 });
}

/** Recursively rounds every finite NON-INTEGER number in an object/array to
 * `sig` significant figures, so responses fed to a model stay compact.
 * Integers (row counts, task counts, node counts, ...) are left exact —
 * rounding e.g. 9996 to 3 sig figs would silently turn it into 10000. */
export function roundDeep<T>(value: T, sig = 3): T {
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Number.isInteger(value)) return value as unknown as T;
    return roundSig(value, sig) as unknown as T;
  }
  if (Array.isArray(value)) {
    return value.map((v) => roundDeep(v, sig)) as unknown as T;
  }
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = roundDeep(v, sig);
    }
    return out as T;
  }
  return value;
}
