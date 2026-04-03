/**
 * Generate a new Solana keypair — Drift bot format only.
 *
 * Writes:
 * - keypair.json — ONE line, compact JSON array [n,n,...] (64 bytes). No spaces.
 *   src/bot/drift_trading_bot_source.ts: JSON.parse → Uint8Array.from → Keypair.fromSecretKey
 * - keypair.base58 — ONE line, base58 only (no brackets) for Phantom/import UIs.
 *
 * Run: npm run create-wallet (from repo root) or npm run create-wallet --prefix trading_core
 */

import { chmodSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { Keypair } from "@solana/web3.js";
import bs58 from "bs58";

const wallet = Keypair.generate();
const publicKey = wallet.publicKey.toBase58();
const secretBytes = Array.from(wallet.secretKey);
const secretKeyBase58 = bs58.encode(wallet.secretKey);

// Compact JSON: no spaces anywhere (single line).
const compactArray = JSON.stringify(secretBytes);
const driftPath = resolve("./keypair.json");
writeFileSync(driftPath, compactArray + "\n", { encoding: "utf8" });

const base58Path = resolve("./keypair.base58");
writeFileSync(base58Path, secretKeyBase58 + "\n", { encoding: "utf8" });

for (const p of [driftPath, base58Path]) {
  try {
    chmodSync(p, 0o600);
  } catch {
    /* ignore */
  }
}

console.log("Public key:", publicKey);
console.log("Drift load (JSON array):", driftPath);
console.log("Import (base58 one line):", base58Path);
console.log("Fund this address on-chain. Do not commit these files.");

if (process.env.SHOW_SECRET === "1") {
  console.log("base58:", secretKeyBase58);
}
