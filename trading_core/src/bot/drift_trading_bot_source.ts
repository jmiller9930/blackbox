/**
 * Trading core rules — source snapshot (SOL-PERP bot; Drift SDK for orders/subscriptions).
 * DEPRECATED: Drift is not in service for BLACK BOX — do not treat this file as an active live venue path.
 * See docs/architect/ANNA_GOES_TO_SCHOOL.md §1.1.2.1.
 * Extracted from operator email / thread 2026-03-22.
 * Drift DLOB WebSocket removed (migrating to Jupiter Perps); bid/ask come from Pyth oracle until native Jupiter book is wired.
 * QUICKNODE_RPC redacted: use env SOLANA_RPC_URL for authenticated RPC.
 * keypair.json must never be committed.
 */

import { promises as fs } from 'fs';
import { Connection, Keypair, PublicKey } from '@solana/web3.js';
import { Wallet as AnchorWallet } from '@project-serum/anchor';
import {
 DriftClient,
 PerpMarketAccount,
 BN,
 PositionDirection,
 OrderType,
 OrderParams,
 PostOnlyParams,
 MarketType,
 OrderSubscriber,
 BASE_PRECISION,
 PRICE_PRECISION,
 QUOTE_PRECISION,
 getMarketsAndOraclesForSubscription,
 OrderTriggerCondition,
 OraclePriceData,
 OrderStatus,
 TxParams,
 EventSubscriber,
 DriftClientSubscriptionConfig,
 EventSubscriptionOptions,
 isVariant,
 BulkAccountLoader,
 Order,
 UserAccount,
 ModifyOrderParams,
} from '@drift-labs/sdk';
import EventSource from 'eventsource';
import {
 JUPITER_PERP_PROGRAM_ID,
 JUPITER_PERP_POOL,
 JUPITER_SOL_CUSTODY,
 JUPITER_USDC_CUSTODY,
} from '../venue/jupiter_perp.js';

const SOL_PERP_INDEX = 0;
const USDC_SPOT_INDEX = 0;
const LEVERAGE = 40;
const TP_PCT = 0.005;
const SL_PCT = 0.005;
const EMERGENCY_SL_PCT = 0.006;
const INITIAL_COLLATERAL = 20;
const LOOKBACK = 10;
const RSI_PERIOD = 14;
/** Sean Jupiter policy v2 (Apr 2026) — align Python baseline ``sean_jupiter_baseline_signal``; deprecated Drift snapshot used 60/40. */
const RSI_SHORT_THRESHOLD = 48;
const RSI_LONG_THRESHOLD = 52;
const CONFIDENCE_THRESHOLD = 0.001;
const SLIPPAGE_PCT = 0.001;
const ENTRY_TIMEOUT_MS = 15000;
const MARGIN_BUFFER = 0.999;
const PRICE_MOVE_PCT = 0.0011;
const POSITION_CHECK_INTERVAL_MS = 60000;
const VOLUME_CHECK_INTERVAL_MS = 300000;
const MIN_VOLUME_USD = 90000000;
const PRICE_EPSILON = 0.001;
const RSI_EPSILON = 0.05;
const BE_THRESHOLD = 0.003;
const SMALL_PROFIT = 0.001;
const SL_EM_GAP = 0.001;
const SAFE_PROFIT_THRESHOLD = 0.002;
const QUICKNODE_RPC = process.env.SOLANA_RPC_URL || 'https://api.mainnet-beta.solana.com'; // set SOLANA_RPC_URL (e.g. QuickNode) — no secrets in git
const PUBLIC_SOLANA_WS = 'wss://api.mainnet-beta.solana.com';
/** Load from env so the key file can live outside the repo; never commit the file. */
const KEYPAIR_PATH = process.env.KEYPAIR_PATH || 'keypair.json';

const PYTH_SSE_URL = 'https://hermes.pyth.network/v2/updates/price/stream?ids[]=ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d';
const COINGECKO_VOLUME_URL = 'https://api.coingecko.com/api/v3/exchanges/drift_protocol/volume_chart?days=1';
const COINGECKO_BTC_PRICE_URL = 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd';
const SUBSCRIBE_RETRY_MAX = 3;
const SUBSCRIBE_RETRY_DELAY_MS = 2000;
const BACKOFF_FACTOR = 1.2;
const MAX_BACKOFF_MS = 500;
const PYTH_MAX_RECONNECTS = 10;
const PYTH_BASE_RECONNECT_DELAY = 5000;
const PYTH_MAX_RECONNECT_DELAY = 60000;
const BOOK_UPDATE_TIMEOUT_MS = 5000;
const RESUB_TIMEOUT_MS = 30000;
const MIN_TRAIL_MOVE_PCT = 0.0003; // 0.03% for TP
const MIN_SL_TRAIL_MOVE_PCT = 0.0005; // 0.05% for SL/EM SL
const MOD_DEBOUNCE_MS = 5000; // 5s
const MOD_DELAY_MS = 1500; // 1.5s delay between mods/places
const MIN_NOTIONAL_DEPTH_USD = 10000; // Min cumulative notional for top 5 levels

interface Candle {
 open: number;
 high: number;
 low: number;
 close: number;
 volume: number;
}

class TradingBot {
 private driftClient: DriftClient | null = null;
 private priceBuffer: { timestamp: Date; price: number }[] = [];
 private df5min: { timestamp: Date; candle: Candle }[] = [];
 private breakEvenLocked: boolean = false;
 private rsiInitialized: boolean = false;
 private position: number = 0;
 private entryPrice: number = 0.0;
 private trailSl: number = 0.0;
 private emergTrailSl: number = 0.0;
 private trailTp: number = 0.0;
 private lastHigh: number = 0.0;
 private lastLow: number = 0.0;
 private lastPriceUpdate: number = 0.0;
 private lastModTime: number = 0;
 private lastPrice: number | null = null;
 private orderSubscriber: OrderSubscriber | null = null;
 private eventSubscriber: EventSubscriber | null = null;
 private bestBid: number = 0.0;
 private bestAsk: number = 0.0;
 private bids: { price: number; size: number }[] = [];
 private asks: { price: number; size: number }[] = [];
 private cachedPosition: any | undefined = undefined;
 private previousBaseAmount: BN = new BN(0);
 private pythSse: EventSource | null = null;
 private pythReconnectAttempts: number = 0;
 private slOrderId: number | undefined = undefined;
 private tpOrderId: number | undefined = undefined;
 private emergencySlOrderId: number | undefined = undefined;
 private bookUpdatePromise: Promise<void> | null = null;
 private bookUpdateResolve: (() => void) | null = null;
 private entryTimeout: NodeJS.Timeout | null = null;
 private userPubkey: PublicKey | null = null;
 private pendingSignal: { short: boolean; long: boolean; price: number } | null = null;
 private updateQueue: Promise<void> = Promise.resolve();
 private updateInProgress: boolean = false;
 private lastUpdateAttempt: number = 0;
 private lastVolumeCheckTime: number = 0;
 private cachedVolumeUSD: number = 0;
 private userOrderIdCounter: number = 1;
 private marketCache: PerpMarketAccount | undefined = undefined;

 private getNextUserOrderId(): number {
 return Math.floor(Math.random() * 255) + 1;
 }

