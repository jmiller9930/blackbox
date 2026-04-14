/**
 * Load Solana pubkey from a keypair JSON file (standard solana-keygen format).
 * Never logs or persists secret key material — pubkey only for the analog DB.
 */
import { readFile } from 'fs/promises';
import { Keypair } from '@solana/web3.js';

/**
 * @param {string | undefined} keypairPath
 * @returns {Promise<{ pubkeyBase58: string } | null>}
 */
export async function loadPubkeyFromKeypairFile(keypairPath) {
  const p = (keypairPath || '').trim();
  if (!p) return null;
  const raw = await readFile(p, 'utf8');
  const arr = JSON.parse(raw);
  if (!Array.isArray(arr) || arr.length < 64) {
    throw new Error('keypair_json_invalid: expected uint8 array length >= 64');
  }
  const kp = Keypair.fromSecretKey(Uint8Array.from(arr));
  return { pubkeyBase58: kp.publicKey.toBase58() };
}
