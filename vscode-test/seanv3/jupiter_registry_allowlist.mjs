/**
 * @deprecated Jupiter allowed ids come only from kitchen_policy_deployment_manifest_v1 (Jupiter entries).
 * Kept for grep/docs compatibility; re-exports manifest-based list.
 */
import { loadAllowedDeploymentIdsFromManifest } from './jupiter_policy_runtime.mjs';

export function loadJupiterAllowedPolicyIdsFromRegistry() {
  return loadAllowedDeploymentIdsFromManifest();
}

/** @deprecated Use loadAllowedDeploymentIdsFromManifest() at call time (manifest may change). */
export const ALLOWED_POLICY_IDS = loadAllowedDeploymentIdsFromManifest();
