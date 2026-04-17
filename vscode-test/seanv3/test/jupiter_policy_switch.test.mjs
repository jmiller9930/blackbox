/**
 * Policy switch allowlist — same gate as POST /api/v1/jupiter/active-policy (DV-070).
 */
import assert from 'node:assert';
import { test } from 'node:test';
import { isPolicyIdInAllowedSwitchSet } from '../jupiter_policy_runtime.mjs';

test('isPolicyIdInAllowedSwitchSet accepts registry ids', () => {
  assert.strictEqual(isPolicyIdInAllowedSwitchSet('jup_v4'), true);
  assert.strictEqual(isPolicyIdInAllowedSwitchSet('jup_kitchen_mechanical_v1'), true);
});

test('isPolicyIdInAllowedSwitchSet rejects unknown or empty', () => {
  assert.strictEqual(isPolicyIdInAllowedSwitchSet(''), false);
  assert.strictEqual(isPolicyIdInAllowedSwitchSet('not_a_real_policy'), false);
});
