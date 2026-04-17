/**
 * Regression guard: engine hot path must never import quarantined legacy policy modules.
 * @see docs/architect/engine_policy_demarcation_v1.md
 */
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SEANV3_ROOT = join(__dirname, '..');

/** Files that implement the engine + policy resolution boundary — must stay free of legacy_policies. */
const GUARDED_RELATIVE = [
  'app.mjs',
  'sean_engine.mjs',
  'jupiter_policy_runtime.mjs',
  'sean_lifecycle.mjs',
  'engine/artifact_policy_loader.mjs',
  'engine/atr_math.mjs',
];

/** Import path must never pull from the quarantined strategy directory. */
const FORBIDDEN_SNIPPETS = [
  { re: /from\s+['"][^'"]*legacy_policies/, msg: 'must not import from legacy_policies/' },
  { re: /import\s*\(\s*['"][^'"]*legacy_policies/, msg: 'must not dynamic-import legacy_policies/' },
];

test('engine hot-path files do not import or reference legacy_policies', () => {
  for (const rel of GUARDED_RELATIVE) {
    const abs = join(SEANV3_ROOT, rel);
    const src = readFileSync(abs, 'utf8');
    for (const { re, msg } of FORBIDDEN_SNIPPETS) {
      assert.ok(!re.test(src), `${rel}: ${msg}`);
    }
  }
});
