import { Keypair } from '@solana/web3.js';
import { promises as fs } from 'fs';

async function createKeypair() {
  const kp = Keypair.generate();
  console.info('✅ New wallet address:', kp.publicKey.toBase58());
  await fs.writeFile('new-keypair3.json', JSON.stringify(Array.from(kp.secretKey)));
  console.info('✅ Saved as new-keypair.json — fund this wallet with SOL + USDC');
}

createKeypair().catch(console.error);