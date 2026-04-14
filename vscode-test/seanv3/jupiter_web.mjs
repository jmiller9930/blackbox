#!/usr/bin/env node
/**
 * Jupiter — read-only web UI for SeanV3 parity data (wallet, position, trades from sean_parity.db).
 * Default port 707 (JUPITER_WEB_PORT or legacy SEANV3_WEB_PORT). Host networking recommended.
 * On Linux, ports <1024 need root or NET_BIND_SERVICE — docker-compose runs jupiter-web as root for :707 only.
 * Lab: http://clawbot.a51.corp:707/ (operator browser on LAN/VPN).
 */
import http from 'http';
import { DatabaseSync } from 'node:sqlite';
import { resolve } from 'path';
import { fileURLToPath } from 'url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

function dbPath() {
  const env = (process.env.SQLITE_PATH || process.env.SEAN_SQLITE_PATH || '').trim();
  if (env) return resolve(env);
  return resolve(__dirname, 'capture', 'sean_parity.db');
}

function esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function buildSummary(db) {
  const out = {
    schema: 'jupiter_web_summary_v1',
    application: 'Jupiter',
    sqlite_path: dbPath(),
    wallet: null,
    wallet_status: null,
    position: null,
    recent_trades: [],
    last_kline: null,
    error: null,
  };

  try {
    const st = db.prepare(`SELECT v FROM analog_meta WHERE k = 'wallet_status'`).get();
    if (st?.v) out.wallet_status = String(st.v);
  } catch {
    /* */
  }

  try {
    const w = db.prepare(`SELECT pubkey_base58, keypair_path FROM paper_wallet WHERE id=1`).get();
    if (w?.pubkey_base58) {
      out.wallet = {
        pubkey_base58: String(w.pubkey_base58),
        keypair_path_suffix: w.keypair_path ? String(w.keypair_path).slice(-48) : null,
      };
    }
  } catch {
    /* */
  }

  try {
    const p = db
      .prepare(
        `SELECT side, entry_price, size_notional_sol, entry_market_event_id, opened_at_utc, bars_held
         FROM sean_paper_position WHERE id=1`
      )
      .get();
    if (p) {
      out.position = {
        side: p.side != null ? String(p.side) : null,
        entry_price: p.entry_price,
        size_notional_sol: p.size_notional_sol,
        entry_market_event_id: p.entry_market_event_id != null ? String(p.entry_market_event_id) : null,
        opened_at_utc: p.opened_at_utc != null ? String(p.opened_at_utc) : null,
        bars_held: p.bars_held,
      };
    }
  } catch {
    /* */
  }

  try {
    const rows = db
      .prepare(
        `SELECT id, side, entry_time_utc, exit_time_utc, gross_pnl_usd, result_class, entry_market_event_id
         FROM sean_paper_trades ORDER BY id DESC LIMIT 15`
      )
      .all();
    out.recent_trades = rows.map((r) => ({
      id: r.id,
      side: r.side != null ? String(r.side) : null,
      entry_time_utc: r.entry_time_utc != null ? String(r.entry_time_utc) : null,
      exit_time_utc: r.exit_time_utc != null ? String(r.exit_time_utc) : null,
      gross_pnl_usd: r.gross_pnl_usd,
      result_class: r.result_class != null ? String(r.result_class) : null,
      entry_market_event_id:
        r.entry_market_event_id != null ? String(r.entry_market_event_id) : null,
    }));
  } catch {
    /* */
  }

  try {
    const k = db
      .prepare(
        `SELECT market_event_id, close_px, polled_at_utc FROM sean_binance_kline_poll
         ORDER BY id DESC LIMIT 1`
      )
      .get();
    if (k) {
      out.last_kline = {
        market_event_id: k.market_event_id != null ? String(k.market_event_id) : null,
        close_px: k.close_px,
        polled_at_utc: k.polled_at_utc != null ? String(k.polled_at_utc) : null,
      };
    }
  } catch {
    /* */
  }

  return out;
}