 public async initDrift() {
 try {
 console.info('Starting initDrift...');
 const connection = new Connection(QUICKNODE_RPC, {
 commitment: 'confirmed',
 wsEndpoint: PUBLIC_SOLANA_WS
 });
 const keypairJson = await fs.readFile(KEYPAIR_PATH, 'utf-8');
 const keypairArray = JSON.parse(keypairJson);
 const keypair = Keypair.fromSecretKey(Uint8Array.from(keypairArray));
 const wallet = new AnchorWallet(keypair);

 this.driftClient = new DriftClient({
 connection,
 wallet,
 env: 'mainnet-beta',
 perpMarketIndexes: [SOL_PERP_INDEX],
 spotMarketIndexes: [USDC_SPOT_INDEX],
 accountSubscription: { 
 type: 'websocket',
 resubTimeoutMs: RESUB_TIMEOUT_MS
 },
 txParams: { computeUnits: 600_000, computeUnitsPrice: 10_000 },
 });
 await this.driftClient.subscribe();
 if (!await this.checkUserAccountExists()) {
 console.info('Initializing user account...');
 await this.driftClient.initializeUserAccount();
 }
 this.userPubkey = this.driftClient.getUser().userAccountPublicKey;
 const userAccount = this.driftClient.getUserAccount();
 if (userAccount && !userAccount.isMarginTradingEnabled) {
 console.info('Enabling margin trading...');
 await this.driftClient.updateUserMarginTradingEnabled([{ marginTradingEnabled: true, subAccountId: 0 }]);
 }
 this.marketCache = this.driftClient.getPerpMarketAccount(SOL_PERP_INDEX);
 this.orderSubscriber = new OrderSubscriber({
 driftClient: this.driftClient,
 subscriptionConfig: { type: 'websocket', resubTimeoutMs: RESUB_TIMEOUT_MS },
 });
 await this.orderSubscriber.subscribe();
 // @ts-ignore
 this.orderSubscriber.eventEmitter.on('onAccount', (userAccount: UserAccount) => {
 this.handleOrderUpdate(userAccount.orders);
 });
 console.info('Order subscriber ready');
 this.eventSubscriber = new EventSubscriber(
 this.driftClient.connection,
 this.driftClient.program,
 {
 eventTypes: ['OrderActionRecord'],
 maxTx: 4096,
 maxEventsPerType: 4096,
 orderBy: 'blockchain',
 orderDir: 'asc',
 commitment: 'confirmed',
 logProviderConfig: { type: 'websocket' },
 }
 );
 await this.eventSubscriber.subscribe();
 this.eventSubscriber.eventEmitter.on('newEvent', (event: any) => {
 if (event.eventType === 'OrderActionRecord' && isVariant(event.action, 'fill')) {
 if (event.taker?.equals(this.userPubkey) || event.maker?.equals(this.userPubkey)) {
 console.info('Fill detected');
 this.handleFillEvent();
 }
 }
 });
 console.info('Event subscriber ready');
 console.info(
 `Jupiter Perp reference: program=${JUPITER_PERP_PROGRAM_ID.toBase58()} pool=${JUPITER_PERP_POOL.toBase58()} ` +
 `solCustody=${JUPITER_SOL_CUSTODY.toBase58()} usdcCustody=${JUPITER_USDC_CUSTODY.toBase58()}`
 );
 await this.fetchHistoricalCandles(); // New: Fetch real historical candles before Pyth
 this.setupPythSse();
 const perpPosition = this.driftClient.getUser().getPerpPosition(SOL_PERP_INDEX);
 if (perpPosition && perpPosition.baseAssetAmount.abs().gt(new BN(0)) && this.position === 0) {
 console.info('Detected external position—adopting...');
 await this.adoptPosition(perpPosition);
 }
 } catch (e) {
 console.error(`Init error: ${e}`);
 process.exit(1);
 }
 }

 // New method to fetch historical 5-min candles from Drift Data API
 private async fetchHistoricalCandles() {
 try {
 console.info('Fetching last 15 5-min historical candles from Drift API...');
 const fetch = require('node-fetch');
 const response = await fetch('https://data.api.drift.trade/market/SOL-PERP/candles/5?limit=15');
 const data: any = await response.json();
 if (!data.success || !Array.isArray(data.records)) {
 console.warn('Invalid historical data; falling back to dummies');
 return;
 }
 if (data.records.length === 0) {
 console.warn('No historical candles fetched; falling back to dummies');
 return;
 }
 // Sort records by ts ascending (oldest first) for correct RSI order
 data.records.sort((a: any, b: any) => a.ts - b.ts);
 // Map to df5min format using oracle prices for consistency with live Pyth
 this.df5min = data.records.map((candle: any) => ({
 timestamp: new Date(candle.ts * 1000), // Convert Unix s to Date
 candle: {
 open: candle.oracleOpen,
 high: candle.oracleHigh,
 low: candle.oracleLow,
 close: candle.oracleClose,
 volume: candle.baseVolume // Or quoteVolume if preferred
 }
 }));
 this.rsiInitialized = true;
 console.info(`Fetched ${this.df5min.length} real historical candles for RSI init`);
 } catch (e) {
 console.error('Historical candles fetch error:', e);
 // Fallback to original dummy logic if needed (but we'll keep it empty or handle in aggregateCandles)
 }
 }

 private async checkUserAccountExists(): Promise<boolean> {
 try {
 const exists = !!this.driftClient!.getUserAccount();
 return exists;
 } catch (e) {
 console.error('Check user account error:', e);
 return false;
 }
 }

 private setupPythSse() {
 console.info('Setting up Pyth SSE...');
 this.pythSse = new EventSource(PYTH_SSE_URL);
 this.pythSse.addEventListener('open', () => {
 console.info('Pyth SSE connected');
 });
 this.pythSse.onmessage = (event) => {
 try {
 const data = JSON.parse(event.data);
 if (data.parsed && data.parsed.length > 0) {
 const priceData = data.parsed[0].price;
 if (priceData && priceData.price && priceData.conf && priceData.expo) {
 const rawPrice = Number(priceData.price) * Math.pow(10, priceData.expo);
 const confidence = Number(priceData.conf) * Math.pow(10, priceData.expo);
 if (confidence / rawPrice > CONFIDENCE_THRESHOLD) {
 console.warn(`Ignoring low confidence price: ${rawPrice} (±${confidence})`);
 return;
 }
 if (rawPrice === this.lastPrice) return;

 this.lastPrice = rawPrice;
 this.syncSyntheticBookFromOracle();
 console.info(`Pyth price: ${rawPrice} (±${confidence})`);

 const now = new Date();
 this.priceBuffer.push({ timestamp: now, price: rawPrice });
 this.aggregateCandles();
 this.checkPriceMovementForUpdate();
 }
 }
 } catch (e) {
 console.error('Pyth SSE message error:', e);
 }
 };
 this.pythSse.onerror = (e) => {
 console.error('Pyth SSE error:', e);
 this.pythSse?.close();

 const delay = Math.min(PYTH_BASE_RECONNECT_DELAY * Math.pow(2, this.pythReconnectAttempts), PYTH_MAX_RECONNECT_DELAY);
 this.pythReconnectAttempts++;
 setTimeout(() => this.setupPythSse(), delay);
 };
 console.info('Pyth SSE initialized');
 }

 private async checkPriceMovementForUpdate() {
 if (this.updateInProgress || this.lastPrice === null || this.position === 0) return;

 const now = Date.now();
 if (now - this.lastModTime < MOD_DEBOUNCE_MS) {
 console.info('Debouncing trail update');
 return;
 }

 this.updateInProgress = true;
 try {
 await this.updateTrailingOrders();
 this.lastModTime = now;
 } finally {
 this.updateInProgress = false;
 }
 }

 private async updateTrailingOrders() {
 if (this.position === 0 || this.lastPrice === null) return;
 const perpPosition = this.driftClient!.getUser().getPerpPosition(SOL_PERP_INDEX);
 if (!perpPosition || perpPosition.baseAssetAmount.abs().eq(new BN(0))) {
 console.info('No position to trail');
 return;
 }
 let tpModified = false;
 let slModified = false;
 let emergModified = false;
 const profitPct = this.position === 1
 ? (this.lastPrice - this.entryPrice) / this.entryPrice
 : (this.entryPrice - this.lastPrice) / this.entryPrice;
 if (!this.breakEvenLocked && profitPct > SAFE_PROFIT_THRESHOLD) {
 console.info('Locked breakeven profit');
 if (this.position === 1) {
 this.trailSl = this.entryPrice * (1 + 0.0005);
 this.emergTrailSl = this.trailSl - SL_EM_GAP * this.entryPrice;
 } else {
 this.trailSl = this.entryPrice * (1 - 0.0005);
 this.emergTrailSl = this.trailSl + SL_EM_GAP * this.entryPrice;
 }
 this.breakEvenLocked = true;
 slModified = true;
 emergModified = true;
 }
 const priceMovePct = Math.abs(this.lastPrice - this.lastPriceUpdate) / this.lastPriceUpdate;
 if (this.position === 1) {
 this.lastHigh = Math.max(this.lastHigh, this.lastPrice);
 const newTrailTp = this.lastHigh * (1 + TP_PCT);
 if (newTrailTp > this.trailTp && priceMovePct > MIN_TRAIL_MOVE_PCT) {
 this.trailTp = newTrailTp;
 tpModified = true;
 }
 if (this.breakEvenLocked) {
 const newTrailSl = Math.max(this.trailSl, this.lastPrice * (1 - SL_PCT));
 const newEmergSl = Math.max(this.emergTrailSl, this.lastPrice * (1 - EMERGENCY_SL_PCT));
 if (newTrailSl > this.trailSl && priceMovePct > MIN_SL_TRAIL_MOVE_PCT) {
 this.trailSl = newTrailSl;
 slModified = true;
 }
 if (newEmergSl > this.emergTrailSl && priceMovePct > MIN_SL_TRAIL_MOVE_PCT) {
 this.emergTrailSl = newEmergSl;
 emergModified = true;
 }
 }
 } else {
 this.lastLow = Math.min(this.lastLow, this.lastPrice);
 const newTrailTp = this.lastLow * (1 - TP_PCT);
 if (newTrailTp < this.trailTp && priceMovePct > MIN_TRAIL_MOVE_PCT) {
 this.trailTp = newTrailTp;
 tpModified = true;
 }
 if (this.breakEvenLocked) {
 const newTrailSl = Math.min(this.trailSl, this.lastPrice * (1 + SL_PCT));
 const newEmergSl = Math.min(this.emergTrailSl, this.lastPrice * (1 + EMERGENCY_SL_PCT));
 if (newTrailSl < this.trailSl && priceMovePct > MIN_SL_TRAIL_MOVE_PCT) {
 this.trailSl = newTrailSl;
 slModified = true;
 }
 if (newEmergSl < this.emergTrailSl && priceMovePct > MIN_SL_TRAIL_MOVE_PCT) {
 this.emergTrailSl = newEmergSl;
 emergModified = true;
 }
 }
 }
 if (tpModified || slModified || emergModified) {
 console.info(`Trailing: TP=${this.trailTp.toFixed(8)}, SL=${this.trailSl.toFixed(8)}, EM_SL=${this.emergTrailSl.toFixed(8)}`);
 await this.batchModifyOrders(tpModified, slModified, emergModified);
 this.lastPriceUpdate = this.lastPrice;
 } else {
 console.info('No meaningful trail move');
 }
 }

