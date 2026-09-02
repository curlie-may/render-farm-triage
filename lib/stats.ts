// Exact two-sided binomial test, implemented from scratch on log-gamma /
// log-pmf. No normal approximation, no external stats dependency.

import { SIG_LEVEL, STRONG_SIG_LEVEL } from "./constants";

// ---------------------------------------------------------------------------
// log-gamma (Lanczos approximation, g=7, n=9) — standard coefficients.
// ---------------------------------------------------------------------------

const LANCZOS_G = 7;
const LANCZOS_COEF = [
  0.99999999999980993,
  676.5203681218851,
  -1259.1392167224028,
  771.32342877765313,
  -176.61502916214059,
  12.507343278686905,
  -0.13857109526572012,
  9.9843695780195716e-6,
  1.5056327351493116e-7,
];

function logGamma(x: number): number {
  if (x < 0.5) {
    // Reflection formula for small/negative x.
    return Math.log(Math.PI / Math.sin(Math.PI * x)) - logGamma(1 - x);
  }
  x -= 1;
  let a = LANCZOS_COEF[0];
  const t = x + LANCZOS_G + 0.5;
  for (let i = 1; i < LANCZOS_G + 2; i++) {
    a += LANCZOS_COEF[i] / (x + i);
  }
  return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a);
}

/** log(n choose k), via log-gamma. -Infinity outside [0, n]. */
function logChoose(n: number, k: number): number {
  if (k < 0 || k > n) return -Infinity;
  return logGamma(n + 1) - logGamma(k + 1) - logGamma(n - k + 1);
}

/** log(P(X = k)) for X ~ Binomial(n, p). -Infinity where the pmf is 0. */
function logPmf(k: number, n: number, p: number): number {
  if (k < 0 || k > n) return -Infinity;
  if (p <= 0) return k === 0 ? 0 : -Infinity;
  if (p >= 1) return k === n ? 0 : -Infinity;
  return logChoose(n, k) + k * Math.log(p) + (n - k) * Math.log(1 - p);
}

/**
 * Two-sided exact binomial test p-value for `k` successes in `n` trials
 * against null probability `p` — the PMF-comparison ("relative likelihood")
 * method scipy's `binomtest` uses by default: sum the probability of every
 * outcome j in [0, n] whose PMF is <= PMF(k), on BOTH tails, entirely in log
 * space to avoid underflow when PMF(k) itself is astronomically small.
 *
 * An earlier version of this function computed the two-sided p-value by
 * doubling whichever tail was smaller. That is wrong whenever the observed
 * value sits far enough into one tail that the opposite tail contributes
 * nothing to the exact test — true for essentially every strongly
 * concentrated finding this tool exists to detect, not only at the k=n
 * boundary. It silently doubled the true p-value across that entire regime
 * (verified: exactly 2.0x on Fault A's shot_id concentration, k=75 of
 * n=250 — nowhere near a boundary). The PMF-comparison method below
 * includes only the opposite-tail outcomes that are actually as-or-more
 * extreme, which can correctly be zero of them.
 */
export function twoSidedBinomTest(k: number, n: number, p: number): number {
  if (n <= 0) return 1;
  if (p <= 0) return k === 0 ? 1 : 0;
  if (p >= 1) return k === n ? 1 : 0;

  const logPk = logPmf(k, n, p);
  // Relative tolerance so floating-point noise doesn't exclude k's own
  // outcome (or its exact mirror) from its own "as extreme" set.
  const threshold = logPk + Math.log1p(1e-7);

  let total = 0;
  for (let j = 0; j <= n; j++) {
    const lj = logPmf(j, n, p);
    if (lj <= threshold) total += Math.exp(lj);
  }
  return Math.min(1, total);
}

/** Bonferroni correction: p * (number of hypotheses tested), capped at 1. */
export function bonferroni(pValue: number, numTests: number): number {
  return Math.min(1, pValue * numTests);
}

// ---------------------------------------------------------------------------
// Verdicts
// ---------------------------------------------------------------------------

export type Verdict = "strong concentration" | "concentration above base rate" | "no concentration above base rate";

export function verdictForValue(pCorrected: number, observedShare: number, expectedShare: number): Verdict {
  if (pCorrected < STRONG_SIG_LEVEL && observedShare > expectedShare) return "strong concentration";
  if (pCorrected < SIG_LEVEL && observedShare > expectedShare) return "concentration above base rate";
  return "no concentration above base rate";
}

export function dimensionVerdict(anyValueConcentrates: boolean, topValueDescription?: string): string {
  if (!anyValueConcentrates) {
    return "no value in this dimension concentrates above base rate";
  }
  return topValueDescription
    ? `concentration found: ${topValueDescription}`
    : "at least one value in this dimension concentrates above base rate";
}

/** Round to N significant figures (default 3), for compact API responses. */
export function roundSig(x: number, sig = 3): number {
  if (x === 0 || !isFinite(x)) return x;
  const d = Math.ceil(Math.log10(Math.abs(x)));
  const power = sig - d;
  const magnitude = Math.pow(10, power);
  const shifted = Math.round(x * magnitude);
  return shifted / magnitude;
}
