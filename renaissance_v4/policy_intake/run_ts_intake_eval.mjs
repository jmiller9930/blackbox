#!/usr/bin/env node
/**
 * Deterministic intake evaluation for uploaded TypeScript policy (DV-ARCH-KITCHEN-POLICY-INTAKE-048).
 * Contract: bundled module exports generateSignalFromOhlc(closes, highs, lows, volumes)
 * returning { longSignal, shortSignal, signalPrice }.
 *
 * Usage: node run_ts_intake_eval.mjs <absolute-path-to.ts> <bar_count>
 * stdout: one JSON line
 */
import { spawnSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

function fail(msg, detail = {}) {
  console.log(JSON.stringify({ ok: false, error: msg, ...detail }));
}

async function main() {
  const tsPath = process.argv[2];
  const nBars = Math.max(50, Math.min(5000, parseInt(process.argv[3] || '800', 10) || 800));
  if (!tsPath) {
    fail('missing_ts_path');
    return;
  }

  const outDir = mkdtempSync(join(tmpdir(), 'rv4_intake_'));
  const outMjs = join(outDir, 'bundled.mjs');
  const r = spawnSync(
    'npx',
    ['-y', 'esbuild@0.20.2', tsPath, '--bundle', '--format=esm', '--platform=neutral', `--outfile=${outMjs}`],
    { encoding: 'utf-8', maxBuffer: 20 * 1024 * 1024, env: { ...process.env, npm_config_yes: 'true' } },
  );
  if (r.status !== 0) {
    fail('esbuild_bundle_failed', {
      stderr: ((r.stderr || '') + (r.stdout || '')).slice(0, 6000),
    });
    return;
  }

  let mod;
  try {
    mod = await import(pathToFileURL(outMjs).href);
  } catch (e) {
    fail('module_import_failed', { detail: String(e && e.message ? e.message : e).slice(0, 4000) });
    return;
  }

  const fn =
    typeof mod.generateSignalFromOhlc === 'function'
      ? mod.generateSignalFromOhlc
      : typeof mod.default === 'function'
        ? mod.default
        : null;
  if (!fn) {
    fail('missing_export_generateSignalFromOhlc', {
      hint: 'Export function generateSignalFromOhlc(closes, highs, lows, volumes)',
    });
    return;
  }

  const minBars =
    typeof mod.MIN_BARS === 'number' && Number.isFinite(mod.MIN_BARS) ? mod.MIN_BARS : 2;

  // DV-056: Deterministic OHLC identical on every host (Alpine/Linux/macOS). The previous sin-based
  // series could yield consecutive closes equal within float noise on some platforms, so policies
  // comparing c vs p never saw strict inequality → zero signals → live FAIL vs local PASS.
  const closes = [];
  const highs = [];
  const lows = [];
  const vols = [];
  for (let i = 0; i < nBars; i++) {
    const c = 100 + i;
    closes.push(c);
    highs.push(c + 1);
    lows.push(c - 1);
    vols.push(800 + (i % 40));
  }

  let longBars = 0;
  let shortBars = 0;
  for (let end = minBars; end <= nBars; end++) {
    const sl = closes.slice(0, end);
    const sh = highs.slice(0, end);
    const slo = lows.slice(0, end);
    const sv = vols.slice(0, end);
    const out = fn(sl, sh, slo, sv);
    if (out && out.longSignal) longBars++;
    if (out && out.shortSignal) shortBars++;
  }

  const signalsTotal = longBars + shortBars;

  let tradesOpened = 0;
  let tradesClosed = 0;
  let pnlSum = 0;

  let firstEnd = -1;
  let firstOut = null;
  for (let end = minBars; end <= nBars; end++) {
    const sl = closes.slice(0, end);
    const sh = highs.slice(0, end);
    const slo = lows.slice(0, end);
    const sv = vols.slice(0, end);
    const out = fn(sl, sh, slo, sv);
    if (out && (out.longSignal || out.shortSignal)) {
      firstEnd = end;
      firstOut = out;
      break;
    }
  }

  if (firstEnd >= 0 && firstOut) {
    const entryIdx = firstEnd - 1;
    const isLong = !!firstOut.longSignal && !firstOut.shortSignal;
    const isShort = !!firstOut.shortSignal && !firstOut.longSignal;
    const sideLong = isLong || (!isShort && !isLong ? firstOut.longSignal : isLong);
    const entryPx = closes[entryIdx];
    tradesOpened = 1;
    const exitIdx = Math.min(entryIdx + 1, nBars - 1);
    const exitPx = closes[exitIdx];
    tradesClosed = 1;
    const longSide = !!firstOut.longSignal && !firstOut.shortSignal;
    const shortSide = !!firstOut.shortSignal && !firstOut.longSignal;
    let side = 0;
    if (longSide) side = 1;
    else if (shortSide) side = -1;
    else side = firstOut.shortSignal ? -1 : 1;
    pnlSum = side * (exitPx - entryPx);
  }

  console.log(
    JSON.stringify({
      ok: true,
      test_window_bars: nBars,
      min_bars_used: minBars,
      signals_long: longBars,
      signals_short: shortBars,
      signals_total: signalsTotal,
      trades_opened: tradesOpened,
      trades_closed: tradesClosed,
      pnl_summary: { realized: Number.isFinite(pnlSum) ? pnlSum : 0, currency: 'abstract' },
    }),
  );
}

main().catch((e) => {
  fail('unexpected', { detail: String(e && e.message ? e.message : e) });
});
