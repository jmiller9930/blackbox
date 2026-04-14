import assert from 'node:assert';
import { test } from 'node:test';
import { generateSignalFromOhlcV3, MIN_BARS, resolveEntrySide } from '../jupiter_3_sean_policy.mjs';
import { initialSlTp, computePnlUsd, evaluateExitOhlc } from '../sean_lifecycle.mjs';

test('initialSlTp long places SL below and TP above', () => {
  const { stopLoss, takeProfit } = initialSlTp(100, 1, 'long');
  assert.ok(stopLoss < 100);
  assert.ok(takeProfit > 100);
});

test('computePnlUsd long and short', () => {
  assert.strictEqual(computePnlUsd(100, 102, 1, 'long'), 2);
  assert.strictEqual(computePnlUsd(100, 98, 1, 'short'), 2);
});

test('evaluateExitOhlc long stop', () => {
  const ex = evaluateExitOhlc('long', 95, 110, 99, 99, 94, 96);
  assert.strictEqual(ex?.reason, 'STOP_LOSS');
});

test('generateSignalFromOhlcV3 needs history', () => {
  const short = Array(MIN_BARS - 1).fill(100);
  const r = generateSignalFromOhlcV3(short, short, short, short);
  assert.strictEqual(r.diag.reason, 'insufficient_history');
});

test('resolveEntrySide short wins when both', () => {
  assert.strictEqual(resolveEntrySide(true, true), 'short');
});
