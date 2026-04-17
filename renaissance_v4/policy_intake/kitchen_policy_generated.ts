/**
 * GENERATED — do not edit by hand.
 * Source: OPERATOR_INPUT at top of renaissance_v4/policy_intake/generate_policy.mjs → node generate_policy.mjs
 */
const OPERATOR_DECLARATIONS_JSON = `{
  "policy_enabled": true,
  "output_filename": "kitchen_policy_generated.ts",
  "policy_id": "kitchen_import_template_v1",
  "display_name": "Kitchen policy (generated from generate_policy.mjs)",
  "version": "1.0.0",
  "timeframe": "5m",
  "author": "operator",
  "description": "CI: minimal viable policy for intake test (override default all-off).",
  "min_bars": 2,
  "strategy": "close_vs_previous",
  "indicators": [],
  "gates": []
}`;

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
} {
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
  };
}