 private async batchModifyOrders(tpModified: boolean, slModified: boolean, emergModified: boolean) {
 try {
 await this.waitForBookUpdate(); // Add DLOB fetch for book-aware limits
 // Cancel + place for each modified order
 if (slModified) {
 await this.cancelAndPlaceSLOrder();
 await new Promise(resolve => setTimeout(resolve, MOD_DELAY_MS)); // Delay
 }
 if (tpModified) {
 await this.cancelAndPlaceTPOrder();
 await new Promise(resolve => setTimeout(resolve, MOD_DELAY_MS)); // Delay
 }
 if (emergModified) {
 await this.cancelAndPlaceEmergencySLOrder();
 await new Promise(resolve => setTimeout(resolve, MOD_DELAY_MS)); // Delay
 }
 } catch (e) {
 console.error('Batch mod error:', e);
 // Protection: Re-place all after full cancel
 await this.cancelRemnantOrders();
 await this.batchModifyOrders(true, true, true); // Recursive re-place
 }
 }

 private async getDrift24hVolumeUSD(): Promise<number> {
 try {
 const fetch = require('node-fetch');
 const volumeRes = await fetch(COINGECKO_VOLUME_URL);
 const volumeData = await volumeRes.json();
 const lastBtcVolume = parseFloat(volumeData[volumeData.length - 1][1]);
 const priceRes = await fetch(COINGECKO_BTC_PRICE_URL);
 const priceData = await priceRes.json();
 const btcUsd = priceData.bitcoin.usd;
 const totalUsd = lastBtcVolume * btcUsd;
 console.info(`Fetched Drift 24h volume: $${totalUsd.toFixed(0)} USD`);
 return totalUsd;
 } catch (e) {
 console.error('Volume fetch error:', e);
 return 0;
 }
 }

 private async checkVolume(): Promise<boolean> {
 const now = Date.now();
 if (now - this.lastVolumeCheckTime < VOLUME_CHECK_INTERVAL_MS) {
 return this.cachedVolumeUSD >= MIN_VOLUME_USD;
 }
 this.lastVolumeCheckTime = now;
 this.cachedVolumeUSD = await this.getDrift24hVolumeUSD();
 return this.cachedVolumeUSD >= MIN_VOLUME_USD;
 }

 private async adoptPosition(perpPosition: any) {
 try {
 console.info('Adopting external position...');
 this.position = perpPosition.baseAssetAmount.gt(new BN(0)) ? 1 : -1;
 const quoteAmount = Math.abs(perpPosition.quoteEntryAmount.toNumber()) / QUOTE_PRECISION.toNumber();
 const baseAmount = Math.abs(perpPosition.baseAssetAmount.toNumber()) / BASE_PRECISION.toNumber();
 this.entryPrice = quoteAmount / baseAmount;
 console.info(`Adopted ${this.position === 1 ? 'LONG' : 'SHORT'} at ${this.entryPrice.toFixed(8)}`);
 console.info(`Base: ${baseAmount.toFixed(4)}, Quote: ${quoteAmount.toFixed(2)}`);
 if (this.position === 1) {
 this.trailSl = this.entryPrice * (1 - SL_PCT);
 this.emergTrailSl = this.entryPrice * (1 - EMERGENCY_SL_PCT);
 this.trailTp = this.entryPrice * (1 + TP_PCT);
 this.lastHigh = this.entryPrice;
 this.lastLow = this.entryPrice;
 } else {
 this.trailSl = this.entryPrice * (1 + SL_PCT);
 this.emergTrailSl = this.entryPrice * (1 + EMERGENCY_SL_PCT);
 this.trailTp = this.entryPrice * (1 - TP_PCT);
 this.lastLow = this.entryPrice;
 this.lastHigh = this.entryPrice;
 }
 this.lastPriceUpdate = this.entryPrice;
 this.breakEvenLocked = false;
 this.cachedPosition = perpPosition;
 this.previousBaseAmount = perpPosition.baseAssetAmount.abs();
 await this.cancelRemnantOrders();
 const pendingEntries = this.driftClient!.getUserAccount()!.orders.filter(o =>
 isVariant(o.status, 'open') && !o.reduceOnly && isVariant(o.marketType, 'perp') && o.marketIndex === SOL_PERP_INDEX
 );
 if (pendingEntries.length > 0) {
 console.info(`Canceling ${pendingEntries.length} pending entry orders during adoption`);
 await this.driftClient!.cancelOrders(MarketType.PERP, SOL_PERP_INDEX);
 }
 let success = false;
 let attempts = 0;
 while (!success && attempts < 3) {
 attempts++;
 try {
 const slParams = this.getSLOrderParams();
 const tpParams = this.getTPOrderParams();
 const emParams = this.getEmergencySLOrderParams();
 const orders = [slParams, tpParams, emParams];
 const txSig = await this.driftClient!.placeOrders(orders);
 console.info(`Batch orders placed: ${txSig}`);
 await new Promise(resolve => setTimeout(resolve, 1000)); // Delay for confirm
 const orderIds = await this.getOrderIdsAfterPlace([slParams.userOrderId, tpParams.userOrderId, emParams.userOrderId]);
 this.slOrderId = orderIds[0];
 this.tpOrderId = orderIds[1];
 this.emergencySlOrderId = orderIds[2];
 if (this.slOrderId && this.tpOrderId && this.emergencySlOrderId) {
 success = true;
 } else {
 console.warn(`Batch IDs incomplete on attempt ${attempts}; retrying`);
 await new Promise(resolve => setTimeout(resolve, 2000)); // Delay retry
 }
 } catch (batchErr: any) {
 if (batchErr.message.includes('UserOrderIdAlreadyInUse')) {
 console.warn(`Batch collision on attempt ${attempts}; retrying with new IDs`);
 await new Promise(resolve => setTimeout(resolve, 1000));
 } else {
 throw batchErr;
 }
 }
 }
 if (!success) {
 console.error('Failed batch after retries; falling back to single places');
 await this.cancelAndPlaceSLOrder();
 await this.cancelAndPlaceTPOrder();
 await this.cancelAndPlaceEmergencySLOrder();
 }
 } catch (e) {
 console.error('Adopt position error:', e);
 this.position = 0;
 } finally {
 console.info('Position adopted');
 }
 }

