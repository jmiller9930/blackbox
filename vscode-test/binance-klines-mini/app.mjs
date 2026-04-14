/**
 * Minimal Binance klines poller for Docker on hosts with split-tunnel egress
 * (e.g. WireGuard AllowedIPs → Binance only). Uses host routing; no VPN inside the container.
 *
 * Optional NDJSON capture for parity vs blackbox ingest (join on kline.openTime / closeTime):
 *   CAPTURE_PATH=/capture/binance_klines.ndjson
 */
import { appendFile, mkdir } from 'fs/promises';
import { dirname } from 'path';

const url =
  process.env.BINANCE_KLINES_URL ||
  'https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=5m&limit=1';
const intervalMs = Math.max(
  5_000,
  parseInt(process.env.POLL_INTERVAL_MS || '300000', 10)
);
const capturePath = (process.env.CAPTURE_PATH || '').trim();

function summarizeKline(row) {
  if (!Array.isArray(row) || row.length < 7) return row;
  return {
    openTime: row[0],
    open: row[1],
    high: row[2],
    low: row[3],
    close: row[4],
    volume: row[5],
    closeTime: row[6],
  };
}

async function appendNdjsonLine(obj) {
  if (!capturePath) return;
  await mkdir(dirname(capturePath), { recursive: true });
  await appendFile(
    capturePath,
    JSON.stringify({ source: 'binance_klines_mini', ...obj }) + '\n',
    'utf8'
  );
}

async function fetchOnce() {
  const t0 = Date.now();
  const res = await fetch(url, {
    headers: { Accept: 'application/json' },
  });
  const latencyMs = Date.now() - t0;
  const bodyText = await res.text();
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${bodyText.slice(0, 200)}`);
  }
  let data;
  try {
    data = JSON.parse(bodyText);
  } catch {
    throw new Error(`Invalid JSON: ${bodyText.slice(0, 120)}`);
  }
  const kline = Array.isArray(data) && data.length ? summarizeKline(data[0]) : data;
  const record = {
    ok: true,
    at: new Date().toISOString(),
    latencyMs,
    url,
    kline,
  };
  const line = JSON.stringify(record);
  console.log(line);
  await appendNdjsonLine(record);
}

async function main() {
  console.error(
    `[binance-klines-mini] poll every ${intervalMs}ms — ${url}` +
      (capturePath ? ` — capture: ${capturePath}` : '')
  );
  for (;;) {
    try {
      await fetchOnce();
    } catch (err) {
      const record = {
        ok: false,
        at: new Date().toISOString(),
        error: err instanceof Error ? err.message : String(err),
      };
      console.error(JSON.stringify(record));
      await appendNdjsonLine(record);
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
