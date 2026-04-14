#!/usr/bin/env node
/**
 * Hermes Pyth SSE — same feed id as trading_core/drift_trading_bot_source.ts (SOL/USD).
 * No Drift; proves inbound oracle stream for a wall duration.
 * Usage: node basetrade/pyth_signal_probe.mjs [seconds]
 * Default 1800 (30m). Requires: npm install in basetrade/
 */
import EventSource from "eventsource";

const FEED =
  "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d";
const HERMES_ORIGIN = (
  process.env.PYTH_HERMES_BASE_URL ||
  process.env.HERMES_PYTH_BASE_URL ||
  "https://hermes.pyth.network"
)
  .trim()
  .replace(/\/$/, "");
const URL = `${HERMES_ORIGIN}/v2/updates/price/stream?ids[]=${FEED}`;
const durationSec = Math.max(5, parseInt(process.argv[2] || "1800", 10) || 1800);

let messages = 0;
let errors = 0;
const started = Date.now();

const es = new EventSource(URL);
es.addEventListener("open", () => {
  console.log(`[pyth_signal_probe] SSE open  feed=${FEED}  duration_sec=${durationSec}`);
});
es.onmessage = (ev) => {
  messages += 1;
  if (messages <= 3 || messages % 120 === 0) {
    const preview = (ev.data || "").slice(0, 120);
    console.log(`[pyth_signal_probe] msg#${messages}  ${preview}…`);
  }
};
es.onerror = (e) => {
  errors += 1;
  console.error("[pyth_signal_probe] error", e?.message || e);
};

const t = setTimeout(() => {
  console.log(
    `[pyth_signal_probe] done  elapsed_ms=${Date.now() - started}  messages=${messages}  errors=${errors}`
  );
  es.close();
  process.exit(errors > 0 && messages === 0 ? 1 : 0);
}, durationSec * 1000);

t.unref?.();
