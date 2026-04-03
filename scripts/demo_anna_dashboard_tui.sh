#!/usr/bin/env bash
# Simulate a populated Anna training dashboard (Rich TUI) in a temp dir — no live Solana/DB required.
# Usage (repo root): ./scripts/demo_anna_dashboard_tui.sh
set -euo pipefail
REPO="${BLACKBOX_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO"
export PYTHONPATH="${REPO}${PYTHONPATH:+:${PYTHONPATH}}"
export ANNA_SKIP_PREFLIGHT=1
D="$(mktemp -d)"
export BLACKBOX_ANNA_TRAINING_DIR="$D"
trap 'rm -rf "$D"' EXIT

python3 <<'PY'
from modules.anna_training.catalog import default_state
from modules.anna_training.paper_trades import append_paper_trade
from modules.anna_training.store import save_state

st = default_state()
st["curriculum_id"] = "grade_12_paper_only"
st["training_method_id"] = "karpathy_loop_v1"
st["karpathy_loop_iteration"] = 42
st["karpathy_loop_last_tick_utc"] = "2026-04-03T12:00:00Z"
st["carryforward_bullets"] = [
    "Grade 12 paper harness: RCS/RCA discipline carries forward.",
    "Math engine: cite FACT lines only; epistemic honesty when n is small.",
]
st["completed_curriculum_milestones"] = ["grade_12_paper_only"]
st["cumulative_learning_log"] = [
    {
        "ts_utc": "2026-04-03T11:00:00Z",
        "kind": "demo",
        "curriculum_id": "grade_12_paper_only",
        "summary": "Simulated milestone log entry.",
    },
]
save_state(st)
for i in range(12):
    won = i % 4 != 0
    append_paper_trade(
        symbol="SOL-PERP",
        side="long" if i % 2 == 0 else "short",
        result="won" if won else "lost",
        pnl_usd=8.5 if won else -3.25,
        timeframe="5m",
        notes="simulated",
    )
PY

PYBIN="${REPO}/.venv/bin/python3"
[[ -x "$PYBIN" ]] || PYBIN="$(command -v python3)"
exec "$PYBIN" "${REPO}/scripts/runtime/anna_training_cli.py" dashboard
