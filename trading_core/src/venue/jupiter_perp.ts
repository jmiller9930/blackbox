/**
 * Jupiter Perps — canonical on-chain IDs (Sean).
 * Use for native Jupiter client / orderbook wiring; bot still uses Drift SDK until migrated.
 */

import { PublicKey } from '@solana/web3.js';

export const JUPITER_PERP_PROGRAM_ID = new PublicKey(
  'PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu'
);
export const JUPITER_PERP_POOL = new PublicKey(
  '5BUwFW4nRbftYTDMbgxykoFWqWHPzahFSNAaaaJtVKsq'
);
export const JUPITER_SOL_CUSTODY = new PublicKey(
  'J83w4HKfqxwcq3BEMMkPFSppX3gqekLyLJBexebFVkix'
);
export const JUPITER_USDC_CUSTODY = new PublicKey(
  '5SSkXsEKQepHHAewytPVwdej4epN1nxgLVM84L4KXgy7'
);
