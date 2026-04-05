/**
 * Print base58 public key for a Solana keypair JSON file (Drift/Jupiter-compatible).
 * Usage: npx tsx scripts/wallet_pubkey.ts /path/to/keypair.json
 */
import { Keypair } from "@solana/web3.js";
import fs from "node:fs";

const p = process.argv[2];
if (!p) {
  console.error("usage: wallet_pubkey.ts <keypair.json>");
  process.exit(1);
}
const raw = JSON.parse(fs.readFileSync(p, "utf8"));
const kp = Keypair.fromSecretKey(Uint8Array.from(raw));
console.log(kp.publicKey.toBase58());
