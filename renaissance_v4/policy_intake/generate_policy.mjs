#!/usr/bin/env node
/**
 * Single script: ALL operator inputs live in OPERATOR_INPUT below.
 * Run:  node renaissance_v4/policy_intake/generate_policy.mjs
 *
 * Optional:  node generate_policy.mjs path/to/override.json  (same shape; used by CI/UI if you export JSON)
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// =============================================================================
// OPERATOR INPUT — edit ONLY this object. Then run:  node generate_policy.mjs
//
// DEFAULT: EVERYTHING OFF — no policy is generated until you opt in.
//   - Set policy_enabled to true when you are ready to build a policy.
//   - Set strategy to a real strategy (e.g. close_vs_previous). "none" = no policy.
// Optional: node generate_policy.mjs path/to/override.json  (merges over this object)
// =============================================================================
const OPERATOR_INPUT = {
  /** MUST be true to emit a .ts file. false = nothing on = no policy (generator exits). */
  policy_enabled: false,
  output_filename: 'kitchen_policy_generated.ts',
  policy_id: 'kitchen_import_template_v1',
  display_name: 'Kitchen policy (generated from generate_policy.mjs)',
  version: '1.0.0',
  timeframe: '5m',
  author: 'operator',
  description:
    'Set policy_enabled=true and strategy to generate. Default: no policy until you enable.',
  min_bars: 2,
  /** "none" until you choose a strategy after enabling policy. */
  strategy: 'none',
  indicators: [],
  gates: [],
};

// =============================================================================
// Generator (do not edit unless you are extending strategies)
// =============================================================================

const __dirname = dirname(fileURLToPath(import.meta.url));

let op = { ...OPERATOR_INPUT };
if (process.argv[2]) {
  const p = join(process.cwd(), process.argv[2]);
  try {
    op = { ...op, ...JSON.parse(readFileSync(p, 'utf8')) };
  } catch (e) {
    console.error('generate_policy: failed to read/parse override', p, String(e && e.message ? e.message : e));
    process.exit(1);
  }
}

if (op.policy_enabled !== true) {
  console.error(
    'generate_policy: No policy generated — policy_enabled is not true. Nothing on = no policy. Set policy_enabled: true in OPERATOR_INPUT when you want a policy.',
  );
  process.exit(1);
}

const strategyNorm = String(op.strategy || 'none').toLowerCase();
if (strategyNorm === 'none' || strategyNorm === '') {
  console.error(
    'generate_policy: No policy generated — strategy is "none". Choose a strategy (e.g. close_vs_previous) after enabling policy.',
  );
  process.exit(1);
}

const outName = String(op.output_filename || 'kitchen_policy_generated.ts').replace(/[^a-zA-Z0-9._-]/g, '_');
const outPath = join(__dirname, outName);

const embedded = JSON.stringify(op, null, 2);

const strategy = strategyNorm;
let signalBody;
if (strategy === 'close_vs_previous') {
  signalBody = `
  void _highs;
  void _lows;
  void _volumes;
  const n = closes.length;
  if (n < MIN_BARS) {
    return {
      shortSignal: false,
      longSignal: false,
      signalPrice: 0,
      diag: { reason: "insufficient_bars", policy: POLICY_ID },
    };
  }
  const latest = closes[n - 1]!;
  const previous = closes[n - 2]!;
  const longSignal = latest > previous;
  const shortSignal = latest < previous;
  const rsi = ctx?.indicators?.rsi_main;
  const diag: Record<string, unknown> = {
    policy: POLICY_ID,
    latest_close: latest,
    previous_close: previous,
  };
  if (typeof rsi === "number" && Number.isFinite(rsi)) {
    diag.rsi_at_bar = rsi;
  }
  return {
    longSignal,
    shortSignal,
    signalPrice: latest,
    diag,
  };`;
} else {
  console.error('generate_policy: unknown strategy:', strategy);
  process.exit(1);
}

const ts = `/**
 * GENERATED — do not edit by hand.
 * Source: OPERATOR_INPUT at top of renaissance_v4/policy_intake/generate_policy.mjs → node generate_policy.mjs
 */
const OPERATOR_DECLARATIONS_JSON = \`${embedded.replace(/`/g, '\\`')}\`;

export type OperatorDeclarations = {
  policy_enabled?: boolean;
  output_filename: string;
  policy_id: string;
  display_name: string;
  version: string;
  timeframe: string;
  author: string;
  description: string;
  min_bars: number;
  strategy?: string;
  indicators: Array<{ id: string; kind: string; params?: Record<string, unknown> }>;
  gates: unknown[];
};

export const OPERATOR_DECLARATIONS = JSON.parse(OPERATOR_DECLARATIONS_JSON) as OperatorDeclarations;

export const POLICY_ID = OPERATOR_DECLARATIONS.policy_id;

export const POLICY_META = {
  policy_id: OPERATOR_DECLARATIONS.policy_id,
  name: OPERATOR_DECLARATIONS.display_name,
  version: OPERATOR_DECLARATIONS.version,
  timeframe: OPERATOR_DECLARATIONS.timeframe,
  author: OPERATOR_DECLARATIONS.author,
  policy_class: "candidate" as const,
  promotion_eligible: false,
  target_systems: ["jupiter", "blackbox"],
  description: OPERATOR_DECLARATIONS.description,
};

export const MIN_BARS = Math.max(2, Math.floor(Number(OPERATOR_DECLARATIONS.min_bars) || 2));

export function generateSignalFromOhlc(
  closes: number[],
  _highs: number[],
  _lows: number[],
  _volumes: number[],
  ctx?: { schemaVersion?: string; indicators?: Record<string, number | null | Record<string, unknown>> },
): {
  longSignal: boolean;
  shortSignal: boolean;
  signalPrice: number;
  diag?: Record<string, unknown>;
} {${signalBody}
}
`;

writeFileSync(outPath, ts, 'utf8');
console.log('wrote', outPath);