 private getSLOrderParams(): OrderParams {
 const dir = this.position === 1 ? PositionDirection.SHORT : PositionDirection.LONG;
 const trig = this.trailSl;
 let lim = dir === PositionDirection.SHORT ? trig * (1 - SLIPPAGE_PCT) : trig * (1 + SLIPPAGE_PCT);
 // Clamp limit to not cross book
 const tick = this.getTickSize();
 if (this.bestBid > 0 && this.bestAsk > 0) {
 lim = dir === PositionDirection.SHORT 
 ? Math.max(lim, this.bestBid + tick) // For short (sell): max(trig-slip, bid+tick)
 : Math.min(lim, this.bestAsk - tick); // For long (buy): min(trig+slip, ask-tick)
 } // Else fallback to original if book timeout
 const trigPrice = this.driftClient!.convertToPricePrecision(trig);
 const limPrice = this.driftClient!.convertToPricePrecision(lim);
 const trigCond = this.position === 1 ? OrderTriggerCondition.BELOW : OrderTriggerCondition.ABOVE;
 const base = this.cachedPosition.baseAssetAmount.abs();
 return {
 orderType: OrderType.TRIGGER_LIMIT,
 marketIndex: SOL_PERP_INDEX,
 direction: dir,
 baseAssetAmount: base,
 reduceOnly: true,
 marketType: MarketType.PERP,
 triggerPrice: trigPrice,
 triggerCondition: trigCond,
 price: limPrice,
 postOnly: PostOnlyParams.NONE,
 userOrderId: this.getNextUserOrderId(),
 oraclePriceOffset: 0,
 bitFlags: new BN(0),
 auctionDuration: 0,
 auctionStartPrice: new BN(0),
 auctionEndPrice: new BN(0),
 maxTs: new BN(0),
 };
 }

 private getTPOrderParams(): OrderParams {
 const dir = this.position === 1 ? PositionDirection.SHORT : PositionDirection.LONG;
 const trig = this.trailTp;
 let lim = dir === PositionDirection.SHORT ? trig * (1 - SLIPPAGE_PCT) : trig * (1 + SLIPPAGE_PCT);
 // Clamp limit to not cross book
 const tick = this.getTickSize();
 if (this.bestBid > 0 && this.bestAsk > 0) {
 lim = dir === PositionDirection.SHORT 
 ? Math.max(lim, this.bestBid + tick) // For short (sell): max(trig-slip, bid+tick)
 : Math.min(lim, this.bestAsk - tick); // For long (buy): min(trig+slip, ask-tick)
 } // Else fallback to original if book timeout
 const trigPrice = this.driftClient!.convertToPricePrecision(trig);
 const limPrice = this.driftClient!.convertToPricePrecision(lim);
 const trigCond = this.position === 1 ? OrderTriggerCondition.ABOVE : OrderTriggerCondition.BELOW;
 const base = this.cachedPosition.baseAssetAmount.abs();
 return {
 orderType: OrderType.TRIGGER_LIMIT,
 marketIndex: SOL_PERP_INDEX,
 direction: dir,
 baseAssetAmount: base,
 reduceOnly: true,
 marketType: MarketType.PERP,
 triggerPrice: trigPrice,
 triggerCondition: trigCond,
 price: limPrice,
 postOnly: PostOnlyParams.NONE,
 userOrderId: this.getNextUserOrderId(),
 oraclePriceOffset: 0,
 bitFlags: new BN(0),
 auctionDuration: 0,
 auctionStartPrice: new BN(0),
 auctionEndPrice: new BN(0),
 maxTs: new BN(0),
 };
 }

 private getEmergencySLOrderParams(): OrderParams {
 const dir = this.position === 1 ? PositionDirection.SHORT : PositionDirection.LONG;
 const emergTrig = this.emergTrailSl;
 const trigPrice = this.driftClient!.convertToPricePrecision(emergTrig);
 const trigCond = this.position === 1 ? OrderTriggerCondition.BELOW : OrderTriggerCondition.ABOVE;
 const base = this.cachedPosition.baseAssetAmount.abs();
 return {
 orderType: OrderType.TRIGGER_MARKET,
 marketIndex: SOL_PERP_INDEX,
 direction: dir,
 baseAssetAmount: base,
 reduceOnly: true,
 marketType: MarketType.PERP,
 triggerPrice: trigPrice,
 triggerCondition: trigCond,
 price: new BN(0),
 postOnly: PostOnlyParams.NONE,
 userOrderId: this.getNextUserOrderId(),
 oraclePriceOffset: 0,
 bitFlags: new BN(0),
 auctionDuration: 0,
 auctionStartPrice: new BN(0),
 auctionEndPrice: new BN(0),
 maxTs: new BN(0),
 };
 }

 private async cancelRemnantOrders() {
 console.info('Canceling remnant orders...');
 try {
 const userAccount = this.driftClient!.getUserAccount();
 const remnants = userAccount!.orders.filter(o =>
 isVariant(o.status, 'open') && o.reduceOnly && isVariant(o.marketType, 'perp') && o.marketIndex === SOL_PERP_INDEX
 );
 if (remnants.length > 0) {
 console.info(`Canceling ${remnants.length} remnant reduceOnly orders`);
 await this.driftClient!.cancelOrders(MarketType.PERP, SOL_PERP_INDEX);
 }
 // If position is zero and any open orders remain, force-cancel all
 if (this.position === 0) {
 const remainingOpen = userAccount!.orders.filter(o => isVariant(o.status, 'open') && isVariant(o.marketType, 'perp') && o.marketIndex === SOL_PERP_INDEX);
 if (remainingOpen.length > 0) {
 console.warn(`Found ${remainingOpen.length} lingering open perp orders with zero position; force-canceling all`);
 await this.driftClient!.cancelOrders(MarketType.PERP, SOL_PERP_INDEX);
 }
 }
 this.slOrderId = undefined;
 this.tpOrderId = undefined;
 this.emergencySlOrderId = undefined;
 console.info('Remnant cancel complete');
 } catch (e) {
 console.error('Error canceling remnants:', e);
 }
 }

 private async handleFillEvent() {
 try {
 this.handleOrderUpdate(this.driftClient!.getUserAccount()!.orders);
 } catch (e) {
 console.error('Fill event error:', e);
 }
 }

 /**
  * Bid/ask around Pyth mid (replaces Drift `dlob.drift.trade` WebSocket). Wire `JUPITER_PERP_*` for native Jupiter book when ready.
  */
 private syncSyntheticBookFromOracle(): void {
 if (this.lastPrice === null || this.lastPrice <= 0) return;
 const half = SLIPPAGE_PCT;
 this.bestBid = this.lastPrice * (1 - half);
 this.bestAsk = this.lastPrice * (1 + half);
 const sz = Math.max(MIN_NOTIONAL_DEPTH_USD / this.lastPrice, 1);
 this.bids = [{ price: this.bestBid, size: sz }];
 this.asks = [{ price: this.bestAsk, size: sz }];
 if (this.bookUpdateResolve) {
 this.bookUpdateResolve();
 this.bookUpdateResolve = null;
 }
 }

 private async waitForBookUpdate(): Promise<void> {
 this.syncSyntheticBookFromOracle();
 if (this.bestBid > 0 && this.bestAsk > 0) return;

 let retries = 0;
 const maxRetries = 2;
 while (retries <= maxRetries) {
 this.bookUpdatePromise = new Promise((resolve) => {
 this.bookUpdateResolve = resolve;
 });
 const timeout = setTimeout(() => {
 if (this.bookUpdateResolve) {
 console.warn(`Book timeout on attempt ${retries + 1} (waiting for Pyth)`);
 this.bookUpdateResolve();
 this.bookUpdateResolve = null;
 }
 }, BOOK_UPDATE_TIMEOUT_MS);
 await this.bookUpdatePromise;
 clearTimeout(timeout);
 this.bookUpdatePromise = null;

 this.syncSyntheticBookFromOracle();
 if (this.bestBid > 0 && this.bestAsk > 0) {
 return;
 }
 retries++;
 if (retries <= maxRetries) {
 console.info(`Retrying book update (attempt ${retries})`);
 await new Promise(resolve => setTimeout(resolve, 1000));
 }
 }
 console.warn('Book update failed after retries; using fallback');
 }

 private getCumulativeNotional(direction: 'bid' | 'ask', levels: number = 5): number {
 const bookSide = direction === 'bid' ? this.bids : this.asks;
 let cumulative = 0;
 for (let i = 0; i < Math.min(levels, bookSide.length); i++) {
 cumulative += bookSide[i].size * bookSide[i].price;
 }
 return cumulative;
 }

