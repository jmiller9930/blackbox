/**
 * Generate a new Solana keypair and write Drift-bot-compatible keypair.json.
 *
 * drift_trading_bot_source.ts expects KEYPAIR_PATH (default keypair.json) to be
 * ONLY a JSON array of 64 bytes — see fs.readFile + JSON.parse + Keypair.fromSecretKey.
 *
 * Run: cd trading_core && npm install && npm run create-wallet
 * Never commit keypair.json or *-wallet*.json (see trading_core/.gitignore).
 */

import { chmodSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { Keypair } from "@solana/web3.js";
import bs58 from "bs58";

const wallet = Keypair.generate();
const publicKey = wallet.publicKey.toBase58();
const secretBytes = Array.from(wallet.secretKey);
const secretKeyBase58 = bs58.encode(wallet.secretKey);

// Drift bot load path: JSON.parse -> Uint8Array.from -> Keypair.fromSecretKey
const driftPath = resolve("./keypair.json");
writeFileSync(driftPath, JSON.stringify(secretBytes), { encoding: "utf8" });
try {
  chmodSync(driftPath, 0o600);
} catch {
  // Windows may ignore chmod; ignore errors
}

// Optional human-readable backup (still secret — treat like keypair.json)
const backupPath = resolve("./wallet-backup.json");
const backup = {
  publicKey,
  secretKeyBase58,
  secretKey: secretBytes,
  note: "Keep offline. Drift bot uses keypair.json (array only).",
};
writeFileSync(backupPath, JSON.stringify(backup, null, 2), { encoding: "utf8" });
try {
  chmodSync(backupPath, 0o600);
} catch {
  /* ignore */
}

console.log("Public key (address):", publicKey);
console.log("");
console.log("Wrote Drift-compatible:", driftPath);
console.log("Wrote backup (pub + base58 + array):", backupPath);
console.log("");
console.log("Do not commit these files. Fund SOL/USDC on-chain before Drift deposit.");
console.log("base58 secret is in wallet-backup.json (secretKeyBase58) — never paste into chat.");
if (process.env.SHOW_SECRET === "1") {
  console.log("secretKeyBase58:", secretKeyBase58);
}
