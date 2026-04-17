/**
 * Jupiter deployment identity + artifact loader — no bundled policy modules.
 *
 * Active key: analog_meta.jupiter_active_policy = deployment id (matches
 * kitchen_policy_deployment_manifest_v1.entries[].deployed_runtime_policy_id for Jupiter).
 *
 * Execution: engine/artifact_policy_loader.mjs loads evaluator.mjs from submission artifacts.
 * @see docs/architect/engine_policy_demarcation_v1.md
 */
import fs from 'node:fs';
import path from 'node:path';
import { loadEvaluatorFromManifestBinding } from './engine/artifact_policy_loader.mjs';

export const JUPITER_ACTIVE_POLICY_KEY = 'jupiter_active_policy';

const MANIFEST_SCHEMA = 'kitchen_policy_deployment_manifest_v1';

function repoRoot() {
  return (process.env.BLACKBOX_REPO_ROOT || '').trim();
}

/**
 * @returns {{ schema: string, entries: Array<Record<string, unknown>> }}
 */
export function loadKitchenDeploymentManifest() {
  const root = repoRoot();
  if (!root) {
    return { schema: MANIFEST_SCHEMA, entries: [] };
  }
  const p = path.join(root, 'renaissance_v4', 'config', 'kitchen_policy_deployment_manifest_v1.json');
  try {
    const raw = JSON.parse(fs.readFileSync(p, 'utf8'));
    if (raw?.schema === MANIFEST_SCHEMA && Array.isArray(raw.entries)) {
      return raw;
    }
  } catch {
    /* missing */
  }
  return { schema: MANIFEST_SCHEMA, entries: [] };
}

/**
 * Deployment ids approved for Jupiter (manifest only — no registry fallback).
 * @returns {string[]}
 */
export function loadAllowedDeploymentIdsFromManifest() {
  const m = loadKitchenDeploymentManifest();
  const out = [];
  for (const e of m.entries || []) {
    if (!e || typeof e !== 'object') continue;
    if (String(e.execution_target || '').toLowerCase() !== 'jupiter') continue;
    const id = String(e.deployed_runtime_policy_id || '').trim();
    if (id && !out.includes(id)) out.push(id);
  }
  return out;
}

/**
 * @param {string} deploymentId
 * @returns {{ submission_id: string, content_sha256: string } | null}
 */
export function manifestBindingForJupiterPolicy(deploymentId) {
  const pid = String(deploymentId || '').trim();
  if (!pid) return null;
  const m = loadKitchenDeploymentManifest();
  const e = m.entries.find(
    (x) =>
      x &&
      String(x.execution_target || '').toLowerCase() === 'jupiter' &&
      String(x.deployed_runtime_policy_id || '').trim() === pid
  );
  if (!e) return null;
  return {
    submission_id: String(e.submission_id || ''),
    content_sha256: String(e.content_sha256 || ''),
  };
}

/**
 * @param {string} raw
 */
export function isDeploymentIdInManifest(raw) {
  const id = String(raw || '').trim();
  if (!id) return false;
  return loadAllowedDeploymentIdsFromManifest().includes(id);
}

/**
 * Explicit execution only: deployment id comes solely from analog_meta.jupiter_active_policy.
 * No SEAN_JUPITER_POLICY fallback — empty or missing row means standby (engine does not execute a default policy).
 * @param {import('node:sqlite').DatabaseSync} db
 */
export function getJupiterActivePolicyId(db) {
  const row = db.prepare(`SELECT v FROM analog_meta WHERE k = ?`).get(JUPITER_ACTIVE_POLICY_KEY);
  if (row === undefined) {
    return '';
  }
  return String(row.v ?? '').trim();
}

/**
 * Sync snapshot for observability (no dynamic import).
 * @param {import('node:sqlite').DatabaseSync} db
 */
export function getActiveDeploymentSnapshot(db) {
  const row = db.prepare(`SELECT v FROM analog_meta WHERE k = ?`).get(JUPITER_ACTIVE_POLICY_KEY);
  const deploymentId = getJupiterActivePolicyId(db);
  const manifestBinding = deploymentId ? manifestBindingForJupiterPolicy(deploymentId) : null;
  const source =
    row === undefined ? 'unset' : deploymentId ? 'runtime_config' : 'runtime_config_standby';
  return {
    policyId: deploymentId || '',
    source,
    manifestBinding,
  };
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 */
export async function loadActivePolicyContext(db) {
  const deploymentId = getJupiterActivePolicyId(db);
  if (!deploymentId) {
    return {
      ok: false,
      error: 'no_active_deployment',
      detail:
        'Standby: no active deployment. Set via POST /api/v1/jupiter/active-policy with a manifest deployment id, or clear with {"policy":""}.',
    };
  }
  if (!isDeploymentIdInManifest(deploymentId)) {
    return {
      ok: false,
      error: 'deployment_not_in_manifest',
      detail: `Deployment id ${JSON.stringify(deploymentId)} is not listed in kitchen_policy_deployment_manifest_v1 for Jupiter.`,
      deploymentId,
    };
  }
  const manifestBinding = manifestBindingForJupiterPolicy(deploymentId);
  if (!manifestBinding?.submission_id) {
    return { ok: false, error: 'manifest_binding_incomplete', deploymentId };
  }
  const loaded = await loadEvaluatorFromManifestBinding(manifestBinding, repoRoot());
  if (!loaded.ok) {
    return { ...loaded, deploymentId, manifestBinding };
  }
  return {
    ok: true,
    policyId: deploymentId,
    source: 'artifact',
    deploymentId,
    manifestBinding,
    minBars: loaded.minBars,
    generateEntrySignal: loaded.generateEntrySignal,
    resolveEntrySide: loaded.resolveEntrySide,
    engineId: 'sean_artifact_engine_v1',
    policyEngineTag: loaded.policyEngineTag,
  };
}

/** @deprecated Use isDeploymentIdInManifest */
export function isPolicyIdInAllowedSwitchSet(raw) {
  return isDeploymentIdInManifest(raw);
}
