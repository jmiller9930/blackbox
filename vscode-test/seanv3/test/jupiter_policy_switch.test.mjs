/**
 * Deployment ids — same gate as POST /api/v1/jupiter/active-policy (manifest Jupiter entries).
 */
import assert from 'node:assert';
import { mkdirSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import os from 'os';
import { test } from 'node:test';
import { isDeploymentIdInManifest } from '../jupiter_policy_runtime.mjs';

function writeManifest(repo, ids) {
  const entries = ids.map((deployed_runtime_policy_id) => ({
    execution_target: 'jupiter',
    deployed_runtime_policy_id,
    submission_id: 's_' + deployed_runtime_policy_id,
    content_sha256: 'a'.repeat(64),
  }));
  const p = join(repo, 'renaissance_v4', 'config', 'kitchen_policy_deployment_manifest_v1.json');
  writeFileSync(
    p,
    JSON.stringify({ schema: 'kitchen_policy_deployment_manifest_v1', entries }, null, 2),
    'utf8'
  );
}

test('isDeploymentIdInManifest accepts manifest deployment ids', () => {
  const prev = process.env.BLACKBOX_REPO_ROOT;
  const repo = mkdtempSync(join(os.tmpdir(), 'jup-manifest-'));
  process.env.BLACKBOX_REPO_ROOT = repo;
  try {
    mkdirSync(join(repo, 'renaissance_v4', 'config'), { recursive: true });
    writeManifest(repo, ['dep_a', 'dep_b']);
    assert.strictEqual(isDeploymentIdInManifest('dep_a'), true);
    assert.strictEqual(isDeploymentIdInManifest('dep_b'), true);
  } finally {
    if (prev === undefined) delete process.env.BLACKBOX_REPO_ROOT;
    else process.env.BLACKBOX_REPO_ROOT = prev;
    rmSync(repo, { recursive: true, force: true });
  }
});

test('isDeploymentIdInManifest rejects unknown or empty', () => {
  const prev = process.env.BLACKBOX_REPO_ROOT;
  const repo = mkdtempSync(join(os.tmpdir(), 'jup-manifest-'));
  process.env.BLACKBOX_REPO_ROOT = repo;
  try {
    mkdirSync(join(repo, 'renaissance_v4', 'config'), { recursive: true });
    writeManifest(repo, ['only_one']);
    assert.strictEqual(isDeploymentIdInManifest(''), false);
    assert.strictEqual(isDeploymentIdInManifest('not_in_manifest'), false);
  } finally {
    if (prev === undefined) delete process.env.BLACKBOX_REPO_ROOT;
    else process.env.BLACKBOX_REPO_ROOT = prev;
    rmSync(repo, { recursive: true, force: true });
  }
});
