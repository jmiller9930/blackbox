/**
 * Loader layer — DV-ARCH-ENGINE-EXTRACTION: resolves Kitchen deployment identity to an executable policy.
 * Engine never imports bundled strategy modules; it only receives functions returned here.
 *
 * Artifact layout (Kitchen / CI):
 *   ${BLACKBOX_REPO_ROOT}/renaissance_v4/state/policy_intake_submissions/<submission_id>/artifacts/evaluator.mjs
 * Optional integrity:
 *   .../artifacts/evaluator.sha256  (single line hex = sha256 of evaluator.mjs bytes)
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

/** @param {string} repoRoot */
export function evaluatorArtifactPaths(repoRoot, submissionId) {
  const base = path.join(
    repoRoot,
    'renaissance_v4',
    'state',
    'policy_intake_submissions',
    String(submissionId).trim(),
    'artifacts'
  );
  const evaluatorMjs = path.join(base, 'evaluator.mjs');
  const evaluatorSha = path.join(base, 'evaluator.sha256');
  return { base, evaluatorMjs, evaluatorSha };
}

function sha256File(filePath) {
  const buf = fs.readFileSync(filePath);
  return crypto.createHash('sha256').update(buf).digest('hex');
}

/**
 * @param {{ submission_id: string, content_sha256?: string }} binding
 * @param {string} repoRoot
 * @returns {Promise<{ ok: true, generateEntrySignal: Function, resolveEntrySide: Function, minBars: number, policyEngineTag: string } | { ok: false, error: string, detail?: string }>}
 */
export async function loadEvaluatorFromManifestBinding(binding, repoRoot) {
  const sid = String(binding?.submission_id || '').trim();
  if (!sid) {
    return { ok: false, error: 'missing_submission_id' };
  }
  const root = String(repoRoot || '').trim();
  if (!root) {
    return { ok: false, error: 'blackbox_repo_root_unset', detail: 'Set BLACKBOX_REPO_ROOT to the BlackBox repo mount.' };
  }
  const { evaluatorMjs, evaluatorSha } = evaluatorArtifactPaths(root, sid);
  if (!fs.existsSync(evaluatorMjs)) {
    return {
      ok: false,
      error: 'policy_artifact_missing',
      detail: `Expected Kitchen-built evaluator at ${evaluatorMjs}`,
    };
  }
  const strict = ['1', 'true', 'yes'].includes(String(process.env.SEAN_REQUIRE_ARTIFACT_SHA256 || '').trim().toLowerCase());
  if (fs.existsSync(evaluatorSha)) {
    const expected = fs.readFileSync(evaluatorSha, 'utf8').trim().split(/\s+/)[0]?.toLowerCase();
    const actual = sha256File(evaluatorMjs);
    if (expected && expected.length === 64 && expected !== actual) {
      return { ok: false, error: 'artifact_sha256_mismatch', detail: `evaluator.mjs hash ${actual} !== ${evaluatorSha}` };
    }
  } else if (strict) {
    return { ok: false, error: 'artifact_sha256_required', detail: `Missing ${evaluatorSha} (SEAN_REQUIRE_ARTIFACT_SHA256=1)` };
  }

  let mod;
  try {
    mod = await import(pathToFileURL(evaluatorMjs).href);
  } catch (e) {
    return {
      ok: false,
      error: 'artifact_import_failed',
      detail: e instanceof Error ? e.message : String(e),
    };
  }

  const evaluate = mod.evaluate;
  const gen = mod.generateSignalFromOhlc;
  if (typeof evaluate !== 'function' && typeof gen !== 'function') {
    return {
      ok: false,
      error: 'artifact_missing_export',
      detail: 'evaluator.mjs must export evaluate(marketState) or generateSignalFromOhlc(closes,highs,lows,vols).',
    };
  }

  const minBars = Math.max(1, Math.floor(Number(mod.MIN_BARS ?? mod.minBars ?? 2)));
  const policyEngineTag = String(mod.POLICY_ENGINE_TAG ?? mod.policyEngineTag ?? 'kitchen_artifact_v1');

  let resolveEntrySide = mod.resolveEntrySide;
  if (typeof resolveEntrySide !== 'function') {
    resolveEntrySide = (shortSignal, longSignal) => {
      if (longSignal && !shortSignal) return 'long';
      if (shortSignal && !longSignal) return 'short';
      return null;
    };
  }

  /** @type {(c: number[], h: number[], l: number[], v: number[]) => Promise<unknown>|unknown} */
  async function generateEntrySignal(closes, highs, lows, vols) {
    if (typeof gen === 'function') {
      return gen(closes, highs, lows, vols);
    }
    const marketState = {
      closes,
      highs,
      lows,
      volumes: vols,
      symbol: (process.env.SEANV3_CANONICAL_SYMBOL || process.env.CANONICAL_SYMBOL || 'SOL-PERP').trim(),
    };
    return evaluate(marketState);
  }

  return {
    ok: true,
    generateEntrySignal,
    resolveEntrySide,
    minBars,
    policyEngineTag,
  };
}
