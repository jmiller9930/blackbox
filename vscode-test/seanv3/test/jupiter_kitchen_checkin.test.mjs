/**
 * Kitchen runtime policy check-in helper (handshake after trade-surface policy change).
 */
import assert from 'node:assert';
import { test } from 'node:test';
import {
  kitchenRuntimePolicyCheckinHttp,
  tradeSurfacePolicyKitchenHandshake,
} from '../jupiter_kitchen_checkin.mjs';

test('kitchenRuntimePolicyCheckinHttp skips when base or token missing', async () => {
  const r = await kitchenRuntimePolicyCheckinHttp({
    baseUrl: '',
    token: 't',
    activePolicy: 'jup_v4',
  });
  assert.strictEqual(r.skipped, true);
  assert.strictEqual(r.ok, false);
});

test('kitchenRuntimePolicyCheckinHttp POSTs and parses success', async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: true,
      status: 200,
      json: async () => ({
        ok: true,
        schema: 'runtime_policy_checkin_result_v1',
        reconcile_linkage: 'candidate_rebound',
      }),
    };
  };
  const r = await kitchenRuntimePolicyCheckinHttp({
    baseUrl: 'https://bb.example',
    token: 'secret',
    activePolicy: 'jup_v4',
    fetchImpl,
  });
  assert.strictEqual(r.ok, true);
  assert.strictEqual(calls.length, 1);
  assert.match(calls[0].url, /runtime-policy-checkin$/);
  assert.ok(String(calls[0].init.headers.Authorization).includes('secret'));
});

test('kitchenRuntimePolicyCheckinHttp POSTs standby (empty activePolicy)', async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    const body = JSON.parse(String(init.body));
    assert.strictEqual(body.active_policy, '');
    return {
      ok: true,
      status: 200,
      json: async () => ({ ok: true, schema: 'runtime_policy_checkin_result_v1' }),
    };
  };
  const r = await kitchenRuntimePolicyCheckinHttp({
    baseUrl: 'https://bb.example',
    token: 'secret',
    activePolicy: '',
    fetchImpl,
  });
  assert.strictEqual(r.ok, true);
  assert.strictEqual(calls.length, 1);
});

test('tradeSurfacePolicyKitchenHandshake relaxed: failed check-in keeps warning', async () => {
  const fetchImpl = async () => ({
    ok: false,
    status: 401,
    json: async () => ({ ok: false, error: 'unauthorized' }),
  });
  const r = await tradeSurfacePolicyKitchenHandshake({
    beforePolicyId: 'a',
    afterPolicyId: 'b',
    env: {
      JUPITER_KITCHEN_CHECKIN_BASE: 'https://x',
      JUPITER_KITCHEN_CHECKIN_TOKEN: 't',
      JUPITER_REQUIRE_KITCHEN_ACK: '',
    },
    fetchImpl,
  });
  assert.strictEqual(r.strictBlocked, false);
  assert.ok(r.kitchen_checkin_warning);
  assert.strictEqual(r.kitchen_checkin.ok, false);
});

test('tradeSurfacePolicyKitchenHandshake strict: failed check-in blocks', async () => {
  const fetchImpl = async () => ({
    ok: false,
    status: 502,
    json: async () => ({ ok: false, error: 'runtime_unreachable' }),
  });
  const r = await tradeSurfacePolicyKitchenHandshake({
    beforePolicyId: 'a',
    afterPolicyId: 'b',
    env: {
      JUPITER_KITCHEN_CHECKIN_BASE: 'https://x',
      JUPITER_KITCHEN_CHECKIN_TOKEN: 't',
      JUPITER_REQUIRE_KITCHEN_ACK: '1',
    },
    fetchImpl,
  });
  assert.strictEqual(r.strictBlocked, true);
});

test('tradeSurfacePolicyKitchenHandshake strict: transport exception still blocks', async () => {
  const fetchImpl = async () => {
    throw new Error('connect ECONNREFUSED 127.0.0.1:8080');
  };
  const r = await tradeSurfacePolicyKitchenHandshake({
    beforePolicyId: 'a',
    afterPolicyId: 'b',
    env: {
      JUPITER_KITCHEN_CHECKIN_BASE: 'https://x',
      JUPITER_KITCHEN_CHECKIN_TOKEN: 't',
      JUPITER_REQUIRE_KITCHEN_ACK: '1',
    },
    fetchImpl,
  });
  assert.strictEqual(r.strictBlocked, true);
  assert.strictEqual(r.kitchen_checkin.ok, false);
  assert.match(String(r.detail || ''), /ECONNREFUSED/);
});

test('tradeSurfacePolicyKitchenHandshake relaxed: transport exception becomes warning', async () => {
  const fetchImpl = async () => {
    throw new Error('socket hang up');
  };
  const r = await tradeSurfacePolicyKitchenHandshake({
    beforePolicyId: 'a',
    afterPolicyId: 'b',
    env: {
      JUPITER_KITCHEN_CHECKIN_BASE: 'https://x',
      JUPITER_KITCHEN_CHECKIN_TOKEN: 't',
      JUPITER_REQUIRE_KITCHEN_ACK: '',
    },
    fetchImpl,
  });
  assert.strictEqual(r.strictBlocked, false);
  assert.strictEqual(r.kitchen_checkin.ok, false);
  assert.ok(r.kitchen_checkin_warning);
  assert.match(String(r.kitchen_checkin_warning), /socket hang up/);
});

test('tradeSurfacePolicyKitchenHandshake strict: missing env blocks', async () => {
  const r = await tradeSurfacePolicyKitchenHandshake({
    beforePolicyId: 'a',
    afterPolicyId: 'b',
    env: { JUPITER_REQUIRE_KITCHEN_ACK: '1' },
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ ok: true }) }),
  });
  assert.strictEqual(r.strictBlocked, true);
});

test('tradeSurfacePolicyKitchenHandshake relaxed: missing env only warns', async () => {
  const r = await tradeSurfacePolicyKitchenHandshake({
    beforePolicyId: 'a',
    afterPolicyId: 'b',
    env: {},
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ ok: true }) }),
  });
  assert.strictEqual(r.strictBlocked, false);
  assert.strictEqual(r.kitchen_checkin.skipped, true);
});
