/**
 * Funding / wallet gates before opening a position — treats SeanV3 as an operator-grade stack.
 * - Wallet must be connected (wallet_status + paper_wallet row from connectWalletOnce).
 * - Paper mode: simulated equity must cover intended notional (and be > 0).
 * - Chain mode: PAPER_TRADING must be off + cached on-chain SOL above minimum.
 */
import { getMeta } from './paper_analog.mjs';
import { getPaperPosition } from './sean_ledger.mjs';

function paperStartingUsd(db) {
  try {
    const row = db.prepare(`SELECT v FROM analog_meta WHERE k = ?`).get('paper_starting_balance_usd');
    if (row?.v) {
      const v = parseFloat(String(row.v).trim());
      if (v > 0) return v;
    }
  } catch {
    /* */
  }
  const raw = (process.env.SEAN_PAPER_STARTING_BALANCE_USD || '1000').trim();
  const n = parseFloat(raw);
  return n > 0 ? n : 1000;
}

function realizedSumUsd(db) {
  try {
    const row = db.prepare(`SELECT COALESCE(SUM(gross_pnl_usd), 0) AS s FROM sean_paper_trades`).get();
    return Number(row?.s || 0);
  } catch {
    return 0;
  }
}

/** Approximate mark-to-market USD for open position (same convention as TUI ledger). */
function unrealizedUsd(db, markUsd) {
  const pos = getPaperPosition(db);
  if (!pos || pos.side === 'flat' || !Number.isFinite(markUsd)) return 0;
  const sd = String(pos.side).toLowerCase();
  const ep = pos.entry_price;
  const sz = pos.size_notional_sol;
  if (sd === 'long') return (markUsd - ep) * sz;
  if (sd === 'short') return (ep - markUsd) * sz;
  return 0;
}

export function getPaperEquityUsd(db, markUsd) {
  const starting = paperStartingUsd(db);
  const realized = realizedSumUsd(db);
  const unreal = unrealizedUsd(db, markUsd);
  return {
    starting_usd: starting,
    realized_pnl_usd: realized,
    unrealized_usd: unreal,
    equity_usd: starting + realized + unreal,
  };
}

/**
 * @param {import('node:sqlite').DatabaseSync} db
 * @param {{ markUsd: number, sizeNotionalSol: number, closePx: number }} ctx
 */
export function assertCanOpenPosition(db, ctx) {
  const markUsd = Number(ctx.markUsd);
  const closePx = Number(ctx.closePx);
  const sizeNotionalSol = Number(ctx.sizeNotionalSol);

  const ws = getMeta(db, 'wallet_status');
  if (ws !== 'connected') {
    return { ok: false, reason: 'wallet_not_connected', detail: 'Set KEYPAIR_PATH and restart seanv3 so pubkey is stored.' };
  }
  const pk = db.prepare(`SELECT pubkey_base58 FROM paper_wallet WHERE id=1`).get();
  if (!pk?.pubkey_base58) {
    return { ok: false, reason: 'no_paper_wallet_row', detail: 'paper_wallet empty' };
  }

  const mode = (getMeta(db, 'sean_funding_mode') || 'paper').trim().toLowerCase();
  const pt = (process.env.PAPER_TRADING || '1').trim().toLowerCase();
  const paperEnvOn = pt !== '0' && pt !== 'false';

  const chainMode = mode === 'chain' || mode === 'live';
  if (!chainMode) {
    if (!Number.isFinite(closePx) || closePx <= 0) {
      return { ok: false, reason: 'missing_mark', detail: 'Need a Binance close (or Hermes mark) before sizing paper risk.' };
    }
  }

  const notionalUsd = Math.max(0, sizeNotionalSol * closePx);

  if (chainMode) {
    if (paperEnvOn) {
      return {
        ok: false,
        reason: 'chain_mode_blocked',
        detail: 'Set PAPER_TRADING=0 in compose for real wallet funding; restart seanv3.',
      };
    }
    const lamRaw = getMeta(db, 'chain_sol_balance_lamports');
    const lam = parseInt(String(lamRaw || '0'), 10);
    const minLam = parseInt(process.env.SEAN_MIN_CHAIN_LAMPORTS || '1000000', 10);
    if (!Number.isFinite(lam) || lam < minLam) {
      return {
        ok: false,
        reason: 'insufficient_chain_sol',
        detail: `Cached lamports=${lam} (min ${minLam}). Fund wallet or wait for RPC cache.`,
      };
    }
    return { ok: true, reason: 'chain_ok', detail: '' };
  }

  const eq = getPaperEquityUsd(db, Number.isFinite(markUsd) ? markUsd : closePx);
  if (eq.equity_usd <= 1e-9) {
    return { ok: false, reason: 'paper_equity_zero', detail: 'Increase paper stake or realize PnL.' };
  }
  const minOrder = parseFloat(process.env.SEAN_MIN_ORDER_USD || '0.01');
  if (eq.equity_usd < minOrder) {
    return { ok: false, reason: 'paper_equity_below_min', detail: `equity ${eq.equity_usd} < min ${minOrder} USD` };
  }
  if (notionalUsd > 0 && eq.equity_usd + 1e-9 < notionalUsd) {
    return {
      ok: false,
      reason: 'paper_equity_below_notional',
      detail: `equity ${eq.equity_usd.toFixed(4)} USD < required ~${notionalUsd.toFixed(4)} USD (size×close).`,
    };
  }
  return { ok: true, reason: 'paper_ok', detail: '' };
}
