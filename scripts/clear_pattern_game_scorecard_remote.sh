#!/usr/bin/env bash
# Truncate pattern-game batch scorecard JSONL on the **lab host** (default: clawbot).
# The operator UI reads that file on the server — clearing only a Mac clone does nothing.
#
# Env (same defaults as scripts/gsync.py):
#   GSYNC_SSH / BLACKBOX_SYNC_SSH   default: jmiller@clawbot.a51.corp
#   BLACKBOX_REMOTE_HOME          default: blackbox  (repo dir under remote $HOME)
#
# Usage: ./scripts/clear_pattern_game_scorecard_remote.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_TARGET="${GSYNC_SSH:-${BLACKBOX_SYNC_SSH:-jmiller@clawbot.a51.corp}}"
REMOTE_REPO_NAME="${BLACKBOX_REMOTE_HOME:-blackbox}"

echo "clear_pattern_game_scorecard_remote: SSH ${SSH_TARGET} repo ~/${REMOTE_REPO_NAME}"

ssh "${SSH_TARGET}" bash -s <<EOF
set -euo pipefail
REPO="\${HOME}/${REMOTE_REPO_NAME}"
cd "\${REPO}"
export PYTHONPATH="\${REPO}"
python3 <<'PY'
from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl

p = default_batch_scorecard_jsonl()
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text("", encoding="utf-8")
print("cleared", str(p.resolve()), p.stat().st_size, "bytes")
PY
EOF

echo "clear_pattern_game_scorecard_remote: done (hard-refresh the pattern-game scorecard in the browser)."
