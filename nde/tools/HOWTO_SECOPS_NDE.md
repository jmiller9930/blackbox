# SecOps NDE — HOWTO

## Kick off (smoke)

Run on the NDE host:

```bash
/data/NDE/tools/run_graph.sh --domain secops --mode smoke
```

## What the system does

* validate_sources
* process_sources
* validate_dataset
* smoke_train
* run_eval
* evaluate_gate
* auto_reinforce (if needed)
* final_exam (on pass)
* certify (on pass)

## Where to look

Run folder:

```
/data/NDE/secops/runs/<run_id>/
```

Key files:

* `state.json` — overall status
* `nodes/<node>/node_status.json` — per-step results
* `CERTIFICATE.json` — only present if fully certified

## Full training (only after approval)

```bash
touch /data/NDE/secops/runs/<run_id>/APPROVED

/data/NDE/tools/run_graph.sh \
  --domain secops \
  --mode full \
  --require-approval
```

## Rules

* Do not run training or eval directly
* Do not bypass LangGraph
* All data must come from `/data/NDE/secops/sources/raw/`
* Certification requires final exam pass