 private aggregateCandles() {
 try {
 const now = new Date();
 const fiveMinAgo = new Date(now.getTime() - 5 * 60 * 1000);
 this.priceBuffer = this.priceBuffer.filter(p => p.timestamp >= new Date(fiveMinAgo.getTime() - 30 * 5 * 60 * 1000));
 const minutes = Math.floor(now.getMinutes() / 5) * 5;
 const currentMin = new Date(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours(), minutes, 0, 0);
 if (this.df5min.length > 0 && this.df5min[this.df5min.length - 1].timestamp.getTime() >= currentMin.getTime()) return;
 const recentPrices = this.priceBuffer.filter(p => p.timestamp >= fiveMinAgo).map(p => p.price);
 if (recentPrices.length > 0) {
 if (this.df5min.length === 0 && !this.rsiInitialized) {
 const firstPrice = recentPrices[0];
 const startTs = new Date(now.getTime() - RSI_PERIOD * 5 * 60 * 1000);
 for (let j = 0; j < RSI_PERIOD; j++) {
 const dummyTs = new Date(startTs.getTime() + j * 5 * 60 * 1000);
 const dummyCandle: Candle = {
 open: firstPrice,
 high: firstPrice,
 low: firstPrice,
 close: firstPrice,
 volume: 0,
 };
 this.df5min.push({ timestamp: dummyTs, candle: dummyCandle });
 }
 console.info(`Initialized ${RSI_PERIOD} dummy flat candles at ${firstPrice.toFixed(8)} for neutral RSI=50`);
 this.rsiInitialized = true;
 }
 const candle: Candle = {
 open: recentPrices[0],
 high: Math.max(...recentPrices),
 low: Math.min(...recentPrices),
 close: recentPrices[recentPrices.length - 1],
 volume: recentPrices.length,
 };
 this.df5min.push({ timestamp: currentMin, candle });
 this.df5min = this.df5min.slice(-(LOOKBACK + RSI_PERIOD + 10));
 console.info(`New 5-min candle formed: Timestamp=${currentMin.toISOString()}, O=${candle.open.toFixed(8)}, H=${candle.high.toFixed(8)}, L=${candle.low.toFixed(8)}, C=${candle.close.toFixed(8)}, V=${candle.volume}`);
 if (this.df5min.length >= 2) {
 const i = this.df5min.length - 1;
 const prevCandle = this.df5min[i - 1].candle;
 const currCandle = this.df5min[i].candle;
 let prevRsiRaw = NaN;
 let currentRsiRaw = NaN;
 let shortSignal = false;
 let longSignal = false;
 if (this.df5min.length >= RSI_PERIOD + 2) {
 const closes = this.df5min.map(d => d.candle.close);
 const rsiValues = this.rsi(closes);
 currentRsiRaw = rsiValues[i];
 prevRsiRaw = rsiValues[i - 1];
 shortSignal = (currCandle.high - prevCandle.high > PRICE_EPSILON) && (prevRsiRaw - currentRsiRaw > RSI_EPSILON) && currentRsiRaw > RSI_SHORT_THRESHOLD;
 longSignal = (prevCandle.low - currCandle.low > PRICE_EPSILON) && (currentRsiRaw - prevRsiRaw > RSI_EPSILON) && currentRsiRaw < RSI_LONG_THRESHOLD;
 }
 console.info(`Previous candle: O=${prevCandle.open.toFixed(8)}, H=${prevCandle.high.toFixed(8)}, L=${prevCandle.low.toFixed(8)}, C=${prevCandle.close.toFixed(8)}, RSI=${isNaN(prevRsiRaw) ? 'N/A' : prevRsiRaw.toFixed(12)}`);
 console.info(`Current candle: O=${currCandle.open.toFixed(8)}, H=${currCandle.high.toFixed(8)}, L=${candle.low.toFixed(8)}, C=${currCandle.close.toFixed(8)}, RSI=${isNaN(currentRsiRaw) ? 'N/A' : currentRsiRaw.toFixed(12)}`);
 console.info(`Signals: short=${shortSignal} (RSI=${isNaN(currentRsiRaw) ? 'N/A' : currentRsiRaw.toFixed(12)}), long=${longSignal}`);
 if (shortSignal || longSignal) {
 this.pendingSignal = { short: shortSignal, long: longSignal, price: candle.close };
 console.info(`Signal detected on new 5-min candle! Short=${shortSignal}, Long=${longSignal}, Entry Price=${candle.close.toFixed(8)}`);
 }
 }
 if (this.pendingSignal && this.position === 0) {
 this.processSignals(this.pendingSignal.short, this.pendingSignal.long, this.pendingSignal.price);
 this.pendingSignal = null;
 }
 } else {
 console.warn('No recent prices for 5-min candle; skipping');
 }
 } catch (e) {
 console.error('Aggregate error:', e);
 }
 }

 private async getOrderIdsAfterPlace(userOrderIds: number[]): Promise<(number | undefined)[]> {
 return new Promise((resolve) => {
 const timeout = setTimeout(async () => {
 console.warn('Orders not confirmed via event; falling back to poll');
 let pollAttempts = 0;
 const maxPoll = 30; // Fix: Extended for reliability
 const pollInterval = setInterval(async () => {
 if (pollAttempts >= maxPoll) {
 clearInterval(pollInterval);
 resolve(userOrderIds.map(() => undefined));
 return;
 }
 try {
 const userAccount = this.driftClient!.getUserAccount();
 const orderIds = userOrderIds.map(id => {
 const order = userAccount!.orders.find(o => o.userOrderId === id);
 return order ? order.orderId : undefined;
 });
 if (orderIds.every(id => id !== undefined)) {
 console.info(`Polled order IDs: ${orderIds.join(', ')}`);
 clearInterval(pollInterval);
 resolve(orderIds);
 }
 } catch (e) {
 console.warn('Poll fetch error:', e);
 }
 pollAttempts++;
 }, 500);
 }, 10000);
 const listener = (userAccount: UserAccount) => {
 const orderIds = userOrderIds.map(id => {
 const order = userAccount.orders.find(o => o.userOrderId === id);
 return order ? order.orderId : undefined;
 });
 if (orderIds.every(id => id !== undefined)) {
 clearTimeout(timeout);
 // @ts-ignore
 this.orderSubscriber!.eventEmitter.off('onAccount', listener);
 console.info(`Event order IDs: ${orderIds.join(', ')}`);
 resolve(orderIds);
 }
 };
 // @ts-ignore
 this.orderSubscriber!.eventEmitter.on('onAccount', listener);
 });
 }

 private async handleOrderUpdate(orders: Order[]) {
 this.updateQueue = this.updateQueue.then(() => this.processOrderUpdate(orders));
 }

