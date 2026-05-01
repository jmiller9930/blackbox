# FinQuant Unified

This directory is the home for FinQuant's unified agent work.

## Isolation boundary

**Do not mix anything here with:**
- existing UI code
- Flask API routes
- dashboard code
- current Student seam runtime
- current replay runner
- existing scorecard wiring
- existing operator batch code
- production runtime paths

## Subdirectories

| Path | Purpose |
|------|---------|
| `agent_lab/` | Isolated FinQuant Unified Agent Lab — prove lifecycle trading behavior before wiring back into the app |

## Intent

The application is not the agent.  
FinQuant is the agent.  
This lab is where we prove the agent works before integrating it.

See `agent_lab/README.md` for execution instructions.  
See `docs/architect/FINQUANT_UNIFIED_AGENT_LAB_ARCHITECTURE_001.md` for the normative architecture directive.
