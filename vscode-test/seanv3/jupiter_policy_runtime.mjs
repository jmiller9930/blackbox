/**
 * Runtime Jupiter policy resolution for SeanV3 — DV-ARCH-JUPITER-POLICY-SWITCH-037.
 * Order: analog_meta.jupiter_active_policy → SEAN_JUPITER_POLICY → default jup_v4.
 * Evaluated fresh each engine cycle (no module-level policy cache).
 */
import { getMeta } from './paper_analog.mjs';
import {
  generateSignalFromOhlcV3,
  resolveEntrySide as resolveEntrySideV3,
  MIN_BARS as MIN_BARS_V3,
  ENGINE_ID as ENGINE_ID_V3,
} from './jupiter_3_sean_policy.mjs';
import {
  generateSignalFromOhlcV4,
  resolveEntrySide as resolveEntrySideV4,
  MIN_BARS as MIN_BARS_V4,
  ENGINE_ID as ENGINE_ID_V4,
} from './jupiter_4_sean_policy.mjs';
import {
  generateSignalFromOhlcMcTest,
  resolveEntrySide as resolveEntrySideMc,
  MIN_BARS as MIN_BARS_MC,
  ENGINE_ID as ENGINE_ID_MC,
} from './jupiter_mc_test_policy.mjs';
import {
  generateSignalFromOhlcMc2,
  resolveEntrySide as resolveEntrySideMc2,
  MIN_BARS as MIN_BARS_MC2,
  ENGINE_ID as ENGINE_ID_MC2,
} from './jupiter_mc2_policy.mjs';
import {
  generateSignalFromOhlcPipelineProof,
  resolveEntrySide as resolveEntrySidePipelineProof,
  MIN_BARS as MIN_BARS_PIPELINE_PROOF,
  ENGINE_ID as ENGINE_ID_PIPELINE_PROOF,
} from './jupiter_pipeline_proof_policy.mjs';
import {
  generateSignalFromOhlcKitchenMechanical,
  resolveEntrySide as resolveEntrySideKitchenMechanical,
  MIN_BARS as MIN_BARS_KITCHEN_MECHANICAL,
  ENGINE_ID as ENGINE_ID_KITCHEN_MECHANICAL,
} from './jupiter_kitchen_mechanical_policy.mjs';

import { ALLOWED_POLICY_IDS } from './jupiter_registry_allowlist.mjs';

export { ALLOWED_POLICY_IDS };

export const JUPITER_ACTIVE_POLICY_KEY = 'jupiter_active_policy';

/**
 * @param {string | null | undefined} s
 * @returns {'jup_v4' | 'jup_v3' | 'jup_mc_test' | 'jup_mc2' | 'jup_pipeline_proof_v1' | 'jup_kitchen_mechanical_v1' | null}
 */
export function normalizePolicyId(s) {
  const t = String(s ?? '')
    .trim()
    .toLowerCase();
  if (!t) return null;
  if (t === 'jup_v4' || t === 'jupiter_4' || t === 'v4') return 'jup_v4';
  if (t === 'jup_v3' || t === 'jupiter_3' || t === 'v3') return 'jup_v3';
  if (t === 'jup_mc_test' || t === 'jupiter_mc_test' || t === 'mc_test') return 'jup_mc_test';
  if (t === 'jup_mc2' || t === 'jupiter_mc2' || t === 'mc2') return 'jup_mc2';
  if (
    t === 'jup_pipeline_proof_v1' ||
    t === 'pipeline_proof' ||
    t === 'pipeline_proof_v1' ||
    t === 'jupiter_pipeline_proof'
  ) {
    return 'jup_pipeline_proof_v1';
  }
  if (
    t === 'jup_kitchen_mechanical_v1' ||
    t === 'kitchen_mechanical' ||
    t === 'kitchen_mechanical_always_long'
  ) {
    return 'jup_kitchen_mechanical_v1';
  }
  return null;
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @returns {{
 *   policyId: 'jup_v4' | 'jup_v3' | 'jup_mc_test' | 'jup_mc2' | 'jup_pipeline_proof_v1' | 'jup_kitchen_mechanical_v1',
 *   source: 'runtime_config' | 'environment' | 'default',
 *   minBars: number,
 *   generateEntrySignal: Function,
 *   resolveEntrySide: (a: boolean, b: boolean) => string | null,
 *   engineId: string,
 *   policyEngineTag: string,
 * }}
 */
export function resolveJupiterPolicy(db) {
  let source = /** @type {'runtime_config' | 'environment' | 'default'} */ ('default');
  let id = normalizePolicyId(getMeta(db, JUPITER_ACTIVE_POLICY_KEY));

  if (id) {
    source = 'runtime_config';
  } else {
    const envId = normalizePolicyId(process.env.SEAN_JUPITER_POLICY);
    if (envId) {
      id = envId;
      source = 'environment';
    } else {
      id = 'jup_v4';
      source = 'default';
    }
  }

  if (!ALLOWED_POLICY_IDS.includes(id)) {
    id = 'jup_v4';
    source = 'default';
  }

  if (id === 'jup_v3') {
    return {
      policyId: 'jup_v3',
      source,
      minBars: MIN_BARS_V3,
      generateEntrySignal: generateSignalFromOhlcV3,
      resolveEntrySide: resolveEntrySideV3,
      engineId: 'sean_jupiter3_engine_v1',
      policyEngineTag: ENGINE_ID_V3,
    };
  }
  if (id === 'jup_mc_test') {
    return {
      policyId: 'jup_mc_test',
      source,
      minBars: MIN_BARS_MC,
      generateEntrySignal: generateSignalFromOhlcMcTest,
      resolveEntrySide: resolveEntrySideMc,
      engineId: 'sean_jupiter_mc_test_engine_v1',
      policyEngineTag: ENGINE_ID_MC,
    };
  }
  if (id === 'jup_mc2') {
    return {
      policyId: 'jup_mc2',
      source,
      minBars: MIN_BARS_MC2,
      generateEntrySignal: generateSignalFromOhlcMc2,
      resolveEntrySide: resolveEntrySideMc2,
      engineId: 'sean_jupiter_mc2_engine_v1',
      policyEngineTag: ENGINE_ID_MC2,
    };
  }
  if (id === 'jup_pipeline_proof_v1') {
    return {
      policyId: 'jup_pipeline_proof_v1',
      source,
      minBars: MIN_BARS_PIPELINE_PROOF,
      generateEntrySignal: generateSignalFromOhlcPipelineProof,
      resolveEntrySide: resolveEntrySidePipelineProof,
      engineId: 'sean_jupiter_pipeline_proof_engine_v1',
      policyEngineTag: ENGINE_ID_PIPELINE_PROOF,
    };
  }
  if (id === 'jup_kitchen_mechanical_v1') {
    return {
      policyId: 'jup_kitchen_mechanical_v1',
      source,
      minBars: MIN_BARS_KITCHEN_MECHANICAL,
      generateEntrySignal: generateSignalFromOhlcKitchenMechanical,
      resolveEntrySide: resolveEntrySideKitchenMechanical,
      engineId: 'sean_jupiter_kitchen_mechanical_engine_v1',
      policyEngineTag: ENGINE_ID_KITCHEN_MECHANICAL,
    };
  }
  return {
    policyId: 'jup_v4',
    source,
    minBars: MIN_BARS_V4,
    generateEntrySignal: generateSignalFromOhlcV4,
    resolveEntrySide: resolveEntrySideV4,
    engineId: 'sean_jupiter4_engine_v1',
    policyEngineTag: ENGINE_ID_V4,
  };
}
