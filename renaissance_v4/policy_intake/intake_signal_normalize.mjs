/**
 * Kitchen intake deterministic signal shape normalization (DV-065).
 * Used by run_ts_intake_eval.mjs for counting; safe to import without side effects.
 */

/**
 * Map policy return value to booleans for intake counting.
 * Primary contract: { longSignal, shortSignal, signalPrice }.
 * Also accepts: long/short aliases, nested signal.{...}, direction string, numeric side.
 */
export function normalizeIntakeSignalOutput(raw) {
  if (raw == null || typeof raw !== 'object') {
    return { longSignal: false, shortSignal: false, _norm_source: 'non_object' };
  }
  let L = !!raw.longSignal;
  let S = !!raw.shortSignal;
  let src = 'legacy_longSignal_shortSignal';
  if (!L && !S) {
    if (typeof raw.long === 'boolean' || typeof raw.short === 'boolean') {
      L = !!raw.long;
      S = !!raw.short;
      src = 'alias_long_short';
    }
  }
  if (!L && !S && raw.signal && typeof raw.signal === 'object') {
    const g = raw.signal;
    L = !!(g.longSignal || g.long);
    S = !!(g.shortSignal || g.short);
    const gd = String(g.direction || g.side || '').toLowerCase();
    if (gd === 'long' || gd === 'buy') L = true;
    if (gd === 'short' || gd === 'sell') S = true;
    if (L || S) src = 'nested_signal';
  }
  if (!L && !S) {
    const d = String(raw.direction || '').toLowerCase();
    if (d === 'long' || d === 'buy') {
      L = true;
      src = 'direction_top';
    } else if (d === 'short' || d === 'sell') {
      S = true;
      src = 'direction_top';
    }
  }
  if (!L && !S && typeof raw.side === 'number' && Number.isFinite(raw.side)) {
    if (raw.side > 0) {
      L = true;
      src = 'side_number';
    } else if (raw.side < 0) {
      S = true;
      src = 'side_number';
    }
  }
  return { longSignal: L, shortSignal: S, _norm_source: src };
}

export function makeSignalProbe(end, raw, norm) {
  const keys = raw && typeof raw === 'object' ? Object.keys(raw).slice(0, 24) : [];
  return {
    end,
    normalized: {
      longSignal: norm.longSignal,
      shortSignal: norm.shortSignal,
      source: norm._norm_source,
    },
    raw_keys: keys,
    raw_longSignal: raw && typeof raw === 'object' ? raw.longSignal : undefined,
    raw_shortSignal: raw && typeof raw === 'object' ? raw.shortSignal : undefined,
    raw_long: raw && typeof raw === 'object' ? raw.long : undefined,
    raw_short: raw && typeof raw === 'object' ? raw.short : undefined,
  };
}
