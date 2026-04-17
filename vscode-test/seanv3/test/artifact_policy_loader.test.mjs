/**
 * Manifest content_sha256 must match evaluator.mjs bytes (Path A binding).
 */
import assert from 'node:assert';
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { test } from 'node:test';
import { join } from 'node:path';
import os from 'node:os';

import { loadEvaluatorFromManifestBinding } from '../engine/artifact_policy_loader.mjs';

test('loadEvaluatorFromManifestBinding rejects manifest_content_sha256_mismatch', async () => {
  const root = mkdtempSync(join(os.tmpdir(), 'art-loader-mismatch-'));
  const sid = 'sub_mismatch';
  const artDir = join(root, 'renaissance_v4', 'state', 'policy_intake_submissions', sid, 'artifacts');
  mkdirSync(artDir, { recursive: true });
  const src = `export function generateSignalFromOhlc() { return {}; }\n`;
  writeFileSync(join(artDir, 'evaluator.mjs'), src, 'utf8');
  const wrongHex = 'b'.repeat(64);
  const prev = process.env.BLACKBOX_REPO_ROOT;
  process.env.BLACKBOX_REPO_ROOT = root;
  try {
    const r = await loadEvaluatorFromManifestBinding(
      { submission_id: sid, content_sha256: wrongHex },
      root
    );
    assert.strictEqual(r.ok, false);
    assert.strictEqual(r.error, 'manifest_content_sha256_mismatch');
  } finally {
    if (prev === undefined) delete process.env.BLACKBOX_REPO_ROOT;
    else process.env.BLACKBOX_REPO_ROOT = prev;
    rmSync(root, { recursive: true, force: true });
  }
});

test('loadEvaluatorFromManifestBinding succeeds when manifest hash matches file', async () => {
  const root = mkdtempSync(join(os.tmpdir(), 'art-loader-ok-'));
  const sid = 'sub_ok';
  const artDir = join(root, 'renaissance_v4', 'state', 'policy_intake_submissions', sid, 'artifacts');
  mkdirSync(artDir, { recursive: true });
  const src = `export const MIN_BARS = 2;
export function generateSignalFromOhlc() { return { longSignal: false, shortSignal: false }; }
`;
  writeFileSync(join(artDir, 'evaluator.mjs'), src, 'utf8');
  const hex = createHash('sha256').update(src, 'utf8').digest('hex');
  const prev = process.env.BLACKBOX_REPO_ROOT;
  process.env.BLACKBOX_REPO_ROOT = root;
  try {
    const r = await loadEvaluatorFromManifestBinding({ submission_id: sid, content_sha256: hex }, root);
    assert.strictEqual(r.ok, true);
    assert.strictEqual(typeof r.generateEntrySignal, 'function');
  } finally {
    if (prev === undefined) delete process.env.BLACKBOX_REPO_ROOT;
    else process.env.BLACKBOX_REPO_ROOT = prev;
    rmSync(root, { recursive: true, force: true });
  }
});
