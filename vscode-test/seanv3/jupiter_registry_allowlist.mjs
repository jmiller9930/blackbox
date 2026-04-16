/**
 * DV-070 — Jupiter allowed policy IDs come only from BlackBox kitchen policy registry.
 * Reads ``renaissance_v4/config/kitchen_policy_registry_v1.json`` under BLACKBOX_REPO_ROOT.
 * Fallback: embedded list if the file is missing (dev / misconfiguration).
 */
import fs from 'node:fs';
import path from 'node:path';

const FALLBACK_JUPITER_ALLOWED = Object.freeze([
  'jup_v4',
  'jup_v3',
  'jup_mc_test',
  'jup_mc2',
  'jup_pipeline_proof_v1',
  'jup_kitchen_mechanical_v1',
]);

/**
 * @returns {readonly string[]}
 */
export function loadJupiterAllowedPolicyIdsFromRegistry() {
  const root = (process.env.BLACKBOX_REPO_ROOT || '').trim();
  if (!root) {
    return FALLBACK_JUPITER_ALLOWED;
  }
  const p = path.join(root, 'renaissance_v4', 'config', 'kitchen_policy_registry_v1.json');
  try {
    const raw = JSON.parse(fs.readFileSync(p, 'utf8'));
    const jup = raw?.runtime_policies?.jupiter;
    if (Array.isArray(jup) && jup.length > 0) {
      const ids = jup.map((x) => String(x).trim()).filter(Boolean);
      return Object.freeze(ids);
    }
  } catch {
    /* use fallback */
  }
  return FALLBACK_JUPITER_ALLOWED;
}

/** Single source for Sean/Jupiter validation and GET /api/v1/jupiter/policy (DV-070). */
export const ALLOWED_POLICY_IDS = loadJupiterAllowedPolicyIdsFromRegistry();
