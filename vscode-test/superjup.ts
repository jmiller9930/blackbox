import { promises as fs } from 'fs';
import {
  Connection,
  Keypair,
  PublicKey,
  ComputeBudgetProgram,
  VersionedTransaction,
  TransactionMessage,
  SystemProgram,
} from '@solana/web3.js';
import * as anchor from '@coral-xyz/anchor';
import {
  getAssociatedTokenAddressSync,
  createAssociatedTokenAccountIdempotentInstruction,
  TOKEN_PROGRAM_ID,
  ASSOCIATED_TOKEN_PROGRAM_ID,
  NATIVE_MINT,
  createSyncNativeInstruction,
} from '@solana/spl-token';
import { EventSource } from 'eventsource';
import fetch from 'node-fetch';

// ====================== CONSTANTS ======================
const PROGRAM_ID = new PublicKey('PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu');

// ====================== IDL ======================
import { IDL as jupiterPerpsIdl } from './jupiter-perpetuals-idl';

// ====================== CLIENT ======================
class JupiterPerpsClient {
  private program: anchor.Program;
  private connection: Connection;
  private wallet: anchor.Wallet;
  private userPubkey: PublicKey;

  constructor(connection: Connection, wallet: anchor.Wallet) {
    this.connection = connection;
    this.wallet = wallet;
    this.userPubkey = wallet.publicKey;

    const provider = new anchor.AnchorProvider(connection, wallet, { commitment: 'confirmed' });

    const idlWithAddress = {
      ...(jupiterPerpsIdl as any),
      address: PROGRAM_ID.toBase58(),
    };

    this.program = new anchor.Program(idlWithAddress as any, provider);
  }

  async getPerpPosition() {
    try {
      const longPos: any = await (this.program as any).account.position.fetch('dummy');
      return longPos;
    } catch {
      return null;
    }
  }
} // ✅ FIXED: class properly closed

// ====================== BOT ======================
class TradingBot {

  private async fetchLatestBinanceKline() {
    try {
      const response = await fetch('https://api.binance.com/api/v3/klines?symbol=SOLUSDT&interval=5m&limit=2');
      const data = await response.json() as any[];

      if (!data || data.length < 1) return null;

      const k = data[0];
      return {
        open: parseFloat(k[1]),
        high: parseFloat(k[2]),
        low: parseFloat(k[3]),
        close: parseFloat(k[4]),
        volume: parseFloat(k[5])
      };
    } catch {
      return null;
    }
  }

  public async run() {
    console.info('Bot starting (compile-safe mode)');
  }
}

// ====================== MAIN ======================
async function main() {
  const bot = new TradingBot();
  await bot.run();
}

main().catch(console.error);
