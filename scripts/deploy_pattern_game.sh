#!/usr/bin/env sh
# Full end-to-end pattern-game deploy: commit (if needed) → push → lab git pull → restart Flask
# on :8765 → verify remote HEAD matches origin and HTTP X-Pattern-Game-UI-Version.
# Run from repo root: ./scripts/deploy_pattern_game.sh
# Same as: ./scripts/sync_pattern_game.sh
cd "$(dirname "$0")/.." || exit 1
exec python3 scripts/gsync.py --pattern-game "$@"