 private async processOrderUpdate(orders: Order[]) {
 try {
 const perpPosition = this.driftClient!.getUser().getPerpPosition(SOL_PERP_INDEX);
 this.cachedPosition = perpPosition;
 if (perpPosition && perpPosition.baseAssetAmount.abs().gt(new BN(0)) && this.position === 0) {
 this.position = perpPosition.baseAssetAmount.gt(new BN(0)) ? 1 : -1;
 const quoteAmount = Math.abs(perpPosition.quoteEntryAmount.toNumber()) / QUOTE_PRECISION.toNumber();
 const baseAmount = Math.abs(perpPosition.baseAssetAmount.toNumber()) / BASE_PRECISION.toNumber();
 this.entryPrice = quoteAmount / baseAmount;
 console.info(`Position ${this.position === 1 ? 'LONG' : 'SHORT'} at ${this.entryPrice.toFixed(8)}`);
 if (this.position === 1) {
 this.trailSl = this.entryPrice * (1 - SL_PCT);
 this.emergTrailSl = this.entryPrice * (1 - EMERGENCY_SL_PCT);
 this.trailTp = this.entryPrice * (1 + TP_PCT);
 this.lastHigh = this.entryPrice;
 this.lastLow = this.entryPrice;
 } else {
 this.trailSl = this.entryPrice * (1 + SL_PCT);
 this.emergTrailSl = this.entryPrice * (1 + EMERGENCY_SL_PCT);
 this.trailTp = this.entryPrice * (1 - TP_PCT);
 this.lastLow = this.entryPrice;
 this.lastHigh = this.entryPrice;
 }
 this.lastPriceUpdate = this.entryPrice;
 let success = false;
 let attempts = 0;
 while (!success && attempts < 3) {
 attempts++;
 try {
 const slParams = this.getSLOrderParams();
 const tpParams = this.getTPOrderParams();
 const emParams = this.getEmergencySLOrderParams();
 const ordersParams = [slParams, tpParams, emParams];
 const txSig = await this.driftClient!.placeOrders(ordersParams);
 console.info(`Batch protective orders placed: ${txSig}`);
 await new Promise(resolve => setTimeout(resolve, 1000)); // Delay for confirm
 const orderIds = await this.getOrderIdsAfterPlace([slParams.userOrderId, tpParams.userOrderId, emParams.userOrderId]);
 this.slOrderId = orderIds[0];
 this.tpOrderId = orderIds[1];
 this.emergencySlOrderId = orderIds[2];
 if (this.slOrderId && this.tpOrderId && this.emergencySlOrderId) {
 success = true;
 } else {
 console.warn(`Batch IDs incomplete on attempt ${attempts}; retrying`);
 await new Promise(resolve => setTimeout(resolve, 2000)); // Delay retry
 }
 } catch (batchErr: any) {
 if (batchErr.message.includes('UserOrderIdAlreadyInUse')) {
 console.warn(`Batch collision on attempt ${attempts}; retrying with new IDs`);
 await new Promise(resolve => setTimeout(resolve, 1000));
 } else {
 throw batchErr;
 }
 }
 }
 if (!success) {
 console.error('Failed batch after retries; falling back to single places');
 await this.cancelAndPlaceSLOrder();
 await this.cancelAndPlaceTPOrder();
 await this.cancelAndPlaceEmergencySLOrder();
 }
 this.previousBaseAmount = perpPosition.baseAssetAmount.abs();
 if (this.entryTimeout) {
 clearTimeout(this.entryTimeout);
 this.entryTimeout = null;
 }
 this.breakEvenLocked = false;
 } else if (perpPosition && perpPosition.baseAssetAmount.abs().gt(new BN(0)) && this.position !== 0) {
 const currentBase = perpPosition.baseAssetAmount.abs();
 if (currentBase.gt(this.previousBaseAmount)) {
 console.info('Position size increased; updating orders');
 this.previousBaseAmount = currentBase;
 const quoteAmount = Math.abs(perpPosition.quoteEntryAmount.toNumber()) / QUOTE_PRECISION.toNumber();
 const baseAmount = Math.abs(perpPosition.baseAssetAmount.toNumber()) / BASE_PRECISION.toNumber();
 this.entryPrice = quoteAmount / baseAmount;
 await this.batchModifyOrders(true, true, true); // Refresh all on size change
 }
 } else if ((!perpPosition || perpPosition.baseAssetAmount.abs().eq(new BN(0))) && this.position !== 0) {
 console.info('Position closed');
 try {
 console.info('Force-canceling all open perp orders on close');
 await this.driftClient!.cancelOrders(MarketType.PERP, SOL_PERP_INDEX);
 await this.cancelRemnantOrders(); // Fallback for any remnants
 } catch (cancelErr) {
 console.error('Cancel on close error:', cancelErr);
 }
 this.position = 0;
 this.slOrderId = undefined;
 this.tpOrderId = undefined;
 this.emergencySlOrderId = undefined;
 this.previousBaseAmount = new BN(0);
 }
 } catch (e) {
 console.error('Order update error:', e);
 }
 }

 private rsi(series: number[], period: number = RSI_PERIOD): number[] {
 const rsiValues: number[] = Array(series.length).fill(NaN);
 if (series.length < period) return rsiValues;
 let gain = 0, loss = 0;
 for (let i = 1; i <= period; i++) {
 const delta = series[i] - series[i - 1];
 if (delta > 0) gain += delta;
 else loss -= delta;
 }
 let avgGain = gain / period;
 let avgLoss = loss / period;
 if (avgGain === 0 && avgLoss === 0) {
 avgGain = 0.001;
 avgLoss = 0.001;
 }
 let rs = (avgLoss === 0) ? Infinity : avgGain / avgLoss;
 rsiValues[period] = 100 - (100 / (1 + rs));
 for (let i = period + 1; i < series.length; i++) {
 const delta = series[i] - series[i - 1];
 const currentGain = delta > 0 ? delta : 0;
 const currentLoss = delta < 0 ? -delta : 0;
 avgGain = (avgGain * (period - 1) + currentGain) / period;
 avgLoss = (avgLoss * (period - 1) + currentLoss) / period;
 rs = (avgLoss === 0) ? Infinity : avgGain / avgLoss;
 rsiValues[i] = 100 - (100 / (1 + rs));
 }
 return rsiValues;
 }

 private getTickSize(): number {
 return this.marketCache!.amm.orderTickSize.toNumber() / PRICE_PRECISION.toNumber();
 }

 private roundToTick(price: number, direction: 'up' | 'down'): number {
 const tick = this.getTickSize();
 return direction === 'down' ? Math.floor(price / tick) * tick : Math.ceil(price / tick) * tick;
 }

 private async processSignals(shortSignal: boolean, longSignal: boolean, signalPrice: number) {
 try {
 if (this.position !== 0) {
 if ((this.position === 1 && shortSignal) || (this.position === -1 && longSignal)) {
 await this.closePosition(false, false, true);
 return;
 }
 return;
 }
 if (!shortSignal && !longSignal) return;
 console.info(`Processing ${shortSignal ? 'SHORT' : 'LONG'} at ${signalPrice.toFixed(8)}`);
 const hasSufficientVolume = await this.checkVolume();
 if (!hasSufficientVolume) {
 console.info(`Low volume (${this.cachedVolumeUSD.toFixed(0)} USD), skipping`);
 return;
 }
 const perpPosition = this.driftClient!.getUser().getPerpPosition(SOL_PERP_INDEX);
 if (perpPosition && perpPosition.baseAssetAmount.abs().gt(new BN(0))) {
 console.warn('Undetected position, aborting');
 return;
 }
 await this.driftClient!.cancelOrders(MarketType.PERP, SOL_PERP_INDEX); // Fix: Cancel all open perp orders (manual pending) before entry
 let freeCollateral: number | null = null;
 for (let attempt = 0; attempt < 5; attempt++) {
 try {
 freeCollateral = (this.driftClient!.getUser().getFreeCollateral()).toNumber() / QUOTE_PRECISION.toNumber();
 break;
 } catch (e) {
 console.warn(`Collateral fetch attempt ${attempt + 1} failed: ${e}`);
 await new Promise(resolve => setTimeout(resolve, 1000));
 }
 }
 if (freeCollateral === null) {
 console.error('Failed to fetch collateral after retries');
 return;
 }
 if (freeCollateral < INITIAL_COLLATERAL / 2) {
 console.warn('Insufficient margin');
 return;
 }
 await this.cancelRemnantOrders();
 this.marketCache = this.driftClient!.getPerpMarketAccount(SOL_PERP_INDEX);
 if (!this.marketCache) {
 console.error('Market cache not available');
 return;
 }
 const initialMarginFraction = this.marketCache.marginRatioInitial / 10000;
 const maxLeverage = 1 / initialMarginFraction;
 let effectiveNotional = freeCollateral * maxLeverage * MARGIN_BUFFER;
 const requestedNotional = INITIAL_COLLATERAL * LEVERAGE;
 effectiveNotional = Math.min(requestedNotional, effectiveNotional);
 const baseAmount = this.driftClient!.convertToPerpPrecision(effectiveNotional / signalPrice);
 await this.waitForBookUpdate(); // Fetch fresh DLOB
 const mark = this.lastPrice ?? this.driftClient!.getOracleDataForPerpMarket(SOL_PERP_INDEX).price.toNumber() / PRICE_PRECISION.toNumber();
 const tick = this.getTickSize();
 let limPrice: number;
 if (shortSignal) { // Sell (short entry)
 limPrice = Math.max(mark, this.bestBid + tick);
 limPrice = this.roundToTick(limPrice, 'up'); // Round up for better sell price
 } else { // Buy (long entry)
 limPrice = Math.min(mark, this.bestAsk - tick);
 limPrice = this.roundToTick(limPrice, 'down'); // Round down for better buy price
 }
 // Fallback if book timeout left bestBid/Ask at 0 (prevent negative/invalid)
 if (limPrice <= 0 || isNaN(limPrice)) {
 console.warn('Invalid limPrice from book timeout; falling back to mark ± wider slippage');
 limPrice = shortSignal 
 ? mark * (1 + 0.002) // Wider slippage fallback for sell
 : mark * (1 - 0.002); // Wider slippage fallback for buy
 limPrice = shortSignal 
 ? this.roundToTick(limPrice, 'up')
 : this.roundToTick(limPrice, 'down');
 }
 // Depth check
 const direction = shortSignal ? 'ask' : 'bid'; // For short entry (sell), check ask depth; for long (buy), bid depth
 const cumulativeNotional = this.getCumulativeNotional(direction);
 const orderParams: OrderParams = {
 orderType: cumulativeNotional >= MIN_NOTIONAL_DEPTH_USD ? OrderType.LIMIT : OrderType.MARKET,
 marketIndex: SOL_PERP_INDEX,
 direction: shortSignal ? PositionDirection.SHORT : PositionDirection.LONG,
 baseAssetAmount: baseAmount,
 price: cumulativeNotional >= MIN_NOTIONAL_DEPTH_USD ? this.driftClient!.convertToPricePrecision(limPrice) : new BN(0),
 postOnly: cumulativeNotional >= MIN_NOTIONAL_DEPTH_USD ? PostOnlyParams.MUST_POST_ONLY : PostOnlyParams.NONE,
 reduceOnly: false,
 marketType: MarketType.PERP,
 userOrderId: this.getNextUserOrderId(),
 triggerPrice: new BN(0),
 triggerCondition: OrderTriggerCondition.ABOVE,
 oraclePriceOffset: 0,
 bitFlags: new BN(0),
 auctionDuration: 0,
 auctionStartPrice: new BN(0),
 auctionEndPrice: new BN(0),
 maxTs: new BN(0),
 };
 if (cumulativeNotional < MIN_NOTIONAL_DEPTH_USD) {
 console.warn(`Low book depth (${cumulativeNotional.toFixed(2)} USD); falling back to market entry`);
 }
 if (shortSignal ? (limPrice <= this.bestBid) : (limPrice >= this.bestAsk)) {
 console.warn('Would cross; falling back to market entry');
 orderParams.orderType = OrderType.MARKET;
 orderParams.price = new BN(0); // For market
 orderParams.postOnly = PostOnlyParams.NONE;
 }
 console.info(`Entry ${shortSignal ? 'SHORT' : 'LONG'} at ${limPrice.toFixed(8)}`);
 const entryTxSig = await this.driftClient!.placePerpOrder(orderParams);
 console.info(`Entry order placed: ${entryTxSig}`);
 this.entryTimeout = setTimeout(async () => {
 console.info('Entry timeout');
 await this.handleEntryTimeout();
 }, ENTRY_TIMEOUT_MS);
 } catch (e) {
 console.error('Process signal error:', e);
 }
 }

