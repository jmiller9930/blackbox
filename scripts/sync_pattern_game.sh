#!/usr/bin/env sh
# Alias for deploy_pattern_game.sh — full E2E pattern-game deploy + verify.
cd "$(dirname "$0")/.." || exit 1
exec python3 scripts/gsync.py --pattern-game "$@"
