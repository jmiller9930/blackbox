/**
 * Venue adapter model — BLACK BOX trading_core (TypeScript)
 *
 * **Executors (registry):**
 * - **Billy** → **Drift** venue only.
 * - **Jack** → **Jupiter Perps** venue only.
 *
 * Anna routes approved work to **one** executor per intent by **venue** (`VenueId`), not by informal chat.
 *
 * **Jupiter Perps ≠ Drift (integration path):** Same chain (Solana) does **not** mean the same stack. They differ by **program id**, **SDK / client**, **account graph** (PDAs, custodies, pool), **instruction** shapes, and usually **feeds / subscriptions**. Jack’s adapter is a **separate codebase path** from Billy’s — not a flag on one Drift client.
 *
 * **Rules**
 * - Keep **Drift** and **Jupiter** implementation **separate** (different modules, no shared SDK soup).
 * - Keep **strategy** (signals, sizing, trails) separate from **venue** (accounts, submits, fills) when you split the monolith.
 *
 * **Python parity:** `modules/execution_adapter/` — structured handoff + lane token; map `VenueId` / `executor_agent_id` to the right adapter.
 *
 * **This file** documents intent; wire adapters in `drift_*.ts` / `jupiter_*.ts` as implementation lands.
 */

/** Deployed Solana perp venues; each maps to exactly one executor agent in `agents/agent_registry.json`. */
export type VenueId = 'drift' | 'jupiter_perp';

/**
 * Default venue for new intents and config when not overridden: **Jupiter Perps** → **Jack**.
 * Override with env / policy (e.g. `BLACKBOX_DEFAULT_VENUE=drift`) when implementation reads it.
 */
export const DEFAULT_VENUE_ID: VenueId = 'jupiter_perp';

export const DEFAULT_EXECUTOR_AGENT_ID: 'jack' = 'jack';

/**
 * Which venue (and thus which executor: Billy vs Jack) is active for this process or intent.
 * - `single`: one venue — typical production.
 * - `multi`: more than one adapter may be loaded; routing must be explicit, never implicit.
 */
export type VenueRoutingPolicy =
  | { mode: 'single'; venue: VenueId; executorAgentId: 'billy' | 'jack' }
  | {
      mode: 'multi';
      venues: readonly VenueId[];
      defaultVenue: VenueId;
    };

/** Maps venue to executor agent id (see `agents/agent_registry.json`). */
export function executorForVenue(venue: VenueId): 'billy' | 'jack' {
  switch (venue) {
    case 'drift':
      return 'billy';
    case 'jupiter_perp':
      return 'jack';
  }
}