 private async handleEntryTimeout() {
 try {
 const perpPosition = this.driftClient!.getUser().getPerpPosition(SOL_PERP_INDEX);
 if (perpPosition?.baseAssetAmount.abs().gt(new BN(0))) {
 await this.handleOrderUpdate(this.driftClient!.getUserAccount()!.orders);
 } else {
 await this.driftClient!.cancelOrders(MarketType.PERP, SOL_PERP_INDEX);
 }
 } catch (e) {
 console.error('Entry timeout failed:', e);
 }
 }

 private async cancelAndPlaceSLOrder() {
 try {
 // Cancel existing SL if any
 if (this.slOrderId !== undefined) {
 const order = this.driftClient!.getUserAccount()!.orders.find(o => o.orderId === this.slOrderId);
 if (order && isVariant(order.status, 'open')) {
 await this.driftClient!.cancelOrder(this.slOrderId);
 console.info('Canceled old SL');
 }
 this.slOrderId = undefined;
 }
 await new Promise(resolve => setTimeout(resolve, 500)); // short delay after specific cancel
 let attempts = 0;
 const maxAttempts = 10;
 while (attempts < maxAttempts) {
 const slLikeOrders = this.driftClient!.getUserAccount()!.orders.filter(o =>
 isVariant(o.status, 'open') && o.reduceOnly && isVariant(o.marketType, 'perp') &&
 o.marketIndex === SOL_PERP_INDEX && isVariant(o.orderType, 'triggerLimit') &&
 o.triggerCondition === (this.position === 1 ? OrderTriggerCondition.BELOW : OrderTriggerCondition.ABOVE)
 );
 if (slLikeOrders.length === 0) {
 break;
 }
 console.warn(`Still ${slLikeOrders.length} SL-like orders; canceling them`);
 for (const order of slLikeOrders) {
 await this.driftClient!.cancelOrder(order.orderId);
 }
 await new Promise(resolve => setTimeout(resolve, 500));
 attempts++;
 }
 if (attempts === maxAttempts) {
 console.error('Failed to clear SL orders after max attempts');
 return;
 }
 // Place new
 const params = this.getSLOrderParams();
 const txSig = await this.driftClient!.placePerpOrder(params);
 console.info(`New SL placed: ${txSig}`);
 this.slOrderId = await this.placeAndGetOrderId(params, params.userOrderId);
 } catch (e) {
 console.error('Cancel and place SL error:', e);
 }
 }

 private async cancelAndPlaceTPOrder() {
 try {
 // Cancel existing TP if any
 if (this.tpOrderId !== undefined) {
 const order = this.driftClient!.getUserAccount()!.orders.find(o => o.orderId === this.tpOrderId);
 if (order && isVariant(order.status, 'open')) {
 await this.driftClient!.cancelOrder(this.tpOrderId);
 console.info('Canceled old TP');
 }
 this.tpOrderId = undefined;
 }
 await new Promise(resolve => setTimeout(resolve, 500)); // short delay after specific cancel
 let attempts = 0;
 const maxAttempts = 10;
 while (attempts < maxAttempts) {
 const tpLikeOrders = this.driftClient!.getUserAccount()!.orders.filter(o =>
 isVariant(o.status, 'open') && o.reduceOnly && isVariant(o.marketType, 'perp') &&
 o.marketIndex === SOL_PERP_INDEX && isVariant(o.orderType, 'triggerLimit') &&
 o.triggerCondition === (this.position === 1 ? OrderTriggerCondition.ABOVE : OrderTriggerCondition.BELOW)
 );
 if (tpLikeOrders.length === 0) {
 break;
 }
 console.warn(`Still ${tpLikeOrders.length} TP-like orders; canceling them`);
 for (const order of tpLikeOrders) {
 await this.driftClient!.cancelOrder(order.orderId);
 }
 await new Promise(resolve => setTimeout(resolve, 500));
 attempts++;
 }
 if (attempts === maxAttempts) {
 console.error('Failed to clear TP orders after max attempts');
 return;
 }
 // Place new
 const params = this.getTPOrderParams();
 const txSig = await this.driftClient!.placePerpOrder(params);
 console.info(`New TP placed: ${txSig}`);
 this.tpOrderId = await this.placeAndGetOrderId(params, params.userOrderId);
 } catch (e) {
 console.error('Cancel and place TP error:', e);
 }
 }

 private async cancelAndPlaceEmergencySLOrder() {
 try {
 // Cancel existing EM SL if any
 if (this.emergencySlOrderId !== undefined) {
 const order = this.driftClient!.getUserAccount()!.orders.find(o => o.orderId === this.emergencySlOrderId);
 if (order && isVariant(order.status, 'open')) {
 await this.driftClient!.cancelOrder(this.emergencySlOrderId);
 console.info('Canceled old EM SL');
 }
 this.emergencySlOrderId = undefined;
 }
 await new Promise(resolve => setTimeout(resolve, 500)); // short delay after specific cancel
 let attempts = 0;
 const maxAttempts = 10;
 while (attempts < maxAttempts) {
 const emSlLikeOrders = this.driftClient!.getUserAccount()!.orders.filter(o =>
 isVariant(o.status, 'open') && o.reduceOnly && isVariant(o.marketType, 'perp') &&
 o.marketIndex === SOL_PERP_INDEX && isVariant(o.orderType, 'triggerMarket') &&
 o.triggerCondition === (this.position === 1 ? OrderTriggerCondition.BELOW : OrderTriggerCondition.ABOVE)
 );
 if (emSlLikeOrders.length === 0) {
 break;
 }
 console.warn(`Still ${emSlLikeOrders.length} EM SL-like orders; canceling them`);
 for (const order of emSlLikeOrders) {
 await this.driftClient!.cancelOrder(order.orderId);
 }
 await new Promise(resolve => setTimeout(resolve, 500));
 attempts++;
 }
 if (attempts === maxAttempts) {
 console.error('Failed to clear EM SL orders after max attempts');
 return;
 }
 // Place new
 const params = this.getEmergencySLOrderParams();
 const txSig = await this.driftClient!.placePerpOrder(params);
 console.info(`New EM SL placed: ${txSig}`);
 this.emergencySlOrderId = await this.placeAndGetOrderId(params, params.userOrderId);
 } catch (e) {
 console.error('Cancel and place EM SL error:', e);
 }
 }

