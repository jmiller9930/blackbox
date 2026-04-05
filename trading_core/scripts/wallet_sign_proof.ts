/**
 * Sign a fixed message with the keypair — proves signing works (no on-chain submit).
 * Usage: npx tsx scripts/wallet_sign_proof.ts /path/to/keypair.json
 */
import { ed25519 } from "@noble/curves/ed25519";
import { Keypair } from "@solana/web3.js";
import bs58 from "bs58";
import fs from "node:fs";

const p = process.argv[2];
if (!p) {
  console.error("usage: wallet_sign_proof.ts <keypair.json>");
  process.exit(1);
}
const secret = Uint8Array.from(JSON.parse(fs.readFileSync(p, "utf8")));
const kp = Keypair.fromSecretKey(secret);
const msg = new TextEncoder().encode("blackbox_wallet_proof_v1");
const sig = ed25519.sign(msg, secret.slice(0, 32));
const out = {
  pubkey: kp.publicKey.toBase58(),
  message: "blackbox_wallet_proof_v1",
  signature_b58: bs58.encode(sig),
};
console.log(JSON.stringify(out));
