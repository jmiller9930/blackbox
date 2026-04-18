#!/usr/bin/env sh
# Reload pattern-game Flask on the lab host after commit + push + remote pull.
# Same as: python3 scripts/gsync.py --pattern-game
cd "$(dirname "$0")/.." || exit 1
exec python3 scripts/gsync.py --pattern-game "$@"