 private async placeSLOrder() {
 const params = this.getSLOrderParams();
 const txSig = await this.driftClient!.placePerpOrder(params);
 console.info(`SL placed: ${txSig}`);
 this.slOrderId = await this.placeAndGetOrderId(params, params.userOrderId);
 }

 private async placeTPOrder() {
 const params = this.getTPOrderParams();
 const txSig = await this.driftClient!.placePerpOrder(params);
 console.info(`TP placed: ${txSig}`);
 this.tpOrderId = await this.placeAndGetOrderId(params, params.userOrderId);
 }

 private async placeEmergencySLOrder() {
 const params = this.getEmergencySLOrderParams();
 const txSig = await this.driftClient!.placePerpOrder(params);
 console.info(`EM SL placed: ${txSig}`);
 this.emergencySlOrderId = await this.placeAndGetOrderId(params, params.userOrderId);
 }

 private async placeAndGetOrderId(params: OrderParams, userOrderId: number): Promise<number | undefined> {
 return new Promise((resolve) => {
 const listener = (userAccount: UserAccount) => {
 const order = userAccount.orders.find(o => o.userOrderId === userOrderId);
 if (order) {
 // @ts-ignore
 this.orderSubscriber!.eventEmitter.off('onAccount', listener);
 resolve(order.orderId);
 }
 };
 // @ts-ignore
 this.orderSubscriber!.eventEmitter.on('onAccount', listener);
 setTimeout(async () => {
 const order = this.driftClient!.getUserAccount()!.orders.find(o => o.userOrderId === userOrderId);
 resolve(order ? order.orderId : undefined);
 }, 5000);
 });
 }

 private async closePosition(tp: boolean = false, sl: boolean = false, flip: boolean = false) {
 try {
 console.info(`Closing (TP:${tp}, SL:${sl}, Flip:${flip})`);
 await this.cancelRemnantOrders();
 const perpPos = this.cachedPosition ?? this.driftClient!.getUser().getPerpPosition(SOL_PERP_INDEX);
 if (!perpPos || perpPos.baseAssetAmount.abs().eq(new BN(0))) {
 return;
 }
 const base = perpPos.baseAssetAmount.abs();
 const dir = perpPos.baseAssetAmount.gt(new BN(0)) ? PositionDirection.SHORT : PositionDirection.LONG;
 await this.waitForBookUpdate();
 const mark = this.lastPrice ?? this.driftClient!.getOracleDataForPerpMarket(SOL_PERP_INDEX).price.toNumber() / PRICE_PRECISION.toNumber();
 const tick = this.getTickSize();
 let limPrice: number;
 if (dir === PositionDirection.SHORT) { // Sell (close long)
 limPrice = Math.max(mark, this.bestBid + tick);
 limPrice = this.roundToTick(limPrice, 'up');
 } else { // Buy (close short)
 limPrice = Math.min(mark, this.bestAsk - tick);
 limPrice = this.roundToTick(limPrice, 'down');
 }
 // Fallback if book timeout
 if (limPrice <= 0 || isNaN(limPrice)) {
 console.warn('Invalid limPrice from book timeout; falling back to mark ± wider slippage');
 limPrice = dir === PositionDirection.SHORT 
 ? mark * (1 + 0.002) // Wider slippage fallback for sell
 : mark * (1 - 0.002); // Wider slippage fallback for buy
 limPrice = dir === PositionDirection.SHORT 
 ? this.roundToTick(limPrice, 'up')
 : this.roundToTick(limPrice, 'down');
 }
 // Depth check
 const direction = dir === PositionDirection.SHORT ? 'bid' : 'ask'; // For close long (sell), check bid depth; close short (buy), ask depth
 const cumulativeNotional = this.getCumulativeNotional(direction);
 const params: OrderParams = {
 orderType: cumulativeNotional >= MIN_NOTIONAL_DEPTH_USD ? OrderType.LIMIT : OrderType.MARKET,
 marketIndex: SOL_PERP_INDEX,
 direction: dir,
 baseAssetAmount: base,
 reduceOnly: true,
 postOnly: cumulativeNotional >= MIN_NOTIONAL_DEPTH_USD ? PostOnlyParams.MUST_POST_ONLY : PostOnlyParams.NONE,
 marketType: MarketType.PERP,
 price: cumulativeNotional >= MIN_NOTIONAL_DEPTH_USD ? this.driftClient!.convertToPricePrecision(limPrice) : new BN(0),
 userOrderId: this.getNextUserOrderId(),
 triggerPrice: new BN(0),
 triggerCondition: OrderTriggerCondition.ABOVE,
 oraclePriceOffset: 0,
 bitFlags: new BN(0),
 auctionDuration: 0,
 auctionStartPrice: new BN(0),
 auctionEndPrice: new BN(0),
 maxTs: new BN(0),
 };
 if (cumulativeNotional < MIN_NOTIONAL_DEPTH_USD) {
 console.warn(`Low book depth (${cumulativeNotional.toFixed(2)} USD); falling back to market close`);
 }
 if (dir === PositionDirection.SHORT ? (limPrice <= this.bestBid) : (limPrice >= this.bestAsk)) {
 console.warn('Would cross; falling back to market close');
 params.orderType = OrderType.MARKET;
 params.price = new BN(0);
 params.postOnly = PostOnlyParams.NONE;
 }
 const txSig = await this.driftClient!.placePerpOrder(params);
 console.info(`Close at ${limPrice.toFixed(8)}, txSig: ${txSig}`);
 } catch (e) {
 console.error('Close error:', e);
 console.warn('Emergency market close');
 try {
 const perpPos = this.cachedPosition ?? this.driftClient!.getUser().getPerpPosition(SOL_PERP_INDEX);
 if (perpPos && perpPos.baseAssetAmount.abs().gt(new BN(0))) {
 const base = perpPos.baseAssetAmount.abs();
 const dir = perpPos.baseAssetAmount.gt(new BN(0)) ? PositionDirection.SHORT : PositionDirection.LONG;
 const params: OrderParams = {
 orderType: OrderType.MARKET,
 marketIndex: SOL_PERP_INDEX,
 direction: dir,
 baseAssetAmount: base,
 reduceOnly: true,
 marketType: MarketType.PERP,
 userOrderId: this.getNextUserOrderId(),
 price: new BN(0),
 postOnly: PostOnlyParams.NONE,
 triggerPrice: new BN(0),
 triggerCondition: OrderTriggerCondition.ABOVE,
 oraclePriceOffset: 0,
 bitFlags: new BN(0),
 auctionDuration: 0,
 auctionStartPrice: new BN(0),
 auctionEndPrice: new BN(0),
 maxTs: new BN(0),
 };
 const txSig = await this.driftClient!.placePerpOrder(params);
 console.info('Market close:', txSig);
 }
 } catch (marketErr) {
 console.error('Market close failed:', marketErr);
 }
 }
 }

 public async run() {
 await this.initDrift();
 setInterval(async () => {
 if (this.position === 0) {
 const perpPosition = this.driftClient!.getUser().getPerpPosition(SOL_PERP_INDEX);
 if (!perpPosition || perpPosition.baseAssetAmount.abs().eq(new BN(0))) {
 await this.cancelRemnantOrders(); // Periodic remnant check
 }
 }
 }, POSITION_CHECK_INTERVAL_MS);
 process.on('SIGINT', async () => {
 console.info('Shutdown');
 if (this.pythSse) this.pythSse.close();
 if (this.position !== 0) {
 const perpPosition = this.driftClient!.getUser().getPerpPosition(SOL_PERP_INDEX);
 if (perpPosition && perpPosition.baseAssetAmount.abs().gt(new BN(0))) {
 await this.closePosition();
 } else {
 this.position = 0;
 }
 }
 await this.cancelRemnantOrders(); // Fix: Cancel before unsub
 if (this.orderSubscriber) await this.orderSubscriber.unsubscribe();
 if (this.eventSubscriber) await this.eventSubscriber.unsubscribe();
 await this.driftClient!.unsubscribe();
 console.info('Done');
 process.exit(0);
 });
 await new Promise(() => {});
 }
}

async function main() {
 const bot = new TradingBot();
 await bot.run();
}
main().catch(console.error);