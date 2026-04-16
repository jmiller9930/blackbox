#!/usr/bin/env node
/**
 * Deterministic intake evaluation for uploaded TypeScript policy (DV-ARCH-KITCHEN-POLICY-INTAKE-048).
 * Contract: bundled module exports generateSignalFromOhlc(closes, highs, lows, volumes)
 * returning { longSignal, shortSignal, signalPrice }.
 *
 * DV-063: Parent process sets RV4_POLICY_INDICATORS_JSON (canonical indicators section). The harness
 * validates structure (ids, kinds in frozen vocabulary, gate refs) and echoes policy_indicators on stdout.
 * Policies may read process.env.RV4_POLICY_INDICATORS_JSON in Node for the same declarations.
 *
 * Usage: node run_ts_intake_eval.mjs <absolute-path-to.ts> <bar_count>
 * stdout: one JSON line
 */
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import { pathToFileURL } from 'node:url';

function fail(msg, detail = {}) {
  console.log(JSON.stringify({ ok: false, error: msg, ...detail }));
}

/** Mirror renaissance_v4/policy_spec/indicators_v1.py INDICATOR_KIND_VOCABULARY (keep in sync). */
const INDICATOR_KIND_VOCABULARY = new Set([
  'ema',
  'sma',
  'rsi',
  'atr',
  'macd',
  'bollinger_bands',
  'vwap',
  'supertrend',
  'stochastic',
  'adx',
  'cci',
  'williams_r',
  'mfi',
  'obv',
  'parabolic_sar',
  'ichimoku',
  'donchian',
  'volume_filter',
  'divergence',
  'body_measurement',
  'fixed_threshold',
  'threshold_group',
]);

function summarizePolicyIndicatorsFromEnv() {
  const raw = process.env.RV4_POLICY_INDICATORS_JSON;
  if (!raw || !String(raw).trim()) {
    return {
      validated: true,
      source: 'empty_env',
      schema_version: 'policy_indicators_v1',
      declaration_count: 0,
      gate_count: 0,
      kinds: [],
    };
  }
  try {
    const o = JSON.parse(raw);
    if (!o || typeof o !== 'object') {
      return { validated: false, error: 'not_object' };
    }
    const decls = Array.isArray(o.declarations) ? o.declarations : [];
    const errs = [];
    const ids = new Set();
    for (let i = 0; i < decls.length; i++) {
      const d = decls[i];
      if (!d || typeof d !== 'object') {
        errs.push(`declarations[${i}]_not_object`);
        continue;
      }
      const id = String(d.id || '').trim();
      const kind = String(d.kind || '').trim().toLowerCase();
      if (!id) errs.push(`declarations[${i}]_missing_id`);
      else if (ids.has(id)) errs.push(`duplicate_id:${id}`);
      else ids.add(id);
      if (!kind) errs.push(`declarations[${i}]_missing_kind`);
      else if (!INDICATOR_KIND_VOCABULARY.has(kind)) errs.push(`declarations[${i}]_unknown_kind:${kind}`);
      if (d.params != null && typeof d.params !== 'object') errs.push(`declarations[${i}]_params_not_object`);
    }
    const gates = Array.isArray(o.gates) ? o.gates : [];
    for (let i = 0; i < gates.length; i++) {
      const g = gates[i];
      if (!g || typeof g !== 'object') {
        errs.push(`gates[${i}]_not_object`);
        continue;
      }
      const gid = String(g.indicator_id || '').trim();
      if (gid && !ids.has(gid)) errs.push(`gates[${i}]_unknown_indicator_id:${gid}`);
    }
    const kinds = [...new Set(decls.map((d) => String(d.kind || '').toLowerCase()).filter(Boolean))];
    return {
      validated: errs.length === 0,
      errors: errs.length ? errs : undefined,
      schema_version: o.schema_version || 'policy_indicators_v1',
      declaration_count: decls.length,
      gate_count: gates.length,
      kinds,
    };
  } catch (e) {
    return {
      validated: false,
      error: 'json_parse',
      detail: String(e && e.message ? e.message : e).slice(0, 500),
    };
  }
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

  /** Proves which harness logic ran (DV-060); integer OHLC series — not sin/float. */
  const HARNESS_REVISION = 'int_ohlc_v2';

  const out = {
    ok: true,
    harness_revision: HARNESS_REVISION,
    test_window_bars: nBars,
    min_bars_used: minBars,
    signals_long: longBars,
    signals_short: shortBars,
    signals_total: signalsTotal,
    trades_opened: tradesOpened,
    trades_closed: tradesClosed,
    pnl_summary: { realized: Number.isFinite(pnlSum) ? pnlSum : 0, currency: 'abstract' },
    policy_indicators: summarizePolicyIndicatorsFromEnv(),
  };

  if (process.env.RV4_INTAKE_HARNESS_DEBUG === '1') {
    let tsSha = '';
    try {
      tsSha = createHash('sha256').update(readFileSync(tsPath)).digest('hex');
    } catch (e) {
      tsSha = `read_error:${String(e && e.message ? e.message : e)}`;
    }
    const endProbe = Math.max(minBars, 2);
    const slP = closes.slice(0, endProbe);
    const shP = highs.slice(0, endProbe);
    const sloP = lows.slice(0, endProbe);
    const svP = vols.slice(0, endProbe);
    out.intake_debug = {
      fixture_basename: basename(tsPath),
      ts_sha256: tsSha,
      export_name:
        typeof mod.generateSignalFromOhlc === 'function' ? 'generateSignalFromOhlc' : 'default',
      ohlc_first3_close: closes.slice(0, 3),
      ohlc_last3_close: closes.slice(-3),
      probe_end_bars: endProbe,
      probe_policy_out: fn(slP, shP, sloP, svP),
    };
  }

  console.log(JSON.stringify(out));
}

main().catch((e) => {
  fail('unexpected', { detail: String(e && e.message ? e.message : e) });
});
