# CONTEXT_PROFILE — Mia

<!-- Generated from ../../agent_registry.json — edit registry and re-run scripts/render_agent_registry.py -->

Defines what context the **runtime injects**, what this agent may **write back**, **trusted memory** reuse, **artifact** relevance, and **conversation** participation. See `contextProfileContract` in `agents/agent_registry.json`.

## defaultContextScopes

- market_feed_symbol_scope
- last_n_ticks_or_candles_readonly

## allowedContextClasses

- market_api_read
- normalized_quote_snapshot

## writableContextClasses

- ephemeral_quote_cache_under_ttl

## reusableMemoryPolicy

- `none`

## artifactRelevance

- market_data_client_response
- price_volume_tick

## bundleSections

- identity
- tools
- contextProfile
- symbol_scope

## conversationParticipationMode

- `read_only_feed`