function htmlPage(data) {
  const w = data.wallet;
  const pos = data.position;
  const trades = data.recent_trades || [];
  const kl = data.last_kline;

  const errBlock = data.error
    ? `<p class="warn">SQLite: ${esc(data.error)}</p>`
    : '';

  const walletBlock = w
    ? `<p><strong>Pubkey</strong><br><code>${esc(w.pubkey_base58)}</code></p>
       <p class="muted">status: ${esc(data.wallet_status || '—')}</p>`
    : '<p class="warn">No wallet row in <code>paper_wallet</code> — set <code>KEYPAIR_PATH</code> and restart <code>seanv3</code>.</p>';

  const posBlock =
    pos && String(pos.side) !== 'flat'
      ? `<p><strong>Open</strong> ${esc(pos.side)} @ ${esc(pos.entry_price)} · mid ${esc(pos.entry_market_event_id)}</p>`
      : '<p class="muted">Position: flat</p>';

  const rows = trades
    .map(
      (t) =>
        `<tr><td>${esc(t.id)}</td><td>${esc(t.side)}</td><td>${esc(t.exit_time_utc)}</td><td>${esc(t.gross_pnl_usd)}</td><td>${esc(t.result_class)}</td></tr>`
    )
    .join('');

  const klBlock = kl
    ? `<p class="muted">Last kline poll: ${esc(kl.market_event_id)} · close ${esc(kl.close_px)} · ${esc(kl.polled_at_utc)}</p>`
    : '';

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Jupiter</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: ui-monospace, "Cascadia Code", "SF Mono", Menlo, Consolas, monospace;
      background: #0c0c0c;
      color: #e6edf3;
      margin: 0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 1.5rem 1rem 2rem;
    }
    .wrap {
      width: 100%;
      max-width: 88ch;
    }
    .panel {
      border: 1px solid #3d3d3d;
      border-radius: 2px;
      padding: 0.75rem 1rem;
      margin-bottom: 0.75rem;
      background: #121212;
    }
    .panel h2 {
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #8b949e;
      margin: 0 0 0.5rem 0;
      border-bottom: 1px solid #30363d;
      padding-bottom: 0.35rem;
    }
    h1 { font-size: 1.1rem; margin: 0 0 0.35rem 0; font-weight: 600; }
    .tagline { margin: 0 0 0.25rem 0; }
    code { background: #1e1e1e; padding: 0.1rem 0.35rem; border: 1px solid #333; word-break: break-all; }
    table { border-collapse: collapse; width: 100%; font-size: 0.8rem; }
    th, td { border: 1px solid #30363d; padding: 0.35rem 0.5rem; text-align: left; }
    th { background: #161b22; }
    .muted { color: #8b949e; font-size: 0.88rem; }
    .warn { color: #d29922; }
    a { color: #58a6ff; }
    footer.links { margin-top: 0.5rem; }
    p { margin: 0.35rem 0; }
    p:first-child { margin-top: 0; }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="panel">
      <h1>Jupiter — read-only</h1>
      <p class="muted tagline">SeanV3 parity data (same SQLite as TUI) — not a terminal emulator.</p>
      <p class="muted">${esc(data.sqlite_path)}</p>
    </section>
    ${errBlock ? `<section class="panel">${errBlock}</section>` : ''}
    <section class="panel">
      <h2>Wallet</h2>
      ${walletBlock}
    </section>
    <section class="panel">
      <h2>Position &amp; last kline</h2>
      ${posBlock}
      ${klBlock}
    </section>
    <section class="panel">
      <h2>Recent closed trades</h2>
      <table>
        <thead><tr><th>id</th><th>side</th><th>exit UTC</th><th>PnL USD</th><th>result</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="5" class="muted">No rows</td></tr>'}</tbody>
      </table>
    </section>
    <p class="muted links footer"><a href="/api/summary.json">summary.json</a> · <a href="/health">health</a></p>
  </div>
</body>
</html>`;
}

const portRaw = process.env.JUPITER_WEB_PORT || process.env.SEANV3_WEB_PORT || '707';
const port = Math.max(1, Math.min(65535, parseInt(portRaw, 10) || 707));
const bind = (process.env.JUPITER_WEB_BIND || process.env.SEANV3_WEB_BIND || '0.0.0.0').trim() || '0.0.0.0';

const server = http.createServer((req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);

  if (url.pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(
      JSON.stringify({
        ok: true,
        schema: 'jupiter_web_health_v1',
        application: 'Jupiter',
        port,
        bind,
      })
    );
    return;
  }

  let summary = {
    schema: 'jupiter_web_summary_v1',
    application: 'Jupiter',
    sqlite_path: dbPath(),
    wallet: null,
    wallet_status: null,
    position: null,
    recent_trades: [],
    last_kline: null,
    error: null,
  };

  let db;
  try {
    db = new DatabaseSync(dbPath(), { readOnly: true });
  } catch (e) {
    summary.error = e instanceof Error ? e.message : String(e);
  }

  if (db) {
    try {
      summary = buildSummary(db);
    } catch (e) {
      summary.error = e instanceof Error ? e.message : String(e);
    } finally {
      try {
        db.close();
      } catch {
        /* */
      }
    }
  }

  if (url.pathname === '/api/summary.json') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(JSON.stringify(summary, null, 2));
    return;
  }

  if (url.pathname === '/' || url.pathname === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(htmlPage(summary));
    return;
  }

  res.writeHead(404, { 'Content-Type': 'text/plain' });
  res.end('not found');
});

server.listen(port, bind, () => {
  console.error(`[jupiter] http://${bind}:${port}/  (read-only)`);
});
